"""Autonomous Observe Worker according to SPEC.md §6.3."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import Counter
from typing import Any, Dict

from src.twg.http import TechnocoreHTTP
from src.twg.keys import get_did_shard
from src.twg.proto import (
    make_bid,
    make_deliver,
    parse_twg_line,
)
from src.twg.store import TwgStore

logger = logging.getLogger("twg.worker")


class ObserveWorker:
    """Worker agent that bids on kind=observe jobs, performs analysis, and delivers outputs."""

    def __init__(self, http: TechnocoreHTTP, store: TwgStore, mailbox: str) -> None:
        self.http = http
        self.store = store
        self.mailbox = mailbox
        self.did = http.did or ""
        self.fp16, self.shard, self.key_path = get_did_shard(self.did)
        self.running = False

    async def initialize(self) -> None:
        """Register worker capability in /kv/twg-agents/<fp16>."""
        logger.info("Initializing Observe Worker for DID %s", self.did)
        await self.store.register_agent(
            fp16=self.fp16,
            did=self.did,
            mailbox=self.mailbox,
            svc=["observe"],
            max_in=4,
            sla_s=120,
        )

    async def start(self) -> None:
        """Start worker mailbox polling loop."""
        self.running = True
        asyncio.create_task(self._poll_mailbox_loop())

    async def stop(self) -> None:
        self.running = False

    async def _poll_mailbox_loop(self) -> None:
        """Listen to our mailbox for poke or accept messages."""
        cursor = 0
        while self.running:
            try:
                msgs = await self.http.read_room(
                    self.mailbox,
                    since=cursor if cursor > 0 else None,
                    wait=10,
                    as_json=True,
                )
                if isinstance(msgs, list):
                    for msg in msgs:
                        seq = msg.get("seq", 0)
                        sender = msg.get("from", "")
                        text = msg.get("text", "")
                        if sender.startswith("did:key:"):
                            await self._handle_inbound(sender, text)
                        if seq > cursor:
                            cursor = seq
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Worker mailbox error: %s", exc)
                await asyncio.sleep(2.0)

    async def _handle_inbound(self, sender: str, text: str) -> None:
        """Handle incoming twg1 messages."""
        msg = parse_twg_line(text)
        if not msg:
            return

        if msg.verb == "accept":
            # twg1 accept <job_id> worker=<did> room=<p-room>
            job_id = msg.args[0] if msg.args else None
            worker = msg.kwargs.get("worker")
            room = msg.kwargs.get("room")
            if job_id and worker == self.did and room:
                await self.execute_and_deliver(job_id, room)

        elif msg.verb == "poke":
            # Check if there are open jobs we can bid on
            pass

    async def evaluate_and_bid(self, job_record: Dict[str, Any], poster_mailbox: str) -> bool:
        """Bid on an open observe job if input is allowlisted."""
        if job_record.get("kind") != "observe":
            return False

        input_target = job_record.get("in", "")
        # Allowlist check: room:..., https://technocore.chat/...
        if not (input_target.startswith("room:") or input_target.startswith("https://technocore.chat/")):
            logger.warning("Rejected non-allowlisted job input: %s", input_target)
            return False

        job_id = job_record["id"]
        bid_line = make_bid(job_id, eta=30, conf=0.9)

        # Send bid to job poster's mailbox
        try:
            await self.http.say_signed(poster_mailbox, bid_line)
            # Also record in job store CAS
            await self.store.append_bid(job_id, self.did, eta=30, conf=0.9)
            logger.info("Placed bid on job %s -> %s", job_id, poster_mailbox)
            return True
        except Exception as exc:
            logger.warning("Failed to deliver bid: %s", exc)
            return False

    async def execute_and_deliver(self, job_id: str, delivery_room: str) -> None:
        """Fetch input, analyze, write out note, and deliver."""
        job = await self.store.get_job(job_id)
        if not job:
            return

        input_target = job.get("in", "room:lobby")
        room_to_read = input_target.replace("room:", "")

        logger.info("Executing observe job %s for target %s", job_id, room_to_read)

        # Fetch last 50 messages from target room
        msgs = await self.http.read_room(room_to_read, limit=50, as_json=True)
        total_n = len(msgs) if isinstance(msgs, list) else 0
        signed_n = 0
        nicks: set[str] = set()
        words: list[str] = []

        if isinstance(msgs, list):
            for m in msgs:
                sender = m.get("from", "anon")
                if sender.startswith("did:key:"):
                    signed_n += 1
                else:
                    nicks.add(sender)
                for w in m.get("text", "").lower().split():
                    if len(w) > 3:
                        words.append(w)

        top_topics = [w for w, _ in Counter(words).most_common(3)]
        top_str = ",".join(top_topics) if top_topics else "general"

        # SPEC.md §6.3 format:
        # observe room=lobby n=50 signed=11 nicks=29 pulse=high top=airdrop,did,checkin
        pulse_level = "high" if total_n > 30 else "medium" if total_n > 10 else "low"
        out_text = (
            f"observe room={room_to_read} n={total_n} signed={signed_n} "
            f"nicks={len(nicks)} pulse={pulse_level} top={top_str}"
        )
        sha256_hex = hashlib.sha256(out_text.encode("utf-8")).hexdigest()

        # Write out note and deliver
        await self.store.deliver_job(job_id, sha256_hex, out_text)

        deliver_line = make_deliver(job_id, sha256_hex, f"twg-jobs/{job_id}-out")
        try:
            await self.http.say_signed(delivery_room, deliver_line)
            logger.info("Delivered job %s to %s", job_id, delivery_room)
        except Exception as exc:
            logger.error("Failed to deliver line to %s: %s", delivery_room, exc)
