from app.core import tracing


class FakeObs:
    def __init__(self):
        self.calls = []

    def start_observation(self, **kw):
        self.calls.append(("start", kw))
        return FakeObs()

    def update(self, **kw):
        self.calls.append(("update", kw))

    def end(self):
        self.calls.append(("end", {}))


def test_disabled_is_noop(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    span = tracing.start_trace("rag.ask")
    child = span.child("x", input="secret")
    child.update(output="secret")
    child.end()
    span.end()  # nothing raises, nothing is imported


def test_content_dropped_unless_opted_in(monkeypatch):
    obs = FakeObs()
    span = tracing.Span(obs)
    monkeypatch.delenv("LANGFUSE_CAPTURE_CONTENT", raising=False)
    span.update(input="q", output="a", metadata={"n": 1})
    assert obs.calls[-1] == ("update", {"metadata": {"n": 1}})
    monkeypatch.setenv("LANGFUSE_CAPTURE_CONTENT", "true")
    span.update(input="q", output="a")
    assert obs.calls[-1] == ("update", {"input": "q", "output": "a"})


def test_errors_never_reach_the_caller():
    class Broken:
        def start_observation(self, **kw):
            raise RuntimeError("boom")

        def update(self, **kw):
            raise RuntimeError("boom")

        def end(self):
            raise RuntimeError("boom")

    span = tracing.Span(Broken())
    span.child("x").end()
    span.update(metadata={})
    span.end()
