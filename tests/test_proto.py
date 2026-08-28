from src.twg.proto import (
    parse_twg_line,
    make_job,
)


def test_parse_twg_verbs():
    # Hello
    h = parse_twg_line("twg1 hello keeper svc=observe,board docs=https://technocore.chat")
    assert h is not None
    assert h.verb == "hello"
    assert h.args == ["keeper"]
    assert h.kwargs["svc"] == "observe,board"

    # Job
    job_line = (
        "twg1 job j_7k2p9c1a kind=observe pay=rep sla=600 "
        "input=room:lobby out=note:twg-jobs/j_7k2p9c1a-out"
    )
    j = parse_twg_line(job_line)
    assert j is not None
    assert j.verb == "job"
    assert j.args == ["j_7k2p9c1a"]
    assert j.kwargs["kind"] == "observe"
    assert j.kwargs["sla"] == "600"

    # Bid
    b = parse_twg_line("twg1 bid j_7k2p9c1a eta=90 conf=0.8")
    assert b is not None
    assert b.verb == "bid"
    assert b.args == ["j_7k2p9c1a"]
    assert b.kwargs["eta"] == "90"
    assert b.kwargs["conf"] == "0.8"

    # Accept
    a = parse_twg_line("twg1 accept j_7k2p9c1a worker=did:key:z6Mk... room=p-twg-job-j_7k2p9c1a")
    assert a is not None
    assert a.verb == "accept"
    assert a.args == ["j_7k2p9c1a"]
    assert a.kwargs["worker"] == "did:key:z6Mk..."
    assert a.kwargs["room"] == "p-twg-job-j_7k2p9c1a"

    # Deliver
    d = parse_twg_line("twg1 deliver j_7k2p9c1a sha256=abc123def456 note=twg-jobs/j_7k2p9c1a-out")
    assert d is not None
    assert d.verb == "deliver"
    assert d.args == ["j_7k2p9c1a"]
    assert d.kwargs["sha256"] == "abc123def456"

    # Receipt
    r = parse_twg_line("twg1 receipt j_7k2p9c1a ok=1")
    assert r is not None
    assert r.verb == "receipt"
    assert r.args == ["j_7k2p9c1a"]
    assert r.kwargs["ok"] == "1"


def test_builder_roundtrips():
    line = make_job("j_deadbeef", kind="observe", pay="rep", sla=120, input_target="room:lobby")
    parsed = parse_twg_line(line)
    assert parsed is not None
    assert parsed.args[0] == "j_deadbeef"
    assert parsed.kwargs["kind"] == "observe"
    assert parsed.kwargs["sla"] == "120"
