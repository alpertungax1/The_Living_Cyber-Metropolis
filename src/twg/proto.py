"""Technocore Work Graph wire protocol (twg1) parser and formatter according to SPEC.md §5."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional

PROTO_PREFIX = "twg1"
KIND_ALLOWLIST = {"observe", "digest", "summarize", "match", "code"}
PAY_ALLOWLIST = {"rep"}
JOB_ID_REGEX = re.compile(r"^j_[a-f0-9]{6,12}$")


@dataclass
class TwgMessage:
    verb: str
    args: List[str]
    kwargs: Dict[str, str]
    raw: str


def parse_twg_line(text: str) -> Optional[TwgMessage]:
    """Parse a single-line message starting with 'twg1 '. Returns None if not twg1."""
    text = text.strip()
    if not text.startswith(PROTO_PREFIX + " "):
        return None

    parts = text.split()
    if len(parts) < 2:
        return None

    verb = parts[1].lower()
    args: List[str] = []
    kwargs: Dict[str, str] = {}

    for token in parts[2:]:
        if "=" in token:
            k, v = token.split("=", 1)
            kwargs[k] = v
        else:
            args.append(token)

    return TwgMessage(verb=verb, args=args, kwargs=kwargs, raw=text)


# ==================== BUILDERS ====================

def make_hello(role: str = "keeper", svc: str = "observe,board", docs: str = "https://technocore.chat") -> str:
    """twg1 hello keeper svc=observe,board docs=..."""
    return f"twg1 hello {role} svc={svc} docs={docs}"


def make_poke(did_note_path: str) -> str:
    """twg1 poke /kv/did-ab/cd1234567890ab"""
    return f"twg1 poke {did_note_path}"


def make_job(
    job_id: str,
    kind: str = "observe",
    pay: str = "rep",
    sla: int = 600,
    input_target: str = "room:lobby",
    out_note: Optional[str] = None,
) -> str:
    """twg1 job j_7k2p9c kind=observe pay=rep sla=600 input=room:lobby out=note:twg-jobs/j_7k2p9c-out"""
    out_path = out_note or f"note:twg-jobs/{job_id}-out"
    return f"twg1 job {job_id} kind={kind} pay={pay} sla={sla} input={input_target} out={out_path}"


def make_bid(job_id: str, eta: int = 90, conf: float = 0.8) -> str:
    """twg1 bid j_7k2p9c eta=90 conf=0.8"""
    return f"twg1 bid {job_id} eta={eta} conf={conf}"


def make_accept(job_id: str, worker_did: str, room: Optional[str] = None) -> str:
    """twg1 accept j_7k2p9c worker=did:key:z6Mk... room=p-twg-job-j_7k2p9c"""
    p_room = room or f"p-twg-job-{job_id}"
    return f"twg1 accept {job_id} worker={worker_did} room={p_room}"


def make_deliver(job_id: str, sha256_hex: str, note_path: Optional[str] = None) -> str:
    """twg1 deliver j_7k2p9c sha256=<hex> note=twg-jobs/j_7k2p9c-out"""
    note = note_path or f"twg-jobs/{job_id}-out"
    return f"twg1 deliver {job_id} sha256={sha256_hex} note={note}"


def make_receipt(job_id: str, ok: int = 1) -> str:
    """twg1 receipt j_7k2p9c ok=1"""
    return f"twg1 receipt {job_id} ok={ok}"


def make_hb(jobs_open: int, agents_alive: int, msgs: int) -> str:
    """twg1 hb jobs_open=7 agents_alive=12 msgs=340"""
    return f"twg1 hb jobs_open={jobs_open} agents_alive={agents_alive} msgs={msgs}"


def make_expire(job_id: str, reason: str = "sla") -> str:
    """twg1 expire j_7k2p9c reason=sla"""
    return f"twg1 expire {job_id} reason={reason}"
