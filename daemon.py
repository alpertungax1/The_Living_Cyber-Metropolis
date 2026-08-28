"""Autonomous 24/7 Daemon for Technocore Work Graph (twg1 protocol).

Coordinates polling of /r/events, /r/lobby, /r/workgraph, /r/d-twg-board,
dynamic rooms, and the private mailbox (mb-p-...).
Enforces Technocore long-polling rules:
- wait=10 is strictly used with since=<cursor>
- Rate-limit aware pacing (0.5s pause per iteration)
- Sharded DID discovery notes, heartbeats, and periodic field guides.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import List, Set

from client import TechnocoreClient
from config import (
    BOARD_ROOM,
    DID,
    DID_KEY_PATH,
    DID_SHARD,
    EVENTS_ROOM,
    FIELD_GUIDE_INTERVAL,
    HEARTBEAT_INTERVAL,
    LOBBY_ROOM,
    MAILBOX_NAME,
    POLL_WAIT_SECONDS,
    PROTOCOL_ID,
    PUBLIC_WORKGRAPH_ROOM,
    PULSE_ROOM,
    TOPIC_BOARD,
    TOPIC_WORKGRAPH,
)
from observer import NetworkObserver
from state import StateManager
from task_engine import TaskEngine

logger = logging.getLogger("workgraph.daemon")


class WorkGraphDaemon:
    """The central orchestrator running background agent tasks according to twg1 SPEC.md."""

    def __init__(
        self,
        client: TechnocoreClient,
        state_mgr: StateManager,
        observer: NetworkObserver,
        task_engine: TaskEngine,
    ) -> None:
        self.client = client
        self.state_mgr = state_mgr
        self.observer = observer
        self.task_engine = task_engine
        self._running = False
        self._tasks: List[asyncio.Task] = []
        self._tracked_rooms: Set[str] = {
            LOBBY_ROOM,
            EVENTS_ROOM,
            PUBLIC_WORKGRAPH_ROOM,
            BOARD_ROOM,
        }

    async def initialize(self) -> None:
        """Bootstrap state and register DID identity on Technocore."""
        logger.info("Initializing Work Graph Daemon (%s) for DID: %s", PROTOCOL_ID, DID)
        await self.state_mgr.bootstrap()
        await self.publish_identity()
        await self._bootstrap_recent_activity()

    async def _bootstrap_recent_activity(self) -> None:
        """Fetch recent lobby messages on boot so counters and graph start populated."""
        try:
            msgs = await self.client.read_room(LOBBY_ROOM, limit=50, as_json=True)
            if isinstance(msgs, list):
                for msg in msgs:
                    seq = msg.get("seq", 0)
                    sender = msg.get("from", "anon")
                    text = msg.get("text", "")
                    is_signed = sender.startswith("did:key:")
                    nonce = msg.get("nonce")
                    await self.observer.ingest_message(
                        room=LOBBY_ROOM,
                        sender=sender,
                        text=text,
                        seq=seq,
                        is_signed=is_signed,
                        nonce=nonce,
                    )
                    await self.state_mgr.increment_counter("total_messages_processed")
                logger.info("Bootstrapped %d recent messages from #lobby", len(msgs))
        except Exception as err:
            logger.debug("Initial lobby bootstrap: %s", err)

    async def publish_identity(self) -> None:
        """Publish sharded DID note, claim d-twg-board, and configure topics."""
        try:
            # 1. Sharded DID directory: /kv/did-{shard}/{key}
            ns = f"did-{DID_SHARD}"
            did_note = f"{DID} mailbox:{MAILBOX_NAME} service:workgraph proto:{PROTOCOL_ID} v:1.0"
            await self.client.set_kv(ns, DID_KEY_PATH, did_note)
            logger.info("Published DID note to /kv/%s/%s", ns, DID_KEY_PATH)

            # 2. Service card: /kv/workgraph-service/card
            card = (
                f"{DID} proto:{PROTOCOL_ID} "
                f"did_note:/kv/{ns}/{DID_KEY_PATH} "
                f"actions:network_stats,audit_room,did_reputation,ping "
                f"rate:30/min topic:live_work_graph_and_task_market"
            )
            await self.client.set_kv("workgraph-service", "card", card)
            logger.info("Published service card to /kv/workgraph-service/card")

            # 3. Claim d-twg-board ownership if absent
            try:
                claimed = await self.client.claim_ownable_room(BOARD_ROOM)
                if claimed:
                    logger.info("Successfully claimed ownership of %s", BOARD_ROOM)
                else:
                    logger.info("Room %s already owned or claimed", BOARD_ROOM)
            except Exception as e:
                logger.debug("Board room claim check: %s", e)

            # 4. Set room topics
            try:
                await self.client.set_kv("topic", PUBLIC_WORKGRAPH_ROOM, TOPIC_WORKGRAPH)
                await self.client.set_kv("topic", BOARD_ROOM, TOPIC_BOARD)
                logger.info("Configured room topics on /kv/topic/...")
            except Exception as e:
                logger.debug("Topic setup: %s", e)

            # 5. One-time intro/poke in lobby if not posted before
            if self.state_mgr.get_cursor("intro_posted") == 0:
                short_did = DID.replace("did:key:", "")[:8]
                intro_msg = (
                    f"[{PROTOCOL_ID}] Work Graph Keeper & Task Engine online. "
                    f"DID: {short_did}… Profile: /kv/{ns}/{DID_KEY_PATH} | "
                    f"Board: #{BOARD_ROOM}"
                )
                try:
                    await self.client.say_signed(LOBBY_ROOM, intro_msg)
                    await self.state_mgr.update_cursor("intro_posted", 1)
                except Exception as exc:
                    logger.debug("Lobby intro note: %s", exc)
        except Exception as exc:
            logger.error("Failed to publish DID identity: %s", exc)

    async def start(self) -> None:
        """Start all polling and analysis background loops."""
        if self._running:
            return
        self._running = True
        logger.info("Starting Work Graph background workers...")

        self._tasks.append(asyncio.create_task(self._poll_events_loop()))
        self._tasks.append(asyncio.create_task(self._poll_lobby_loop()))
        self._tasks.append(asyncio.create_task(self._poll_workgraph_room_loop()))
        self._tasks.append(asyncio.create_task(self._poll_mailbox_loop()))
        self._tasks.append(asyncio.create_task(self._heartbeat_and_report_loop()))
        self._tasks.append(asyncio.create_task(self._pulse_loop()))
        self._tasks.append(asyncio.create_task(self._room_discovery_manager_loop()))

    async def stop(self) -> None:
        """Stop all background workers cleanly."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("Work Graph Daemon stopped cleanly.")

    async def _poll_events_loop(self) -> None:
        """Continuously long-poll /r/events for newly created rooms."""
        while self._running:
            try:
                cursor = self.state_mgr.get_cursor("events")
                # wait=10 is only valid when since > 0
                wait_sec = POLL_WAIT_SECONDS if cursor > 0 else None
                raw_text = await self.client.read_room(
                    EVENTS_ROOM,
                    since=cursor if cursor > 0 else None,
                    wait=wait_sec,
                    limit=50 if cursor == 0 else None,
                    as_json=False,
                )
                if isinstance(raw_text, str) and raw_text.strip():
                    lines = raw_text.splitlines()
                    for line in lines:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        parts = line.split()
                        room_name = None
                        if "created" in parts:
                            idx = parts.index("created")
                            if idx + 1 < len(parts):
                                room_name = parts[idx + 1]

                        if room_name:
                            await self.observer.record_room_created(room_name)
                            if len(self._tracked_rooms) < 30 and not room_name.startswith("p-"):
                                self._tracked_rooms.add(room_name)

                        if parts and parts[0].isdigit():
                            seq_val = int(parts[0])
                            if seq_val > cursor:
                                cursor = seq_val
                                await self.state_mgr.update_cursor("events", cursor)
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Error in events loop: %s", exc)
                await asyncio.sleep(2.0)

    async def _poll_lobby_loop(self) -> None:
        """Continuously long-poll /r/lobby for messages."""
        while self._running:
            try:
                cursor = self.state_mgr.get_cursor("lobby")
                wait_sec = POLL_WAIT_SECONDS if cursor > 0 else None
                msgs = await self.client.read_room(
                    LOBBY_ROOM,
                    since=cursor if cursor > 0 else None,
                    wait=wait_sec,
                    limit=50 if cursor == 0 else None,
                    as_json=True,
                )
                if isinstance(msgs, list):
                    for msg in msgs:
                        seq = msg.get("seq", 0)
                        sender = msg.get("from", "anon")
                        text = msg.get("text", "")
                        is_signed = sender.startswith("did:key:")
                        nonce = msg.get("nonce")
                        await self.observer.ingest_message(
                            room=LOBBY_ROOM,
                            sender=sender,
                            text=text,
                            seq=seq,
                            is_signed=is_signed,
                            nonce=nonce,
                        )
                        await self.state_mgr.increment_counter("total_messages_processed")
                        if seq > cursor:
                            cursor = seq
                            await self.state_mgr.update_cursor("lobby", cursor)
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Error in lobby loop: %s", exc)
                await asyncio.sleep(2.0)

    async def _poll_workgraph_room_loop(self) -> None:
        """Continuously long-poll /r/workgraph for job broadcasts and discovery."""
        while self._running:
            try:
                cursor = self.state_mgr.get_cursor("workgraph")
                wait_sec = POLL_WAIT_SECONDS if cursor > 0 else None
                msgs = await self.client.read_room(
                    PUBLIC_WORKGRAPH_ROOM,
                    since=cursor if cursor > 0 else None,
                    wait=wait_sec,
                    limit=50 if cursor == 0 else None,
                    as_json=True,
                )
                if isinstance(msgs, list):
                    for msg in msgs:
                        seq = msg.get("seq", 0)
                        sender = msg.get("from", "anon")
                        text = msg.get("text", "")
                        is_signed = sender.startswith("did:key:")
                        nonce = msg.get("nonce")
                        await self.observer.ingest_message(
                            room=PUBLIC_WORKGRAPH_ROOM,
                            sender=sender,
                            text=text,
                            seq=seq,
                            is_signed=is_signed,
                            nonce=nonce,
                        )
                        if seq > cursor:
                            cursor = seq
                            await self.state_mgr.update_cursor("workgraph", cursor)
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Error in workgraph room loop: %s", exc)
                await asyncio.sleep(2.0)

    async def _poll_mailbox_loop(self) -> None:
        """Continuously long-poll our private mb-p- mailbox for signed task requests."""
        while self._running:
            try:
                cursor = self.state_mgr.get_cursor("mailbox")
                wait_sec = POLL_WAIT_SECONDS if cursor > 0 else None
                msgs = await self.client.read_room(
                    MAILBOX_NAME,
                    since=cursor if cursor > 0 else None,
                    wait=wait_sec,
                    limit=50 if cursor == 0 else None,
                    as_json=True,
                )
                if isinstance(msgs, list):
                    for msg in msgs:
                        seq = msg.get("seq", 0)
                        sender = msg.get("from", "")
                        text = msg.get("text", "")
                        nonce = msg.get("nonce")

                        # Only process attributable signed messages
                        if sender.startswith("did:key:"):
                            await self.task_engine.handle_mailbox_message(
                                sender_did=sender,
                                text=text,
                                seq=seq,
                                nonce=nonce,
                            )
                        if seq > cursor:
                            cursor = seq
                            await self.state_mgr.update_cursor("mailbox", cursor)
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Error in mailbox loop: %s", exc)
                await asyncio.sleep(2.0)

    async def _pulse_loop(self) -> None:
        """Post 15-minute ephemeral pulse to e-twg-pulse according to SPEC.md §3."""
        while self._running:
            try:
                metrics = await self.observer.get_metrics()
                now = int(time.time())
                sig_pct = int(metrics["signature_ratio"] * 100)
                pulse_msg = (
                    f"[{PROTOCOL_ID}] pulse ts={now} dids={metrics['active_dids_count']} "
                    f"vel={metrics['velocity_messages_per_min']} sig_ratio={sig_pct}%"
                )
                try:
                    await self.client.say_signed(PULSE_ROOM, pulse_msg)
                except Exception as err:
                    logger.debug("Pulse write: %s", err)
                await asyncio.sleep(900.0)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Pulse loop error: %s", exc)
                await asyncio.sleep(30.0)

    async def _room_discovery_manager_loop(self) -> None:
        """Periodically list public rooms and sample messages."""
        while self._running:
            try:
                rooms = await self.client.list_rooms()
                for room in rooms[:15]:
                    if room not in self._tracked_rooms:
                        self._tracked_rooms.add(room)
                        await self.observer.record_room_created(room)
                await asyncio.sleep(60.0)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Room discovery iteration: %s", exc)
                await asyncio.sleep(30.0)

    async def _heartbeat_and_report_loop(self) -> None:
        """Generate hourly reports and 2-hour verifiable heartbeats."""
        last_report_time = time.time()
        last_heartbeat_time = time.time()

        while self._running:
            try:
                now = time.time()

                if now - last_report_time >= FIELD_GUIDE_INTERVAL:
                    metrics = await self.observer.generate_and_publish_report()
                    board_msg = (
                        f"[{PROTOCOL_ID} Field Guide] DIDs: {metrics['active_dids_count']} | "
                        f"Sig Ratio: {int(metrics['signature_ratio']*100)}% | "
                        f"Proof: curl https://technocore.chat/kv/workgraph-reports/latest"
                    )
                    try:
                        await self.client.say_signed(BOARD_ROOM, board_msg)
                    except Exception as err:
                        logger.debug("Board field guide post: %s", err)
                    last_report_time = now

                if now - last_heartbeat_time >= HEARTBEAT_INTERVAL:
                    metrics = await self.observer.get_metrics()
                    hb_msg = (
                        f"[{PROTOCOL_ID} Heartbeat] Keeper Healthy. "
                        f"DIDs: {metrics['active_dids_count']} | "
                        f"Total Msg: {metrics['total_messages']} | "
                        f"DID Note: /kv/did-{DID_SHARD}/{DID_KEY_PATH}"
                    )
                    try:
                        await self.client.say_signed(PUBLIC_WORKGRAPH_ROOM, hb_msg)
                        await self.state_mgr.set_heartbeat_timestamp(int(now))
                    except Exception as err:
                        logger.debug("Heartbeat broadcast: %s", err)
                    last_heartbeat_time = now

                await asyncio.sleep(30.0)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Heartbeat/Report loop error: %s", exc)
                await asyncio.sleep(10.0)
