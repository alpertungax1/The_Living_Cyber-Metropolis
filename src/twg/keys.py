"""Ed25519 did:key management, text sweeping, and canonical signature engine according to SPEC.md."""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
import unicodedata
from typing import Tuple

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

PREFIX = "did:key:z6Mk"
MULTICODEC_ED25519 = b"\xed\x01"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_INDEX = {c: i for i, c in enumerate(B58)}

INVISIBLE_CATEGORIES = ("Cc", "Cf", "Cs", "Co", "Zl", "Zp")
MAX_TEXT_CHARS = 4096
MAX_VALUE_CHARS = 8192

NONCE_PATTERN = r"^[0-9]{1,19}$"
NONCE_RE = re.compile(NONCE_PATTERN)
SIG_PATTERN = r"^[A-Za-z0-9_-]{86}$"
SIG_RE = re.compile(SIG_PATTERN)


def swept(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    """Clean text exactly as the Technocore server stores it."""
    if not isinstance(text, str):
        text = str(text)
    cleaned = "".join(
        " " if unicodedata.category(c) in INVISIBLE_CATEGORIES else c for c in text
    ).strip()
    if not cleaned:
        raise ValueError("Nothing visible left after single-line sweep")
    if len(cleaned) > limit:
        raise ValueError(
            f"Text length {len(cleaned)} exceeds limit {limit} after sweep"
        )
    return cleaned


def _multibase_b58(raw: bytes) -> str:
    """Base58btc encode bytes."""
    n = int.from_bytes(raw, "big")
    out = ""
    while n:
        n, rem = divmod(n, 58)
        out = B58[rem] + out
    return out


def _b58decode(raw: str) -> bytes:
    """Base58btc decode string."""
    n = 0
    for ch in raw:
        digit = _B58_INDEX.get(ch)
        if digit is None:
            raise ValueError(f"Character {ch!r} is not base58btc")
        n = n * 58 + digit
    return n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b""


def did_from_private_key(key: Ed25519PrivateKey) -> str:
    """Generate did:key:z6Mk... from an Ed25519PrivateKey."""
    pub_bytes = key.public_key().public_bytes_raw()
    mb = "z" + _multibase_b58(MULTICODEC_ED25519 + pub_bytes)
    return "did:key:" + mb


def did_to_public_key_bytes(did: str) -> bytes:
    """Extract raw 32-byte Ed25519 public key from did:key."""
    if not did.startswith("did:key:"):
        raise ValueError("Invalid did:key format")
    mb = did[len("did:key:"):]
    if len(mb) != 48 or not mb.startswith("z"):
        raise ValueError("Invalid multibase did:key length or prefix")
    decoded = _b58decode(mb[1:])
    if len(decoded) != 34 or not decoded.startswith(MULTICODEC_ED25519):
        raise ValueError("Invalid did:key codec or length")
    return decoded[2:]


def get_did_shard(did: str) -> Tuple[str, str, str]:
    """Calculate fingerprint fp16, shard (first 2 chars), and key (remaining 14 chars).

    Returns:
        (fp16, shard, key)
    """
    fp = hashlib.sha256(did.encode("utf-8")).hexdigest()[:16]
    shard = fp[:2]
    key = fp[2:16]
    return fp, shard, key


def sign_message(key: Ed25519PrivateKey, room: str, nonce: str, text: str) -> Tuple[str, str, str]:
    """Sign a chat message for say-signed.

    Returns:
        (did, signature_base64url, swept_text)
    """
    if not NONCE_RE.match(nonce):
        raise ValueError(f"Nonce must be 1-19 digits, got {nonce!r}")
    cleaned = swept(text, MAX_TEXT_CHARS)
    canonical = f"{room}|{nonce}|{cleaned}"
    raw_sig = key.sign(canonical.encode("utf-8"))
    sig_b64 = base64.urlsafe_b64encode(raw_sig).decode("ascii").rstrip("=")
    did = did_from_private_key(key)
    return did, sig_b64, cleaned


def sign_note(key: Ed25519PrivateKey, ns: str, note_key: str, nonce: str, value: str) -> Tuple[str, str, str]:
    """Sign a KV note for set-signed.

    Returns:
        (did, signature_base64url, swept_value)
    """
    if not NONCE_RE.match(nonce):
        raise ValueError(f"Nonce must be 1-19 digits, got {nonce!r}")
    cleaned = swept(value, MAX_VALUE_CHARS)
    canonical = f"{ns}|{note_key}|{nonce}|{cleaned}"
    raw_sig = key.sign(canonical.encode("utf-8"))
    sig_b64 = base64.urlsafe_b64encode(raw_sig).decode("ascii").rstrip("=")
    did = did_from_private_key(key)
    return did, sig_b64, cleaned


def verify_signature(did: str, sig_b64: str, canonical_payload: str) -> bool:
    """Verify an Ed25519 signature over canonical UTF-8 payload."""
    try:
        if not SIG_RE.match(sig_b64):
            return False
        pub_raw = did_to_public_key_bytes(did)
        pub_key = Ed25519PublicKey.from_public_bytes(pub_raw)
        sig_raw = base64.urlsafe_b64decode(sig_b64 + "==")
        pub_key.verify(sig_raw, canonical_payload.encode("utf-8"))
        return True
    except Exception:
        return False


def generate_seed_and_key() -> Tuple[str, Ed25519PrivateKey, str]:
    """Generate a random 32-byte (64 hex char) seed and Ed25519 key."""
    seed_hex = secrets.token_hex(32)
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_hex))
    did = did_from_private_key(key)
    return seed_hex, key, did


def load_key_from_seed(seed_or_passphrase: str) -> Tuple[Ed25519PrivateKey, str]:
    """Load Ed25519 key from hex seed or string passphrase."""
    if len(seed_or_passphrase) == 64:
        try:
            key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed_or_passphrase))
            return key, did_from_private_key(key)
        except ValueError:
            pass
    digest = hashlib.sha256(seed_or_passphrase.encode("utf-8")).hexdigest()
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(digest))
    return key, did_from_private_key(key)
