import pytest
from unittest.mock import AsyncMock
from task_engine import TaskEngine
from observer import NetworkObserver
from state import StateManager


@pytest.mark.anyio
async def test_task_engine_execution():
    mock_client = AsyncMock()
    mock_client.set_kv = AsyncMock(return_value="ok")
    mock_client.say_signed = AsyncMock(return_value=("did", "ok"))

    mock_state = AsyncMock(spec=StateManager)
    mock_observer = AsyncMock(spec=NetworkObserver)
    mock_observer.get_metrics = AsyncMock(return_value={
        "active_dids_count": 5,
        "total_messages": 100,
        "signature_ratio": 0.8,
        "velocity_messages_per_min": 12,
    })
    mock_observer.nodes = {}

    engine = TaskEngine(mock_client, mock_observer, mock_state)

    # Test JSON task payload
    json_task = '{"action": "network_stats", "reply_to": "mb-p-test-reply"}'
    res = await engine.handle_mailbox_message(
        sender_did="did:key:z6MkTestRequester1234567890123456789012345678",
        text=json_task,
        seq=1,
    )

    assert res is not None
    assert res["action"] == "network_stats"
    assert res["result"]["status"] == "success"
    assert res["result"]["active_dids"] == 5
    mock_client.set_kv.assert_called_once()
    mock_client.say_signed.assert_called_once()


@pytest.mark.anyio
async def test_task_engine_command_syntax():
    mock_client = AsyncMock()
    mock_client.set_kv = AsyncMock(return_value="ok")
    mock_state = AsyncMock(spec=StateManager)
    mock_observer = AsyncMock(spec=NetworkObserver)
    mock_observer.nodes = {
        "room:lobby": {"data": {"msg_count": 42}}
    }

    engine = TaskEngine(mock_client, mock_observer, mock_state)
    res = await engine.handle_mailbox_message(
        sender_did="did:key:z6MkTestRequester1234567890123456789012345678",
        text="!audit lobby",
        seq=2,
    )

    assert res is not None
    assert res["action"] == "audit"
    assert res["result"]["room"] == "lobby"
    assert res["result"]["tracked_messages"] == 42
