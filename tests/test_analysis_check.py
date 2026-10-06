from backend.analysis_check import check_analysis


def words(*items):
    """("字", "type") → analysis 清單；只給字串時 type 是 word"""
    return [
        {"word": item, "type": "word"} if isinstance(item, str) else {"word": item[0], "type": item[1]}
        for item in items
    ]


# 涵蓋


def test_full_coverage_passes():
    assert check_analysis("ไม่เป็นไรค่ะ", words(("ไม่เป็นไร", "expression"), ("ค่ะ", "particle"))) == []


def test_missing_word_fails():
    assert check_analysis("ไม่เป็นไรค่ะ", words(("ไม่เป็นไร", "expression"))) != []


def test_changed_spelling_fails():
    assert check_analysis("มาแล้ว", words("มา", "เเล้ว")) != []


def test_wrong_order_fails():
    assert check_analysis("มาแล้ว", words("แล้ว", "มา")) != []


def test_whitespace_and_punctuation_are_ignored():
    assert check_analysis("มา แล้ว!\nค่ะ", words("มา", "แล้ว", ("ค่ะ", "particle"))) == []


def test_symbol_only_line_passes_with_empty_analysis():
    assert check_analysis("♪♪ ~", []) == []


def test_text_line_with_empty_analysis_fails():
    assert check_analysis("มาแล้ว", []) != []


# 粒度


def test_whole_clause_as_one_word_fails():
    clause = "พร้อมที่จะส่งเราให้ไปแบบใช่กันไปเรื่อยๆ"
    problems = check_analysis(clause, words(clause))
    assert len(problems) == 1
    assert clause in problems[0]


def test_compound_word_passes():
    assert check_analysis("เครื่องเขียน", words("เครื่องเขียน")) == []


def test_four_token_idiom_passes():
    assert check_analysis("ชี้เป็นชี้ตาย", words(("ชี้เป็นชี้ตาย", "expression"))) == []


def test_long_name_passes_only_as_name():
    name = "ภัทราภัทรโบว์รัชตะสุวรรณ"
    assert check_analysis(name, words((name, "name"))) == []
    assert check_analysis(name, words(name)) != []


def test_items_without_type_are_treated_as_words():
    clause = "พร้อมที่จะส่งเราให้ไปแบบใช่กันไปเรื่อยๆ"
    assert check_analysis(clause, [{"word": clause}]) != []
