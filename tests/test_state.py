import pytest
import os
from unittest.mock import AsyncMock
from state import StateManager, LOCAL_STATE_FILE


@pytest.fixture(autouse=True)
def clean_local_state():
    if LOCAL_STATE_FILE.exists():
        os.remove(LOCAL_STATE_FILE)
    yield
    if LOCAL_STATE_FILE.exists():
        os.remove(LOCAL_STATE_FILE)


@pytest.mark.anyio
async def test_state_manager_local_and_cursor():
    mock_client = AsyncMock()
    mock_client.set_kv = AsyncMock(return_value="ok")
    mock_client.list_kv_keys = AsyncMock(return_value=["cursor_events", "cursor_lobby"])
    mock_client.get_kv = AsyncMock(side_effect=lambda ns, key: "42" if key == "cursor_events" else "100")

    mgr = StateManager(mock_client, ns="test-ns")
    assert mgr.get_cursor("events") == 0

    await mgr.bootstrap()
    assert mgr.get_cursor("events") == 42
    assert mgr.get_cursor("lobby") == 100

    await mgr.update_cursor("events", 50)
    assert mgr.get_cursor("events") == 50

    mgr.record_discovered_room("room-alpha")
    assert "room-alpha" in mgr.state["known_rooms"]
    assert mgr.state["total_rooms_discovered"] == 1
