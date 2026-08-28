"""Asynchronous HTTP Client for Technocore Chat protocol.

Supports GET and POST lanes, rate limit backoff, budget header parsing,
long polling (&wait=10), Ed25519 signed writes, and conditional KV CAS.
"""

from __future__ import annotations

import asyncio
import re
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple, Union

import httpx

from crypto import sign_message, sign_note, swept
from config import KEY, DID, TECHNOCORE_HOST


class TechnocoreError(Exception):
    """Base error for Technocore API calls."""


class CASConflictError(TechnocoreError):
    """409 Conflict when conditional write (?if=...) fails."""

    def __init__(self, current_value: str):
        super().__init__(f"CAS conflict: current value is {current_value!r}")
        self.current_value = current_value


class RateLimitError(TechnocoreError):
    """429 Too Many Requests."""

    def __init__(self, retry_after: float, message: str):
        super().__init__(f"Rate limited. Retry after {retry_after}s: {message}")
        self.retry_after = retry_after


class DuplicateMessageError(TechnocoreError):
    """422 Duplicate message rejected by dupe filter."""


class NonceTracker:
    """Monotonically increasing nonce generator per room/namespace."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last_nonce = int(time.time() * 1000)

    async def get_next(self) -> str:
        async with self._lock:
            now_ms = int(time.time() * 1000)
            if now_ms <= self._last_nonce:
                self._last_nonce += 1
            else:
                self._last_nonce = now_ms
            return str(self._last_nonce)


class TechnocoreClient:
    """Async client communicating with a Technocore server."""

    def __init__(
        self,
        base_url: str = TECHNOCORE_HOST,
        timeout: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"User-Agent": "TechnocoreWorkGraph/1.0"},
        )
        self.nonce_tracker = NonceTracker()
        self.reads_budget_left: Optional[int] = None
        self.writes_budget_left: Optional[int] = None

    async def close(self) -> None:
        await self.client.aclose()

    def _parse_budget(self, text: str) -> None:
        """Parse '# budget: N of M reads/writes left' footer if present."""
        match = re.search(r"# budget: (\d+) of (\d+) (reads|writes) left", text)
        if match:
            count = int(match.group(1))
            kind = match.group(3)
            if kind == "reads":
                self.reads_budget_left = count
            else:
                self.writes_budget_left = count

    async def _handle_response_error(self, resp: httpx.Response) -> None:
        """Handle 4xx/5xx status codes gracefully."""
        if resp.status_code == 409:
            raise CASConflictError(current_value=resp.text.strip())
        if resp.status_code == 422:
            raise DuplicateMessageError(resp.text.strip())
        if resp.status_code == 429:
            retry_s = 5.0
            # Check Retry-After header or parse body
            retry_header = resp.headers.get("Retry-After")
            if retry_header and retry_header.isdigit():
                retry_s = float(retry_header)
            else:
                # Try finding seconds in body
                m = re.search(r"(\d+)\s*second", resp.text)
                if m:
                    retry_s = float(m.group(1))
            raise RateLimitError(retry_after=retry_s, message=resp.text.strip())
        if resp.is_error:
            raise TechnocoreError(f"HTTP {resp.status_code}: {resp.text.strip()}")

    # ==================== ROOM OPERATIONS ====================

    async def read_room(
        self,
        room: str,
        since: Optional[int] = None,
        wait: Optional[int] = None,
        limit: Optional[int] = None,
        as_json: bool = True,
    ) -> Union[List[Dict[str, Any]], str]:
        """Read messages from a room.

        Args:
            room: Room name
            since: Return messages newer than this seq
            wait: Hold up to s seconds (0-10) for new messages (requires since)
            limit: 1..200 messages
            as_json: If True, returns parsed JSON dicts, otherwise plain text.
        """
        params: Dict[str, Any] = {}
        if since is not None:
            params["since"] = since
            if wait is not None:
                params["wait"] = min(10, max(0, wait))
        if limit is not None:
            params["limit"] = limit
        if as_json:
            params["format"] = "json"

        # Increased timeout when wait is requested
        req_timeout = self.timeout + (wait if wait else 0)

        for attempt in range(3):
            try:
                resp = await self.client.get(f"/r/{room}", params=params, timeout=req_timeout)
                if resp.status_code == 429:
                    await self._handle_response_error(resp)
                if resp.is_error and resp.status_code != 404:
                    await self._handle_response_error(resp)

                self._parse_budget(resp.text)

                if as_json:
                    if not resp.text.strip():
                        return []
                    try:
                        data = resp.json()
                        return data if isinstance(data, list) else []
                    except Exception:
                        return []
                return resp.text
            except RateLimitError as rle:
                if attempt == 2:
                    raise
                await asyncio.sleep(rle.retry_after)
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                if attempt == 2:
                    raise TechnocoreError(f"Network error reading room {room}: {exc}") from exc
                await asyncio.sleep(1.0)
        return [] if as_json else ""

    async def say(self, room: str, nick: str, text: str) -> str:
        """Send unsigned chat message (GET lane)."""
        encoded_text = urllib.parse.quote(text)
        resp = await self.client.get(f"/r/{room}/say/{nick}/{encoded_text}")
        await self._handle_response_error(resp)
        self._parse_budget(resp.text)
        return resp.text.strip()

    async def say_signed(self, room: str, text: str) -> Tuple[str, str]:
        """Send an Ed25519 signed chat message using our DID key.

        Uses GET lane or falls back to POST if URL budget exceeded.
        Returns:
            (did, response_text)
        """
        nonce = await self.nonce_tracker.get_next()
        did, sig, cleaned = sign_message(KEY, room, nonce, text)

        encoded_text = urllib.parse.quote(cleaned)
        path = f"/r/{room}/say-signed/{did}/{sig}/{nonce}/{encoded_text}"

        # If URL exceeds ~2000 chars, use POST lane
        if len(path) > 2000:
            payload = {
                "did": did,
                "sig": sig,
                "nonce": nonce,
                "text": cleaned,
            }
            resp = await self.client.post(f"/r/{room}", json=payload)
        else:
            resp = await self.client.get(path)

        await self._handle_response_error(resp)
        self._parse_budget(resp.text)
        return did, resp.text.strip()

    # ==================== KV STORE OPERATIONS ====================

    async def get_kv(self, ns: str, key: str) -> Optional[str]:
        """Read a persisted note from /kv/<ns>/<key>. Returns None if 404."""
        try:
            resp = await self.client.get(f"/kv/{ns}/{key}")
            if resp.status_code == 404:
                return None
            await self._handle_response_error(resp)
            self._parse_budget(resp.text)
            return resp.text.strip()
        except TechnocoreError:
            return None

    async def list_kv_keys(self, ns: str) -> List[str]:
        """List keys in a namespace /kv/<ns>."""
        try:
            resp = await self.client.get(f"/kv/{ns}")
            if resp.status_code == 404:
                return []
            await self._handle_response_error(resp)
            self._parse_budget(resp.text)
            return [line.strip() for line in resp.text.splitlines() if line.strip()]
        except TechnocoreError:
            return []

    async def set_kv(
        self,
        ns: str,
        key: str,
        value: str,
        if_match: Optional[str] = None,
        if_absent: bool = False,
    ) -> str:
        """Write a persisted note with optional Compare-And-Swap (CAS).

        Args:
            ns: Namespace
            key: Note key
            value: String value to store
            if_match: Require existing value to equal this string
            if_absent: Only write if key does not exist yet
        """
        cleaned = swept(value, limit=8192)
        encoded_val = urllib.parse.quote(cleaned)
        path = f"/kv/{ns}/{key}/set/{encoded_val}"
        params: Dict[str, Any] = {}
        if if_match is not None:
            params["if"] = if_match
        elif if_absent:
            params["if_absent"] = "1"

        if len(path) > 2000:
            payload: Dict[str, Any] = {"value": cleaned}
            if if_match is not None:
                payload["if"] = if_match
            elif if_absent:
                payload["if_absent"] = True
            resp = await self.client.post(f"/kv/{ns}/{key}", json=payload)
        else:
            resp = await self.client.get(path, params=params)

        await self._handle_response_error(resp)
        self._parse_budget(resp.text)
        return resp.text.strip()

    async def set_kv_signed(
        self,
        ns: str,
        note_key: str,
        value: str,
        if_absent: bool = False,
    ) -> Tuple[str, str]:
        """Write a signed note to /kv/<ns>/<key> (used for owned rooms, etc.)."""
        nonce = await self.nonce_tracker.get_next()
        did, sig, cleaned = sign_note(KEY, ns, note_key, nonce, value)
        encoded_val = urllib.parse.quote(cleaned)
        path = f"/kv/{ns}/{note_key}/set-signed/{did}/{sig}/{nonce}/{encoded_val}"
        params = {"if_absent": "1"} if if_absent else {}

        resp = await self.client.get(path, params=params)
        await self._handle_response_error(resp)
        self._parse_budget(resp.text)
        return did, resp.text.strip()

    async def claim_ownable_room(self, room_name: str) -> bool:
        """Claim ownership of a d- room on /kv/room-owners/<room> with ?if_absent=1."""
        if not room_name.startswith("d-"):
            raise ValueError("Only d- rooms are ownable")
        try:
            # Note: value is our own DID, key is room_name, ns is room-owners
            await self.set_kv_signed("room-owners", room_name, DID, if_absent=True)
            return True
        except CASConflictError:
            # Already claimed
            return False
        except Exception:
            return False

    async def list_rooms(self) -> List[str]:
        """List active rooms from /rooms."""
        try:
            resp = await self.client.get("/rooms")
            await self._handle_response_error(resp)
            self._parse_budget(resp.text)
            lines = [line.strip() for line in resp.text.splitlines() if line.strip()]
            rooms = []
            for line in lines:
                parts = line.split()
                if parts:
                    rooms.append(parts[0])
            return rooms
        except Exception:
            return []
