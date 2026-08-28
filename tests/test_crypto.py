import pytest
from crypto import (
    generate_seed_and_key,
    load_key_from_seed,
    did_to_public_key_bytes,
    get_did_shard,
    swept,
    sign_message,
    sign_note,
    verify_signature,
)


def test_did_generation_and_roundtrip():
    seed_hex, key, did = generate_seed_and_key()
    assert did.startswith("did:key:z6Mk")
    assert len(did) == 8 + 48  # 'did:key:' + 48 multibase chars

    pub_raw = did_to_public_key_bytes(did)
    assert len(pub_raw) == 32

    # Roundtrip from seed
    key2, did2 = load_key_from_seed(seed_hex)
    assert did2 == did


def test_did_sharding():
    did = "did:key:z6MkuTi8ePzFpQy5oQv6zB8bC9dE0fG1hI2jK3lM4nO5pQ6r"
    fp, shard, key = get_did_shard(did)
    assert len(fp) == 16
    assert len(shard) == 2
    assert len(key) == 14
    assert fp == shard + key


def test_single_line_sweep():
    raw = "Hello\nWorld\t!\u200b\r\n"
    cleaned = swept(raw)
    assert cleaned == "Hello World !"
    assert "\n" not in cleaned
    assert "\r" not in cleaned

    with pytest.raises(ValueError):
        swept("\n\r \t\u200b")  # Nothing visible


def test_sign_message_and_verify():
    _, key, did = generate_seed_and_key()
    room = "lobby"
    nonce = "1700000000123"
    text = "Technocore Work Graph is online! 🚀"

    did_out, sig, cleaned_text = sign_message(key, room, nonce, text)
    assert did_out == did
    assert len(sig) == 86

    canonical = f"{room}|{nonce}|{cleaned_text}"
    assert verify_signature(did, sig, canonical) is True

    # Tampered message should fail
    assert verify_signature(did, sig, f"{room}|{nonce}|tampered text") is False
    # Tampered room should fail
    assert verify_signature(did, sig, f"other_room|{nonce}|{cleaned_text}") is False


def test_sign_note():
    _, key, did = generate_seed_and_key()
    ns = "workgraph-state"
    note_key = "cursor"
    nonce = "1"
    value = "10452"

    did_out, sig, cleaned_val = sign_note(key, ns, note_key, nonce, value)
    assert did_out == did
    canonical = f"{ns}|{note_key}|{nonce}|{cleaned_val}"
    assert verify_signature(did, sig, canonical) is True
