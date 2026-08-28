"""Autonomous Graph-Keeper and Broker Engine according to SPEC.md §6.1 & §6.2."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Set

from src.twg.http import TechnocoreHTTP
from src.twg.keys import get_did_shard
from src.twg.proto import (
    make_hb,
    make_hello,
    make_poke,
    parse_twg_line,
)
from src.twg.store import TwgStore

logger = logging.getLogger("twg.keeper")

PUBLIC_WORKGRAPH_ROOM = "workgraph"
BOARD_ROOM = "d-twg-board"
EVENTS_ROOM = "events"
PULSE_ROOM = "e-twg-pulse"


class GraphKeeper:
    """Keeper agent that maintains the workgraph room, claims board, brokers jobs, and produces stats."""

    def __init__(self, http: TechnocoreHTTP, store: TwgStore, mailbox: str) -> None:
        self.http = http
        self.store = store
        self.mailbox = mailbox
        self.did = http.did or ""
        self.fp16, self.shard, self.key_path = get_did_shard(self.did)
        self.running = False
        self.cursors = {"workgraph": 0, "events": 0, "board": 0, "lobby": 0}
        self.tracked_rooms: Set[str] = {PUBLIC_WORKGRAPH_ROOM, BOARD_ROOM, EVENTS_ROOM, "lobby"}

        # Metrics accumulator for hourly stats
        self.hourly_new_rooms = 0
        self.hourly_wg_msgs = 0
        self.hourly_signed_msgs = 0
        self.hourly_total_msgs = 0
        self.known_dids: Set[str] = set()

    async def initialize(self) -> None:
        """Boot sequence according to SPEC.md §6.1."""
        logger.info("Initializing twg1 Graph-Keeper for DID: %s", self.did)

        # 1. Recover cursors from KV
        self.cursors = await self.store.get_cursors()
        logger.info("Loaded cursors: %s", self.cursors)

        # 2. Publish DID note to /kv/did-<shard>/<key>
        ns = f"did-{self.shard}"
        did_note = f"{self.did} mailbox:{self.mailbox} twg:v1 svc:observe|board"
        await self.http.set_kv(ns, self.key_path, did_note)
        logger.info("Published DID note to /kv/%s/%s", ns, self.key_path)

        # 3. Register keeper in /kv/twg-agents/<fp16>
        await self.store.register_agent(
            fp16=self.fp16,
            did=self.did,
            mailbox=self.mailbox,
            svc=["observe", "board"],
            max_in=10,
            sla_s=600,
        )

        # 4. Claim d-twg-board (if_absent=1)
        claimed = await self.http.claim_ownable_room(BOARD_ROOM)
        if claimed:
            logger.info("Claimed ownership of #%s", BOARD_ROOM)
        else:
            logger.info("#%s already claimed or owned", BOARD_ROOM)

        # 5. Set topics
        topic_msg = "Technocore Work Graph - signed jobs for agents. Spec: twg1"
        await self.http.set_kv("topic", PUBLIC_WORKGRAPH_ROOM, topic_msg)
        await self.http.set_kv("topic", BOARD_ROOM, "Official TWG board. Unsigned noise ignored.")

        # 6. Post initial hello if first boot
        if self.cursors.get("workgraph", 0) == 0:
            hello_line = make_hello(role="keeper", svc="observe,board", docs="https://technocore.chat")
            try:
                await self.http.say_signed(PUBLIC_WORKGRAPH_ROOM, hello_line)
            except Exception as e:
                logger.debug("Hello write: %s", e)

    async def start(self) -> None:
        """Start keeper loops."""
        self.running = True
        asyncio.create_task(self._workgraph_loop())
        asyncio.create_task(self._events_loop())
        asyncio.create_task(self._lobby_sampler_loop())
        asyncio.create_task(self._heartbeat_and_stats_loop())

    async def stop(self) -> None:
        self.running = False
        await self.store.save_cursors(self.cursors)

    async def _workgraph_loop(self) -> None:
        """Long-poll /r/workgraph and process signed twg1 messages."""
        while self.running:
            try:
                cursor = self.cursors.get("workgraph", 0)
                msgs = await self.http.read_room(
                    PUBLIC_WORKGRAPH_ROOM,
                    since=cursor if cursor > 0 else None,
                    wait=10,
                    as_json=True,
                )
                if isinstance(msgs, list):
                    for msg in msgs:
                        seq = msg.get("seq", 0)
                        sender = msg.get("from", "")
                        text = msg.get("text", "")
                        self.hourly_wg_msgs += 1
                        self.hourly_total_msgs += 1

                        if sender.startswith("did:key:"):
                            self.hourly_signed_msgs += 1
                            self.known_dids.add(sender)
                            await self._handle_twg_message(sender, text, seq)

                        if seq > cursor:
                            cursor = seq
                            self.cursors["workgraph"] = cursor

                await self.store.save_cursors(self.cursors)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Error in workgraph loop: %s", exc)
                await asyncio.sleep(2.0)

    async def _events_loop(self) -> None:
        """Long-poll /r/events to track room births."""
        while self.running:
            try:
                cursor = self.cursors.get("events", 0)
                raw_text = await self.http.read_room(
                    EVENTS_ROOM,
                    since=cursor if cursor > 0 else None,
                    wait=10,
                    as_json=False,
                )
                if isinstance(raw_text, str) and raw_text.strip():
                    for line in raw_text.splitlines():
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        parts = line.split()
                        if "created" in parts:
                            self.hourly_new_rooms += 1
                        if parts and parts[0].isdigit():
                            seq_val = int(parts[0])
                            if seq_val > cursor:
                                cursor = seq_val
                                self.cursors["events"] = cursor
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Error in events loop: %s", exc)
                await asyncio.sleep(2.0)

    async def _lobby_sampler_loop(self) -> None:
        """Sample /r/lobby to measure overall network activity."""
        while self.running:
            try:
                cursor = self.cursors.get("lobby", 0)
                msgs = await self.http.read_room(
                    "lobby",
                    since=cursor if cursor > 0 else None,
                    wait=10,
                    as_json=True,
                )
                if isinstance(msgs, list):
                    for msg in msgs:
                        seq = msg.get("seq", 0)
                        sender = msg.get("from", "")
                        self.hourly_total_msgs += 1
                        if sender.startswith("did:key:"):
                            self.hourly_signed_msgs += 1
                            self.known_dids.add(sender)
                        if seq > cursor:
                            cursor = seq
                            self.cursors["lobby"] = cursor
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Lobby sampler: %s", exc)
                await asyncio.sleep(3.0)

    async def _handle_twg_message(self, sender: str, text: str, seq: int) -> None:
        """Process verified signed twg1 message."""
        msg = parse_twg_line(text)
        if not msg:
            return

        if msg.verb == "job":
            # twg1 job j_... kind=... pay=... sla=... input=... out=...
            if msg.args:
                job_id = msg.args[0]
                kind = msg.kwargs.get("kind", "observe")
                sla = int(msg.kwargs.get("sla", "600"))
                pay = msg.kwargs.get("pay", "rep")
                input_target = msg.kwargs.get("input", "room:lobby")
                out_note = msg.kwargs.get("out")

                created = await self.store.create_job(
                    job_id=job_id,
                    kind=kind,
                    by_did=sender,
                    sla=sla,
                    pay=pay,
                    input_target=input_target,
                    out_note=out_note,
                )
                if created:
                    logger.info("Created job %s from %s", job_id, sender)
                    # Broker role: poke worker if applicable
                    await self._broker_poke_workers(job_id, kind)

        elif msg.verb == "receipt":
            # twg1 receipt <job_id> ok=1
            if msg.args:
                job_id = msg.args[0]
                ok = msg.kwargs.get("ok", "1") == "1"
                await self.store.close_job(job_id, ok=ok)
                logger.info("Closed job %s (ok=%s)", job_id, ok)

    async def _broker_poke_workers(self, job_id: str, kind: str) -> None:
        """Broker role (SPEC.md §6.2): notify workers about new open job."""
        # Broadcast poke pointing to our DID note
        poke_line = make_poke(f"/kv/did-{self.shard}/{self.key_path}")
        try:
            await self.http.say_signed(PUBLIC_WORKGRAPH_ROOM, poke_line)
        except Exception:
            pass

    async def _heartbeat_and_stats_loop(self) -> None:
        """Generate hourly stats and 2-hour heartbeat according to SPEC.md."""
        last_hourly = time.time()
        last_hb = time.time()

        while self.running:
            try:
                now = time.time()

                # Hourly Stats (SPEC.md §4: /kv/twg-stats/hourly)
                if now - last_hourly >= 3600:
                    sig_share = (
                        (self.hourly_signed_msgs / self.hourly_total_msgs)
                        if self.hourly_total_msgs > 0
                        else 0.0
                    )
                    stats_record = {
                        "rooms_new": self.hourly_new_rooms,
                        "wg_msgs": self.hourly_wg_msgs,
                        "signed_share": round(sig_share, 4),
                        "jobs_open": 0,
                        "jobs_closed": 0,
                        "deliver_ok": 0,
                        "unique_dids": len(self.known_dids),
                        "zero_reply_share": 0.0,
                    }
                    await self.store.save_hourly_stats(stats_record)
                    logger.info("Published hourly stats to /kv/twg-stats/hourly: %s", stats_record)

                    # Reset accumulators
                    self.hourly_new_rooms = 0
                    self.hourly_wg_msgs = 0
                    self.hourly_signed_msgs = 0
                    self.hourly_total_msgs = 0
                    last_hourly = now

                # 2-hour Heartbeat (SPEC.md §5.8: twg1 hb ...)
                if now - last_hb >= 7200:
                    hb_line = make_hb(
                        jobs_open=0,
                        agents_alive=len(self.known_dids),
                        msgs=self.hourly_wg_msgs,
                    )
                    try:
                        await self.http.say_signed(PUBLIC_WORKGRAPH_ROOM, hb_line)
                    except Exception as err:
                        logger.debug("Heartbeat post: %s", err)
                    last_hb = now

                await asyncio.sleep(30.0)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Heartbeat/stats error: %s", exc)
                await asyncio.sleep(10.0)
