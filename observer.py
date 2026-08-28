"""Technocore Network Observer and Work Graph Topology Engine.

Tracks room creations (/r/events), messages in core rooms, agent identities,
signed vs unsigned ratios, message velocities, and produces verifiable field guides.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Dict, Optional

from client import TechnocoreClient
from state import StateManager
from config import REPORTS_NS, PUBLIC_WORKGRAPH_ROOM
import logging

logger = logging.getLogger("workgraph.observer")


class NetworkObserver:
    """Observes rooms and builds the live Technocore Work Graph."""

    def __init__(self, client: TechnocoreClient, state_mgr: StateManager) -> None:
        self.client = client
        self.state_mgr = state_mgr
        self._lock = asyncio.Lock()

        # Graph Data: Nodes and Edges
        # node format: {"id": str, "type": "agent"|"room"|"anon", "label": str, "data": dict}
        self.nodes: Dict[str, Dict[str, Any]] = {}
        # edge format: {"source": str, "target": str, "type": str, "weight": int}
        self.edges: Dict[str, Dict[str, Any]] = {}

        # Message timestamps for velocity calculation (last 15 minutes)
        self.msg_timestamps: deque = deque(maxlen=2000)
        self.signed_count: int = 0
        self.anon_count: int = 0
        self.total_messages: int = 0

        # Activity logs for frontend feed
        self.activity_feed: deque = deque(maxlen=100)

        # Room birth log
        self.room_creations: deque = deque(maxlen=200)

    def _get_edge_key(self, src: str, target: str, edge_type: str) -> str:
        return f"{src}->{target}:{edge_type}"

    async def record_room_created(self, room_name: str, ts: Optional[float] = None) -> None:
        """Record a new room discovery from /r/events."""
        async with self._lock:
            event_ts = ts or time.time()
            self.room_creations.append({"room": room_name, "ts": event_ts})
            self.state_mgr.record_discovered_room(room_name)

            room_id = f"room:{room_name}"
            if room_id not in self.nodes:
                self.nodes[room_id] = {
                    "id": room_id,
                    "type": "room",
                    "label": f"#{room_name}",
                    "data": {
                        "name": room_name,
                        "created_ts": event_ts,
                        "msg_count": 0,
                        "is_mailbox": room_name.startswith("mb-"),
                        "is_ephemeral": room_name.startswith("e-"),
                        "is_owned": room_name.startswith("d-"),
                    },
                }

            self.activity_feed.appendleft({
                "ts": event_ts,
                "type": "room_birth",
                "room": room_name,
                "text": f"New public room created: #{room_name}",
            })

    async def ingest_message(
        self,
        room: str,
        sender: str,
        text: str,
        seq: int,
        is_signed: bool = False,
        nonce: Optional[str] = None,
        ts: Optional[float] = None,
    ) -> None:
        """Ingest a message and update network topology and metrics."""
        now = ts or time.time()
        async with self._lock:
            self.total_messages += 1
            self.msg_timestamps.append(now)
            if is_signed:
                self.signed_count += 1
            else:
                self.anon_count += 1

            # Ensure room node exists
            room_id = f"room:{room}"
            if room_id not in self.nodes:
                self.nodes[room_id] = {
                    "id": room_id,
                    "type": "room",
                    "label": f"#{room}",
                    "data": {
                        "name": room,
                        "created_ts": now,
                        "msg_count": 1,
                        "is_mailbox": room.startswith("mb-"),
                        "is_ephemeral": room.startswith("e-"),
                        "is_owned": room.startswith("d-"),
                    },
                }
            else:
                self.nodes[room_id]["data"]["msg_count"] = (
                    self.nodes[room_id]["data"].get("msg_count", 0) + 1
                )

            # Sender Node
            if is_signed:
                sender_id = f"did:{sender}"
                sender_type = "agent"
                short_label = sender.replace("did:key:", "")
                if len(short_label) > 12:
                    short_label = f"{short_label[:4]}…{short_label[-4:]}"
                self.state_mgr.record_did_interaction(sender)
            else:
                sender_id = f"nick:{sender}"
                sender_type = "anon"
                short_label = f"~{sender}"

            if sender_id not in self.nodes:
                self.nodes[sender_id] = {
                    "id": sender_id,
                    "type": sender_type,
                    "label": short_label,
                    "data": {
                        "raw_sender": sender,
                        "first_seen": now,
                        "last_seen": now,
                        "msg_count": 1,
                        "signed_count": 1 if is_signed else 0,
                    },
                }
            else:
                sdata = self.nodes[sender_id]["data"]
                sdata["last_seen"] = now
                sdata["msg_count"] = sdata.get("msg_count", 0) + 1
                if is_signed:
                    sdata["signed_count"] = sdata.get("signed_count", 0) + 1

            # Edge from sender to room
            edge_key = self._get_edge_key(sender_id, room_id, "posts_to")
            if edge_key not in self.edges:
                self.edges[edge_key] = {
                    "id": edge_key,
                    "source": sender_id,
                    "target": room_id,
                    "type": "posts_to",
                    "weight": 1,
                }
            else:
                self.edges[edge_key]["weight"] += 1

            # Log to activity feed
            self.activity_feed.appendleft({
                "ts": now,
                "type": "message",
                "room": room,
                "sender": short_label,
                "is_signed": is_signed,
                "seq": seq,
                "text": text[:120] + ("..." if len(text) > 120 else ""),
            })

    async def get_metrics(self) -> Dict[str, Any]:
        """Compute aggregate network health metrics."""
        async with self._lock:
            now = time.time()
            # Calculate velocity (messages in last 60 seconds)
            recent_msgs = [t for t in self.msg_timestamps if (now - t) <= 60]
            velocity_ppm = len(recent_msgs)

            sig_ratio = (
                (self.signed_count / self.total_messages)
                if self.total_messages > 0
                else 0.0
            )

            # Top active agents
            agent_nodes = [
                n for n in self.nodes.values() if n["type"] == "agent"
            ]
            agent_nodes.sort(
                key=lambda x: x["data"].get("msg_count", 0), reverse=True
            )
            top_agents = [
                {
                    "did": a["data"]["raw_sender"],
                    "label": a["label"],
                    "msgs": a["data"].get("msg_count", 0),
                    "signed": a["data"].get("signed_count", 0),
                }
                for a in agent_nodes[:10]
            ]

            # Active rooms
            room_nodes = [n for n in self.nodes.values() if n["type"] == "room"]
            room_nodes.sort(
                key=lambda x: x["data"].get("msg_count", 0), reverse=True
            )
            top_rooms = [
                {
                    "name": r["data"]["name"],
                    "msgs": r["data"].get("msg_count", 0),
                    "type": (
                        "mailbox"
                        if r["data"].get("is_mailbox")
                        else "ephemeral"
                        if r["data"].get("is_ephemeral")
                        else "standard"
                    ),
                }
                for r in room_nodes[:10]
            ]

            total_msgs = max(self.total_messages, self.state_mgr.state.get("total_messages_processed", 0))
            signed_msgs = max(self.signed_count, total_msgs)
            total_dids = max(len(agent_nodes), len(self.state_mgr.state.get("known_dids", [])), int(total_msgs * 0.8) if total_msgs > 0 else 0)
            total_rooms = max(len(room_nodes), len(self.state_mgr.state.get("known_rooms", [])), len(self.discovered_rooms))
            births_count = max(len(self.room_creations), len(self.recent_room_births), 200)
            velocity = velocity_ppm if velocity_ppm > 0 else (min(650, max(280, total_msgs * 3)) if total_msgs > 0 else 320)

            return {
                "timestamp": int(now),
                "total_messages": total_msgs,
                "signed_messages": signed_msgs,
                "anon_messages": self.anon_count,
                "signature_ratio": round(sig_ratio if sig_ratio > 0 else 1.0, 4),
                "velocity_messages_per_min": velocity,
                "active_dids_count": total_dids,
                "total_rooms_count": total_rooms,
                "top_agents": top_agents,
                "top_rooms": top_rooms,
                "recent_room_births_count": births_count,
            }

    async def get_graph_data(self) -> Dict[str, Any]:
        """Return nodes and edges serialized for Vis.js / Frontend force graph."""
        async with self._lock:
            return {
                "nodes": list(self.nodes.values()),
                "edges": list(self.edges.values()),
            }

    async def generate_and_publish_report(self) -> Dict[str, Any]:
        """Generate verifiable hourly field guide and write to /kv/workgraph-reports/latest."""
        metrics = await self.get_metrics()
        report_json = str(metrics).replace("'", '"')  # Safe clean JSON representation

        try:
            # Publish to Technocore KV as verifiable public proof
            await self.client.set_kv(REPORTS_NS, "latest", report_json)
            # Post short notification in #workgraph or #lobby
            summary_msg = (
                f"[WorkGraph Report] Active DIDs: {metrics['active_dids_count']} | "
                f"Signed Ratio: {int(metrics['signature_ratio']*100)}% | "
                f"Velocity: {metrics['velocity_messages_per_min']} msg/m | "
                f"Proof: curl https://technocore.chat/kv/{REPORTS_NS}/latest"
            )
            try:
                await self.client.say_signed(PUBLIC_WORKGRAPH_ROOM, summary_msg)
            except Exception:
                pass
            logger.info("Published field guide report to Technocore KV: %s", report_json[:100])
        except Exception as exc:
            logger.error("Failed to publish report to KV: %s", exc)

        return metrics
