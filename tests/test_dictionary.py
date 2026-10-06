import threading

from backend import storage
from backend.dictionary import add_entries, load_dictionary, merge_explanation, missing_words


def entry(rtgs):
    return {"rtgs": rtgs, "parts": [], "senses": "意思", "usage": "用法"}


def explanation(thai, *word_list):
    return {
        "thai": thai,
        "v": storage.ANALYSIS_VERSION,
        "rtgs": "",
        "translation": "",
        "analysis": [{"word": word, "type": "word", "meaning": "本句意思", "more": ""} for word in word_list],
    }


# 讀寫


def test_missing_file_is_an_empty_dictionary(data_dir):
    assert load_dictionary() == {}


def test_corrupt_file_is_an_empty_dictionary(data_dir):
    (data_dir / "dictionary.json").write_text("{ not json", encoding="utf-8")
    assert load_dictionary() == {}


def test_non_object_file_is_an_empty_dictionary(data_dir):
    (data_dir / "dictionary.json").write_text("[1, 2]", encoding="utf-8")
    assert load_dictionary() == {}


def test_add_entries_persists(data_dir):
    returned = add_entries({"มา": entry("ma")})
    assert returned == {"มา": entry("ma")}
    assert load_dictionary() == {"มา": entry("ma")}


def test_add_entries_does_not_overwrite_existing_words(data_dir):
    add_entries({"มา": entry("ma")})
    add_entries({"มา": entry("WRONG"), "แล้ว": entry("laeo")})
    assert load_dictionary() == {"มา": entry("ma"), "แล้ว": entry("laeo")}


def test_concurrent_writers_keep_every_word(data_dir):
    def write(prefix):
        for index in range(25):
            add_entries({f"{prefix}{index}": entry("x")})

    threads = [threading.Thread(target=write, args=(prefix,)) for prefix in ("ก", "ข", "ค", "ง")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(load_dictionary()) == 100


# 找缺的字


def test_missing_words_dedupes_and_keeps_first_sentence():
    explanations = {
        2: explanation("แล้วมา", "แล้ว", "มา"),
        1: explanation("มาแล้ว", "มา", "แล้ว", "มา"),
    }
    assert missing_words(explanations, {}) == {"มา": "มาแล้ว", "แล้ว": "มาแล้ว"}


def test_missing_words_skips_known_words():
    explanations = {1: explanation("มาแล้ว", "มา", "แล้ว")}
    assert missing_words(explanations, {"มา": entry("ma")}) == {"แล้ว": "มาแล้ว"}


def test_missing_words_with_nothing_missing():
    explanations = {1: explanation("มา", "มา")}
    assert missing_words(explanations, {"มา": entry("ma")}) == {}


# 合併


def test_merge_adds_dictionary_fields_and_keeps_sentence_fields():
    merged = merge_explanation(explanation("มา", "มา"), {"มา": entry("ma")})
    assert merged["analysis"] == [
        {
            "word": "มา",
            "type": "word",
            "meaning": "本句意思",
            "more": "",
            "rtgs": "ma",
            "parts": [],
            "senses": "意思",
            "usage": "用法",
        }
    ]
    assert merged["thai"] == "มา"
    assert merged["v"] == storage.ANALYSIS_VERSION
    assert "partial" not in merged


def test_merge_marks_partial_when_a_word_is_unknown():
    merged = merge_explanation(explanation("มาแล้ว", "มา", "แล้ว"), {"มา": entry("ma")})
    assert merged["partial"] is True
    assert merged["analysis"][0]["rtgs"] == "ma"
    assert merged["analysis"][1] == {
        "word": "แล้ว",
        "type": "word",
        "meaning": "本句意思",
        "more": "",
        "rtgs": "",
        "parts": [],
        "senses": "",
        "usage": "",
    }


def test_merge_does_not_modify_its_input():
    original = explanation("มา", "มา")
    merge_explanation(original, {"มา": entry("ma")})
    assert "rtgs" not in original["analysis"][0]


def test_corrupt_file_is_kept_as_a_backup_instead_of_overwritten(data_dir, capsys):
    (data_dir / "dictionary.json").write_text('{"มา": {"rtgs": "ma"', encoding="utf-8")
    add_entries({"แล้ว": entry("laeo")})

    backups = list(data_dir.glob("dictionary.json.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == '{"มา": {"rtgs": "ma"'
    assert load_dictionary() == {"แล้ว": entry("laeo")}
    assert "dictionary.json.corrupt-" in capsys.readouterr().out
