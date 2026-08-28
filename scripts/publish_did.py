#!/usr/bin/env python3
"""Publish DID note and profile to Technocore KV according to SPEC.md."""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.twg.keys import load_key_from_seed, get_did_shard
from src.twg.http import TechnocoreHTTP

load_dotenv()


async def main():
    seed = os.getenv("TWG_SEED") or os.getenv("SIGN_SEED")
    mailbox = os.getenv("TWG_MAILBOX") or os.getenv("MAILBOX_NAME")

    if not seed or not mailbox:
        print("Error: Please set TWG_SEED and TWG_MAILBOX in your .env")
        return

    key, did = load_key_from_seed(seed)
    fp16, shard, key_path = get_did_shard(did)

    http = TechnocoreHTTP(key=key, did=did)
    try:
        ns = f"did-{shard}"
        did_note = f"{did} mailbox:{mailbox} twg:v1 svc:observe|board"
        await http.set_kv(ns, key_path, did_note)
        print(f"Successfully published DID note to /kv/{ns}/{key_path}")
        print(f"Content: {did_note}")
    finally:
        await http.close()


if __name__ == "__main__":
    asyncio.run(main())
