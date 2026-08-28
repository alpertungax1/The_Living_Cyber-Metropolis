#!/usr/bin/env python3
"""Claim ownership of d-twg-board room according to SPEC.md."""

import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.twg.keys import load_key_from_seed
from src.twg.http import TechnocoreHTTP

load_dotenv()


async def main():
    seed = os.getenv("TWG_SEED") or os.getenv("SIGN_SEED")
    if not seed:
        print("Error: TWG_SEED not found in .env")
        return

    key, did = load_key_from_seed(seed)
    http = TechnocoreHTTP(key=key, did=did)

    try:
        print("Attempting to claim ownership of d-twg-board...")
        claimed = await http.claim_ownable_room("d-twg-board")
        if claimed:
            print("Successfully claimed d-twg-board with ?if_absent=1!")
        else:
            print("Room d-twg-board is already claimed or owned by someone else.")
    finally:
        await http.close()


if __name__ == "__main__":
    asyncio.run(main())
