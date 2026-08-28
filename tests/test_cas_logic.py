import pytest
from unittest.mock import AsyncMock
from src.twg.store import TwgStore
from src.twg.http import CASConflictError


@pytest.mark.anyio
async def test_job_state_machine_cas():
    mock_http = AsyncMock()
    # Memory KV store simulator
    kv_data = {}

    async def mock_get_kv(ns, key):
        return kv_data.get(f"{ns}/{key}")

    async def mock_set_kv(ns, key, val, if_match=None, if_absent=False):
        full_key = f"{ns}/{key}"
        curr = kv_data.get(full_key)
        if if_absent and curr is not None:
            raise CASConflictError(curr)
        if if_match is not None and curr != if_match:
            raise CASConflictError(curr or "")
        kv_data[full_key] = val
        return "ok"

    mock_http.get_kv = mock_get_kv
    mock_http.set_kv = mock_set_kv

    store = TwgStore(mock_http)

    # 1. Create Job (open)
    job_id = "j_test123"
    created = await store.create_job(
        job_id=job_id,
        kind="observe",
        by_did="did:key:z6MkPoster...",
        sla=600,
        input_target="room:lobby",
    )
    assert created is True

    job = await store.get_job(job_id)
    assert job["st"] == "open"

    # 2. Append Bid
    bid_appended = await store.append_bid(job_id, "did:key:z6MkWorker...", 30, 0.9)
    assert bid_appended is True

    # 3. Accept Job (open -> accepted)
    accepted = await store.accept_job(job_id, "did:key:z6MkWorker...", "p-twg-job-j_test123")
    assert accepted is True
    job = await store.get_job(job_id)
    assert job["st"] == "accepted"

    # 4. Deliver Job (accepted -> delivered)
    delivered = await store.deliver_job(job_id, "sha256_mock_hash", "observe room=lobby n=50 signed=11")
    assert delivered is True
    job = await store.get_job(job_id)
    assert job["st"] == "delivered"

    # 5. Close Job (delivered -> closed)
    closed = await store.close_job(job_id, ok=True)
    assert closed is True
    job = await store.get_job(job_id)
    assert job["st"] == "closed"
