from app.services.parsing.tokenizer import count_tokens, split_by_token_budget, tail_by_tokens


def test_count_tokens_empty_string_is_zero():
    assert count_tokens("") == 0


def test_count_tokens_nonempty():
    assert count_tokens("hello world") == 2


def test_split_by_token_budget_returns_single_piece_when_within_budget():
    pieces = split_by_token_budget("hello world", max_tokens=50)
    assert pieces == ["hello world"]


def test_split_by_token_budget_splits_when_over_budget():
    text = " ".join(f"word{i}" for i in range(200))
    pieces = split_by_token_budget(text, max_tokens=20)
    assert len(pieces) > 1
    assert all(count_tokens(p) <= 20 for p in pieces)
    # round-tripping the pieces should reconstruct the same token stream length
    assert sum(count_tokens(p) for p in pieces) == count_tokens(text)


def test_tail_by_tokens_returns_whole_text_when_shorter_than_n():
    assert tail_by_tokens("hello world", n=50) == "hello world"


def test_tail_by_tokens_returns_suffix():
    text = " ".join(f"word{i}" for i in range(50))
    tail = tail_by_tokens(text, n=5)
    assert count_tokens(tail) <= 5
    assert text.endswith(tail.strip()) or tail.strip() in text


def test_tail_by_tokens_zero_or_negative_is_empty():
    assert tail_by_tokens("hello world", n=0) == ""
    assert tail_by_tokens("hello world", n=-1) == ""
