"""Crash-proof state manager synced to Technocore KV store with CAS semantics.

Ensures that even if the daemon process terminates, all room cursors,
task counters, and heartbeat timestamps are preserved and recovered on restart.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from client import TechnocoreClient, CASConflictError
from config import STATE_NS

logger = logging.getLogger("workgraph.state")

LOCAL_STATE_FILE = Path(__file__).resolve().parent / "local_state.json"


class StateManager:
    """Manages persistent state locally and remotely on Technocore KV."""

    def __init__(self, client: TechnocoreClient, ns: str = STATE_NS) -> None:
        self.client = client
        self.ns = ns
        self._lock = asyncio.Lock()
        self.state: Dict[str, Any] = {
            "cursors": {
                "events": 0,
                "lobby": 0,
                "mailbox": 0,
            },
            "last_heartbeat_ts": 0,
            "total_messages_processed": 0,
            "total_tasks_completed": 0,
            "total_rooms_discovered": 0,
            "known_rooms": [],
            "known_dids": [],
        }
        self._load_local()

    def _load_local(self) -> None:
        """Load state from local file if exists."""
        if LOCAL_STATE_FILE.exists():
            try:
                with open(LOCAL_STATE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.state.update(data)
                        # Ensure lists and dicts are preserved
                        if "cursors" not in self.state:
                            self.state["cursors"] = {}
            except Exception as exc:
                logger.warning("Failed to load local state: %s", exc)

    def _save_local(self) -> None:
        """Save state to local JSON file."""
        try:
            with open(LOCAL_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2)
        except Exception as exc:
            logger.warning("Failed to save local state: %s", exc)

    async def bootstrap(self) -> None:
        """Recover state from Technocore KV and merge with local state."""
        async with self._lock:
            try:
                keys = await self.client.list_kv_keys(self.ns)
                for key in keys:
                    try:
                        val = await self.client.get_kv(self.ns, key)
                        if val is None:
                            continue
                        if key.startswith("cursor_"):
                            room_name = key[len("cursor_"):]
                            remote_seq = int(val) if val.isdigit() else 0
                            local_seq = self.state["cursors"].get(room_name, 0)
                            self.state["cursors"][room_name] = max(local_seq, remote_seq)
                        elif key == "last_heartbeat_ts" and val.isdigit():
                            self.state["last_heartbeat_ts"] = max(
                                self.state["last_heartbeat_ts"], int(val)
                            )
                        elif key == "total_tasks_completed" and val.isdigit():
                            self.state["total_tasks_completed"] = max(
                                self.state["total_tasks_completed"], int(val)
                            )
                    except Exception as err:
                        logger.warning("Error fetching KV key %s: %s", key, err)
                self._save_local()
                logger.info("State bootstrapped. Cursors: %s", self.state["cursors"])
            except Exception as exc:
                logger.warning("Remote KV bootstrap failed (will use local): %s", exc)

    def get_cursor(self, room: str) -> int:
        """Get the current cursor seq for a room."""
        return self.state["cursors"].get(room, 0)

    async def update_cursor(self, room: str, seq: int) -> None:
        """Update cursor locally and attempt CAS sync to KV."""
        async with self._lock:
            old_seq = self.state["cursors"].get(room, 0)
            if seq <= old_seq:
                return
            self.state["cursors"][room] = seq
            self._save_local()

        # Fire-and-forget sync to KV with CAS
        asyncio.create_task(self._sync_kv_key(f"cursor_{room}", str(seq), str(old_seq)))

    async def increment_counter(self, counter_name: str, delta: int = 1) -> int:
        """Increment a counter and sync to KV."""
        async with self._lock:
            current = self.state.get(counter_name, 0)
            new_val = current + delta
            self.state[counter_name] = new_val
            self._save_local()

        asyncio.create_task(self._sync_kv_key(counter_name, str(new_val), str(current)))
        return new_val

    async def set_heartbeat_timestamp(self, ts: int) -> None:
        """Record heartbeat timestamp."""
        async with self._lock:
            old_ts = self.state.get("last_heartbeat_ts", 0)
            self.state["last_heartbeat_ts"] = ts
            self._save_local()

        asyncio.create_task(self._sync_kv_key("last_heartbeat_ts", str(ts), str(old_ts)))

    async def _sync_kv_key(self, key: str, value: str, old_value: Optional[str] = None) -> None:
        """Sync a single key to Technocore KV using CAS."""
        try:
            if old_value and old_value != "0":
                try:
                    await self.client.set_kv(self.ns, key, value, if_match=old_value)
                except CASConflictError:
                    # Overwrite if we lost the race or value advanced
                    await self.client.set_kv(self.ns, key, value)
            else:
                await self.client.set_kv(self.ns, key, value)
        except Exception as exc:
            logger.debug("Failed to sync key %s to KV: %s", key, exc)

    def record_discovered_room(self, room: str) -> None:
        """Track newly discovered public room."""
        if room not in self.state["known_rooms"]:
            self.state["known_rooms"].append(room)
            self.state["total_rooms_discovered"] = len(self.state["known_rooms"])
            self._save_local()

    def record_did_interaction(self, did: str) -> None:
        """Track observed active DID."""
        if did not in self.state["known_dids"]:
            self.state["known_dids"].append(did)
            self._save_local()
