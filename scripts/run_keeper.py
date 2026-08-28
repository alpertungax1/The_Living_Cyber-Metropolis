#!/usr/bin/env python3
"""Run the standalone twg1 Graph-Keeper daemon according to SPEC.md."""

import asyncio
import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.twg.keys import load_key_from_seed
from src.twg.http import TechnocoreHTTP
from src.twg.store import TwgStore
from src.twg.keeper import GraphKeeper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
load_dotenv()


async def main():
    seed = os.getenv("TWG_SEED") or os.getenv("SIGN_SEED")
    mailbox = os.getenv("TWG_MAILBOX") or os.getenv("MAILBOX_NAME")

    if not seed or not mailbox:
        print("Error: TWG_SEED and TWG_MAILBOX must be set in .env")
        return

    key, did = load_key_from_seed(seed)
    http = TechnocoreHTTP(key=key, did=did)
    store = TwgStore(http)
    keeper = GraphKeeper(http=http, store=store, mailbox=mailbox)

    await keeper.initialize()
    await keeper.start()
    print("Graph-Keeper is running. Press Ctrl+C to stop.")

    try:
        while True:
            await asyncio.sleep(1.0)
    except KeyboardInterrupt:
        print("Stopping keeper...")
    finally:
        await keeper.stop()
        await http.close()


if __name__ == "__main__":
    asyncio.run(main())
