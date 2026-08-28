"""Mailbox Task Engine for Technocore Work Graph (twg1 protocol).

Processes inbound signed job requests from other agents via our private mailbox (mb-p-...).
Executes requested analysis (network stats, room audit, DID reputation, proof verification),
generates verifiable signed proof notes on Technocore /kv, and replies to the requester.
Enforces SPEC.md v0.1 input allow-list rules (technocore URLs, room names, note keys).
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from typing import Any, Dict, Optional

from client import TechnocoreClient
from observer import NetworkObserver
from state import StateManager
from config import PROOFS_NS, DID, PROTOCOL_ID

logger = logging.getLogger("workgraph.tasks")


class TaskEngine:
    """Processes signed tasks received in our mailbox according to twg1 SPEC.md."""

    def __init__(
        self,
        client: TechnocoreClient,
        observer: NetworkObserver,
        state_mgr: StateManager,
    ) -> None:
        self.client = client
        self.observer = observer
        self.state_mgr = state_mgr
        self._lock = asyncio.Lock()
        self.completed_tasks: Dict[str, Dict[str, Any]] = {}

    def _validate_input_target(self, target: Optional[str]) -> bool:
        """Enforce SPEC.md §2 allow-list on worker inputs."""
        if not target:
            return True
        # Allow-list: room names, note paths, technocore URLs, did:key
        if target.startswith("https://technocore.chat/"):
            return True
        if target.startswith("room:") or target.startswith("note:"):
            return True
        if target.startswith("did:key:"):
            return True
        # Alphanumeric room/user names
        if target.replace("-", "").replace("_", "").isalnum():
            return True
        return False

    def _parse_task_payload(self, text: str) -> Optional[Dict[str, Any]]:
        """Parse structured JSON or command-line style task payloads."""
        text = text.strip()
        # Try JSON first
        if text.startswith("{") and text.endswith("}"):
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

        # Try slash / exclamation commands
        if text.startswith("!") or text.startswith("/"):
            parts = text[1:].split()
            if not parts:
                return None
            cmd = parts[0].lower()
            target = parts[1] if len(parts) > 1 else None
            return {"action": cmd, "target": target}

        return None

    async def handle_mailbox_message(
        self,
        sender_did: str,
        text: str,
        seq: int,
        nonce: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Process a verified message from our private mb-p- mailbox."""
        payload = self._parse_task_payload(text)
        if not payload:
            logger.debug("Ignored unparseable mailbox message from %s: %s", sender_did, text)
            return None

        action = payload.get("action", "").lower()
        target = payload.get("target")
        reply_to = payload.get("reply_to")
        job_id = f"job-{secrets.token_hex(6)}"
        now = int(time.time())

        # Validate input against SSRF / malicious paths
        if not self._validate_input_target(target):
            logger.warning("Rejected task with non-allowlisted target: %s", target)
            return None

        logger.info("Executing %s job %s (%s) for %s", PROTOCOL_ID, job_id, action, sender_did)

        # Execute requested action
        result_data: Dict[str, Any] = {}
        if action in ("stats", "network_stats", "ping"):
            metrics = await self.observer.get_metrics()
            result_data = {
                "status": "success",
                "active_dids": metrics["active_dids_count"],
                "total_messages": metrics["total_messages"],
                "signature_ratio": metrics["signature_ratio"],
                "velocity_ppm": metrics["velocity_messages_per_min"],
                "protocol": PROTOCOL_ID,
            }
        elif action in ("audit_room", "audit"):
            room_name = (target or "lobby").replace("room:", "")
            room_node = self.observer.nodes.get(f"room:{room_name}")
            msg_count = room_node["data"]["msg_count"] if room_node else 0
            result_data = {
                "status": "success",
                "room": room_name,
                "tracked_messages": msg_count,
                "is_active": room_node is not None,
                "protocol": PROTOCOL_ID,
            }
        elif action in ("did_reputation", "did_lookup", "did"):
            did_query = target or sender_did
            agent_node = self.observer.nodes.get(f"did:{did_query}")
            if agent_node:
                sdata = agent_node["data"]
                result_data = {
                    "status": "success",
                    "did": did_query,
                    "msg_count": sdata.get("msg_count", 0),
                    "signed_count": sdata.get("signed_count", 0),
                    "reputation_score": min(100, sdata.get("signed_count", 0) * 10),
                    "protocol": PROTOCOL_ID,
                }
            else:
                result_data = {
                    "status": "not_found",
                    "did": did_query,
                    "reputation_score": 0,
                    "protocol": PROTOCOL_ID,
                }
        else:
            result_data = {
                "status": "unknown_action",
                "supported_actions": ["stats", "audit_room", "did_reputation", "ping"],
                "protocol": PROTOCOL_ID,
            }

        proof_record = {
            "proto": PROTOCOL_ID,
            "job_id": job_id,
            "requester": sender_did,
            "executor": DID,
            "action": action,
            "target": target,
            "completed_at": now,
            "result": result_data,
        }

        # Store in local memory
        async with self._lock:
            self.completed_tasks[job_id] = proof_record
            await self.state_mgr.increment_counter("total_tasks_completed")

        # Persist proof to Technocore KV as a verifiable public proof note
        proof_json = json.dumps(proof_record)
        try:
            await self.client.set_kv(PROOFS_NS, job_id, proof_json)
            logger.info("Published %s proof %s to /kv/%s/%s", PROTOCOL_ID, job_id, PROOFS_NS, job_id)
        except Exception as exc:
            logger.warning("Failed to store proof note on KV: %s", exc)

        # Send response to requester if reply_to specified (SPEC.md: signed response)
        if reply_to and isinstance(reply_to, str):
            reply_msg = (
                f"[{PROTOCOL_ID} Receipt] Job {job_id} completed. Status: {result_data.get('status')}. "
                f"Proof: curl https://technocore.chat/kv/{PROOFS_NS}/{job_id}"
            )
            try:
                await self.client.say_signed(reply_to, reply_msg)
            except Exception as err:
                logger.warning("Failed to deliver receipt to %s: %s", reply_to, err)

        return proof_record
