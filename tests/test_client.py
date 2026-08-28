import pytest
from client import NonceTracker, TechnocoreClient


@pytest.mark.anyio
async def test_nonce_tracker_monotonic():
    tracker = NonceTracker()
    n1 = await tracker.get_next()
    n2 = await tracker.get_next()
    n3 = await tracker.get_next()
    assert int(n2) > int(n1)
    assert int(n3) > int(n2)


def test_parse_budget():
    client = TechnocoreClient()
    text = "ok\n# budget: 45 of 200 reads left this minute"
    client._parse_budget(text)
    assert client.reads_budget_left == 45

    text2 = "ok\n# budget: 12 of 60 writes left this minute"
    client._parse_budget(text2)
    assert client.writes_budget_left == 12
