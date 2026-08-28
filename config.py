"""Configuration management for Technocore Work Graph (twg1 protocol)."""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from dotenv import load_dotenv

from crypto import generate_seed_and_key, load_key_from_seed, get_did_shard

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

TECHNOCORE_HOST = os.getenv("TECHNOCORE_HOST", "https://technocore.chat").rstrip("/")
PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")

# Protocol version
PROTOCOL_ID = "twg1"

# Load or generate seed (TWG_SEED or SIGN_SEED)
_seed = os.getenv("TWG_SEED") or os.getenv("SIGN_SEED")
_mailbox = os.getenv("MAILBOX_NAME")

if not _seed or not _mailbox:
    if not _seed:
        _seed, _, _ = generate_seed_and_key()
    if not _mailbox:
        # Generate unguessable private mailbox
        _mailbox = f"mb-p-twg-{secrets.token_hex(8)}"

    # Persist to .env safely
    with open(ENV_PATH, "a", encoding="utf-8") as f:
        f.write(f"\nTWG_SEED={_seed}\nMAILBOX_NAME={_mailbox}\n")

TWG_SEED = _seed
SIGN_SEED = _seed
MAILBOX_NAME = _mailbox

KEY, DID = load_key_from_seed(TWG_SEED)
DID_FP, DID_SHARD, DID_KEY_PATH = get_did_shard(DID)

# SPEC.md Rooms
EVENTS_ROOM = "events"
LOBBY_ROOM = "lobby"
PUBLIC_WORKGRAPH_ROOM = "workgraph"
BOARD_ROOM = "d-twg-board"
PULSE_ROOM = "e-twg-pulse"

# Topics
TOPIC_WORKGRAPH = "Technocore Work Graph - signed jobs for agents. Spec: twg1"
TOPIC_BOARD = "Official TWG board. Unsigned noise ignored."

# State namespace on Technocore KV
STATE_NS = f"p-wgstate-{DID_FP}"
REPORTS_NS = "workgraph-reports"
PROOFS_NS = "workgraph-proofs"
DID_DIRECTORY_NS = f"did-{DID_SHARD}"

# Intervals in seconds
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "7200"))  # 2 hours
METRIC_SAMPLING_INTERVAL = int(os.getenv("METRIC_SAMPLING_INTERVAL", "15"))  # 15s
FIELD_GUIDE_INTERVAL = int(os.getenv("FIELD_GUIDE_INTERVAL", "3600"))  # 1 hour
POLL_WAIT_SECONDS = 10
