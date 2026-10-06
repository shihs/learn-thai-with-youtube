from backend.segmenter import tokenize


def test_tokenize_splits_thai_into_words():
    assert tokenize("ไม่เป็นไรค่ะ") == ["ไม่เป็นไร", "ค่ะ"]


def test_tokenize_drops_whitespace_tokens():
    tokens = tokenize("ตู้เย็น อยู่ไหน\nน้ำแข็ง")
    assert tokens == ["ตู้เย็น", "อยู่", "ไหน", "น้ำแข็ง"]
    assert all(token.strip() for token in tokens)


def test_tokenize_empty_text():
    assert tokenize("") == []
