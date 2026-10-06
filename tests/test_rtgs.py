import pytest

from backend.rtgs import plain_rtgs, rtgs_problems


@pytest.mark.parametrize(
    "word, rtgs",
    [
        ("กระเป๋า", "krapao"),
        ("ครับ", "khrap"),
        ("ไม่เป็นไร", "mai pen rai"),
        ("หลิง", "Ling"),
        ("ช่อง", "chong 25"),
    ],
)
def test_plain_rtgs_passes(word, rtgs):
    assert rtgs_problems(word, rtgs) == []


@pytest.mark.parametrize(
    "word, rtgs",
    [
        ("กระเป๋า", "grà-bpǎo"),  # 聲調符號、連字號
        ("ครับ", "kráp"),  # 聲調符號
        ("ใบแรก", "bai-raek"),  # 連字號
        ("สวัสดี", "sawasdee"),  # 不是 RTGS 的母音寫法
        ("อยู่", "yuu"),  # RTGS 不標母音長短
        ("ปาก", "bpak"),  # 別套系統的子音寫法
        ("กระจก", "krajok"),  # RTGS 沒有 j
        ("มา", "  "),  # 沒有拼音
    ],
)
def test_non_rtgs_is_reported(word, rtgs):
    assert rtgs_problems(word, rtgs) != []


@pytest.mark.parametrize("word, rtgs", [("Dior", "Dior"), ("Google", "Google"), ("Vogue Thailand", "Vogue-Thailand"), ("♪♪", "")])
def test_words_without_thai_letters_are_not_checked(word, rtgs):
    assert rtgs_problems(word, rtgs) == []


def test_plain_rtgs_removes_tone_marks_and_hyphens():
    assert plain_rtgs("grà-bpǎo") == "gra bpao"
    assert plain_rtgs("kráp") == "krap"
    assert plain_rtgs("lip-sà-tìk") == "lip sa tik"


def test_plain_rtgs_leaves_clean_text_alone():
    assert plain_rtgs("mai pen rai") == "mai pen rai"
    assert plain_rtgs("Dior") == "Dior"
