#!/usr/bin/env python3
"""Generate random seed, Ed25519 did:key and sharded paths according to SPEC.md."""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.twg.keys import generate_seed_and_key, get_did_shard


def main():
    seed_hex, _, did = generate_seed_and_key()
    fp16, shard, key_path = get_did_shard(did)

    print("=" * 60)
    print("Technocore Work Graph (twg1) Identity Generator")
    print("=" * 60)
    print(f"TWG_SEED:     {seed_hex}")
    print(f"DID:          {did}")
    print(f"Fingerprint:  {fp16}")
    print(f"Shard / Key:  did-{shard} / {key_path}")
    print("=" * 60)
    print("Save TWG_SEED to your .env file. NEVER share or commit it!")


if __name__ == "__main__":
    main()
