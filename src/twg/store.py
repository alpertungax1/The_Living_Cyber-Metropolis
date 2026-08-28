"""Technocore KV Store manager for twg1 protocol according to SPEC.md §4."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from src.twg.http import TechnocoreHTTP, CASConflictError

logger = logging.getLogger("twg.store")


class TwgStore:
    """Manages twg1 entities in Technocore KV store with CAS semantics."""

    def __init__(self, http: TechnocoreHTTP) -> None:
        self.http = http

    # ==================== AGENTS ====================

    async def register_agent(
        self,
        fp16: str,
        did: str,
        mailbox: str,
        svc: Optional[List[str]] = None,
        max_in: int = 4,
        sla_s: int = 120,
    ) -> None:
        """Update /kv/twg-agents/<fp16>."""
        agent_data = {
            "v": 1,
            "did": did,
            "svc": svc or ["observe"],
            "mb": mailbox,
            "cap": {"max_in": max_in, "sla_s": sla_s},
            "seen": int(time.time()),
        }
        await self.http.set_kv("twg-agents", fp16, json.dumps(agent_data))

    async def get_agent(self, fp16: str) -> Optional[Dict[str, Any]]:
        raw = await self.http.get_kv("twg-agents", fp16)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    # ==================== JOBS & STATE MACHINE ====================

    async def create_job(
        self,
        job_id: str,
        kind: str,
        by_did: str,
        sla: int = 600,
        pay: str = "rep",
        input_target: str = "room:lobby",
        out_note: Optional[str] = None,
    ) -> bool:
        """Create new job record in /kv/twg-jobs/<job_id> with ?if_absent=1."""
        now = int(time.time())
        job_record = {
            "v": 1,
            "id": job_id,
            "st": "open",
            "kind": kind,
            "by": by_did,
            "sla": sla,
            "pay": pay,
            "in": input_target,
            "out": out_note or f"note:twg-jobs/{job_id}-out",
            "worker": None,
            "bid": [],
            "ts": now,
            "exp": now + sla,
            "seq": None,
        }
        val_str = json.dumps(job_record)
        try:
            await self.http.set_kv("twg-jobs", job_id, val_str, if_absent=True)
            # Add to open index
            await self.add_to_open_index(job_id)
            return True
        except CASConflictError:
            logger.warning("Job %s already exists", job_id)
            return False

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        raw = await self.http.get_kv("twg-jobs", job_id)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    async def append_bid(self, job_id: str, worker_did: str, eta: int, conf: float) -> bool:
        """Append bid to job.bid[] with CAS."""
        raw = await self.http.get_kv("twg-jobs", job_id)
        if not raw:
            return False
        try:
            data = json.loads(raw)
            if data.get("st") != "open":
                return False
            data.setdefault("bid", []).append({
                "worker": worker_did,
                "eta": eta,
                "conf": conf,
                "ts": int(time.time()),
            })
            new_str = json.dumps(data)
            await self.http.set_kv("twg-jobs", job_id, new_str, if_match=raw)
            return True
        except CASConflictError:
            return False
        except Exception:
            return False

    async def accept_job(self, job_id: str, worker_did: str, room_name: str) -> bool:
        """Transition job from open -> accepted with CAS."""
        raw = await self.http.get_kv("twg-jobs", job_id)
        if not raw:
            return False
        try:
            data = json.loads(raw)
            if data.get("st") != "open":
                return False
            data["st"] = "accepted"
            data["worker"] = worker_did
            data["room"] = room_name
            new_str = json.dumps(data)
            await self.http.set_kv("twg-jobs", job_id, new_str, if_match=raw)
            return True
        except CASConflictError:
            return False

    async def deliver_job(self, job_id: str, sha256_hex: str, out_text: str) -> bool:
        """Write out note and transition accepted -> delivered with CAS."""
        # 1. Write out note
        await self.http.set_kv("twg-jobs", f"{job_id}-out", out_text)

        # 2. Update job record
        raw = await self.http.get_kv("twg-jobs", job_id)
        if not raw:
            return False
        try:
            data = json.loads(raw)
            if data.get("st") != "accepted":
                return False
            data["st"] = "delivered"
            data["out_sha256"] = sha256_hex
            new_str = json.dumps(data)
            await self.http.set_kv("twg-jobs", job_id, new_str, if_match=raw)
            return True
        except CASConflictError:
            return False

    async def close_job(self, job_id: str, ok: bool = True) -> bool:
        """Transition delivered -> closed or disputed with CAS."""
        raw = await self.http.get_kv("twg-jobs", job_id)
        if not raw:
            return False
        try:
            data = json.loads(raw)
            if data.get("st") != "delivered":
                return False
            data["st"] = "closed" if ok else "disputed"
            new_str = json.dumps(data)
            await self.http.set_kv("twg-jobs", job_id, new_str, if_match=raw)
            await self.remove_from_open_index(job_id)
            return True
        except CASConflictError:
            return False

    async def expire_job(self, job_id: str) -> bool:
        """Transition open|accepted -> expired if now > exp with CAS."""
        raw = await self.http.get_kv("twg-jobs", job_id)
        if not raw:
            return False
        try:
            data = json.loads(raw)
            now = int(time.time())
            if data.get("st") in ("open", "accepted") and now > data.get("exp", 0):
                data["st"] = "expired"
                new_str = json.dumps(data)
                await self.http.set_kv("twg-jobs", job_id, new_str, if_match=raw)
                await self.remove_from_open_index(job_id)
                return True
            return False
        except CASConflictError:
            return False

    # ==================== INDICES ====================

    async def add_to_open_index(self, job_id: str) -> None:
        """Add job_id to /kv/twg-index/open."""
        for _ in range(3):
            raw = await self.http.get_kv("twg-index", "open")
            ids = []
            if raw:
                try:
                    ids = json.loads(raw).get("ids", [])
                except Exception:
                    pass
            if job_id not in ids:
                ids.append(job_id)
                val_str = json.dumps({"v": 1, "ids": ids, "t": int(time.time())})
                try:
                    await self.http.set_kv("twg-index", "open", val_str, if_match=raw)
                    break
                except CASConflictError:
                    continue
            else:
                break

    async def remove_from_open_index(self, job_id: str) -> None:
        """Remove job_id from /kv/twg-index/open and append to /kv/twg-index/recent."""
        for _ in range(3):
            raw = await self.http.get_kv("twg-index", "open")
            if not raw:
                break
            try:
                ids = json.loads(raw).get("ids", [])
                if job_id in ids:
                    ids.remove(job_id)
                    val_str = json.dumps({"v": 1, "ids": ids, "t": int(time.time())})
                    await self.http.set_kv("twg-index", "open", val_str, if_match=raw)
                    break
            except CASConflictError:
                continue
            except Exception:
                break

    # ==================== CURSORS & STATS ====================

    async def get_cursors(self) -> Dict[str, int]:
        raw = await self.http.get_kv("twg-stats", "cursor")
        if not raw:
            return {"workgraph": 0, "events": 0, "board": 0, "lobby": 0}
        try:
            return json.loads(raw)
        except Exception:
            return {"workgraph": 0, "events": 0, "board": 0, "lobby": 0}

    async def save_cursors(self, cursors: Dict[str, int]) -> None:
        cursors["v"] = 1
        await self.http.set_kv("twg-stats", "cursor", json.dumps(cursors))

    async def save_hourly_stats(self, stats: Dict[str, Any]) -> None:
        stats["v"] = 1
        stats["t"] = int(time.time())
        await self.http.set_kv("twg-stats", "hourly", json.dumps(stats))
