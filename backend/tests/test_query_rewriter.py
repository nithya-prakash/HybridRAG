from app.services.rag.query_rewriter import QueryRewriter


class FakeChat:
    def __init__(self, response: str = "rewritten query", raise_error: bool = False):
        self.response = response
        self.raise_error = raise_error
        self.calls: list[list[dict]] = []

    async def complete(self, messages):
        self.calls.append(messages)
        if self.raise_error:
            raise RuntimeError("boom")
        return self.response

    def stream_complete(self, messages):
        raise NotImplementedError("not needed for these tests")


async def test_rewrite_skips_llm_call_when_no_history():
    chat = FakeChat()
    rewriter = QueryRewriter(chat)

    result = await rewriter.rewrite([], "What is the meal cap?")

    assert result == "What is the meal cap?"
    assert chat.calls == []


async def test_rewrite_calls_llm_with_history_and_returns_stripped_result():
    chat = FakeChat(response="  What does the travel policy say about flights?  ")
    rewriter = QueryRewriter(chat)
    history = [
        ("user", "Tell me about the travel policy"),
        ("assistant", "It covers flights and hotels."),
    ]

    result = await rewriter.rewrite(history, "what about flights?")

    assert result == "What does the travel policy say about flights?"
    assert len(chat.calls) == 1
    messages = chat.calls[0]
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "user", "content": "Tell me about the travel policy"}
    assert messages[2] == {"role": "assistant", "content": "It covers flights and hotels."}
    assert "what about flights?" in messages[-1]["content"]


async def test_rewrite_falls_back_to_raw_query_on_llm_error():
    chat = FakeChat(raise_error=True)
    rewriter = QueryRewriter(chat)

    result = await rewriter.rewrite([("user", "hi"), ("assistant", "hello")], "what about X?")

    assert result == "what about X?"


async def test_rewrite_falls_back_to_raw_query_on_empty_completion():
    chat = FakeChat(response="   ")
    rewriter = QueryRewriter(chat)

    result = await rewriter.rewrite([("user", "hi"), ("assistant", "hello")], "what about X?")

    assert result == "what about X?"


async def test_rewrite_caps_history_to_configured_max_turns():
    chat = FakeChat(response="rewritten")
    rewriter = QueryRewriter(chat)
    history = [("user", f"msg{i}") for i in range(15)]

    await rewriter.rewrite(history, "latest")

    messages = chat.calls[0]
    history_messages = messages[1:-1]  # exclude system prompt and the wrapped final user turn
    assert len(history_messages) == 10
    assert history_messages[0]["content"] == "msg5"
    assert history_messages[-1]["content"] == "msg14"
