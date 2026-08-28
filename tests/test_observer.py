import pytest
from unittest.mock import AsyncMock
from observer import NetworkObserver
from state import StateManager


@pytest.mark.anyio
async def test_observer_ingest_and_graph():
    mock_client = AsyncMock()
    mock_state = AsyncMock(spec=StateManager)
    observer = NetworkObserver(mock_client, mock_state)

    # Record room creation
    await observer.record_room_created("d-test-room")
    assert "room:d-test-room" in observer.nodes

    # Ingest signed message
    did = "did:key:z6MkuTi8ePzFpQy5oQv6zB8bC9dE0fG1hI2jK3lM4nO5pQ6r"
    await observer.ingest_message(
        room="d-test-room",
        sender=did,
        text="Hello Work Graph",
        seq=1,
        is_signed=True,
    )

    # Ingest anon message
    await observer.ingest_message(
        room="d-test-room",
        sender="alice",
        text="GM anon",
        seq=2,
        is_signed=False,
    )

    metrics = await observer.get_metrics()
    assert metrics["total_messages"] == 2
    assert metrics["signed_messages"] == 1
    assert metrics["anon_messages"] == 1
    assert metrics["signature_ratio"] == 0.5
    assert metrics["active_dids_count"] == 1

    graph = await observer.get_graph_data()
    assert len(graph["nodes"]) >= 3  # room + did + anon
    assert len(graph["edges"]) == 2  # did->room, anon->room
