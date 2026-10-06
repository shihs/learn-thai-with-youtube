import pytest

from backend import gpt_teacher, storage
from tests.conftest import FakeClient

# 每一句正確的拆法
GOOD = {
    "ไม่เป็นไรค่ะ": [("ไม่เป็นไร", "expression"), ("ค่ะ", "particle")],
    "มาแล้ว": [("มา", "word"), ("แล้ว", "word")],
}
# 漏掉後半句的拆法，過不了涵蓋檢查
BAD = {
    "ไม่เป็นไรค่ะ": [("ไม่เป็นไร", "expression")],
    "มาแล้ว": [("มา", "word")],
}


def result(pairs):
    return {
        "rtgs": "rtgs",
        "translation": "翻譯",
        "analysis": [{"word": word, "type": kind, "meaning": "意思", "more": ""} for word, kind in pairs],
    }


def respond_with(table):
    return lambda payload: {key: result(table[item["thai"]]) for key, item in payload.items()}


def transcript(*texts):
    return {index: {"text": text} for index, text in enumerate(texts)}


@pytest.fixture
def use_client(monkeypatch):
    def install(respond):
        client = FakeClient(respond)
        monkeypatch.setattr(gpt_teacher, "OpenAI", lambda **kwargs: client)
        return client

    return install


@pytest.fixture
def no_client(monkeypatch):
    def fail(**kwargs):
        raise AssertionError("不應該呼叫 OpenAI")

    monkeypatch.setattr(gpt_teacher, "OpenAI", fail)


# 提示開關


def test_hint_defaults_to_on(monkeypatch):
    monkeypatch.delenv("SEGMENT_HINT", raising=False)
    # 對照實驗（103 句）：on 最後沒通過檢查 3 句、off 8 句，所以預設開啟
    assert gpt_teacher.segment_hint_enabled() is True


def test_hint_follows_environment(monkeypatch):
    monkeypatch.setenv("SEGMENT_HINT", "off")
    assert gpt_teacher.segment_hint_enabled() is False
    monkeypatch.setenv("SEGMENT_HINT", "ON")
    assert gpt_teacher.segment_hint_enabled() is True


def test_payload_with_hint_includes_tokens():
    payload = gpt_teacher.build_payload([{"id": 7, "thai": "ไม่เป็นไรค่ะ"}], hint=True)
    assert payload == {"item_1": {"thai": "ไม่เป็นไรค่ะ", "tokens": ["ไม่เป็นไร", "ค่ะ"]}}


def test_payload_and_prompt_without_hint_never_mention_tokens():
    payload = gpt_teacher.build_payload([{"id": 7, "thai": "ไม่เป็นไรค่ะ"}], hint=False)
    assert payload == {"item_1": {"thai": "ไม่เป็นไรค่ะ"}}
    assert "tokens" not in gpt_teacher.build_prompt(payload, hint=False)
    assert "tokens" in gpt_teacher.build_prompt(gpt_teacher.build_payload([{"id": 7, "thai": "มา"}], True), True)


# 解析結果


def test_results_carry_version_and_original_thai(use_client):
    use_client(respond_with(GOOD))
    results = gpt_teacher.analyze_long_text(transcript("มาแล้ว"))
    assert results[0]["thai"] == "มาแล้ว"
    assert results[0]["v"] == storage.ANALYSIS_VERSION
    assert [item["word"] for item in results[0]["analysis"]] == ["มา", "แล้ว"]
    assert "resent" not in results[0]


def test_blank_words_are_dropped(use_client):
    use_client(respond_with({"มาแล้ว": [("มา", "word"), ("  ", "word"), ("แล้ว", "word")]}))
    results = gpt_teacher.analyze_long_text(transcript("มาแล้ว"))
    assert [item["word"] for item in results[0]["analysis"]] == ["มา", "แล้ว"]


def test_empty_lines_are_not_sent(use_client):
    client = use_client(respond_with(GOOD))
    results = gpt_teacher.analyze_long_text(transcript("มาแล้ว", "   "))
    assert list(results) == [0]
    assert len(client.calls) == 1


# 快取


def test_current_cache_is_reused_without_calling_openai(no_client):
    cached = {0: {"thai": "มาแล้ว", "v": storage.ANALYSIS_VERSION, **result(GOOD["มาแล้ว"])}}
    assert gpt_teacher.analyze_long_text(transcript("มาแล้ว"), cached=cached) == cached


def test_old_version_cache_is_analyzed_again(use_client):
    client = use_client(respond_with(GOOD))
    cached = {0: {"thai": "มาแล้ว", **result(GOOD["มาแล้ว"])}}
    results = gpt_teacher.analyze_long_text(transcript("มาแล้ว"), cached=cached)
    assert len(client.calls) == 1
    assert results[0]["v"] == storage.ANALYSIS_VERSION


def test_cache_for_changed_text_is_analyzed_again(use_client):
    client = use_client(respond_with(GOOD))
    cached = {0: {"thai": "ไม่เป็นไรค่ะ", "v": storage.ANALYSIS_VERSION, **result(GOOD["ไม่เป็นไรค่ะ"])}}
    gpt_teacher.analyze_long_text(transcript("มาแล้ว"), cached=cached)
    assert len(client.calls) == 1


# 檢查後重送


def test_failed_sentence_is_resent_alone_and_replaced(use_client):
    attempts = []

    def respond(payload):
        attempts.append([item["thai"] for item in payload.values()])
        table = BAD if len(attempts) == 1 else GOOD
        return {key: result(table[item["thai"]] if item["thai"] == "มาแล้ว" else GOOD[item["thai"]]) for key, item in payload.items()}

    use_client(respond)
    stats = {}
    results = gpt_teacher.analyze_long_text(transcript("ไม่เป็นไรค่ะ", "มาแล้ว"), stats=stats)
    assert attempts == [["ไม่เป็นไรค่ะ", "มาแล้ว"], ["มาแล้ว"]]
    assert [item["word"] for item in results[1]["analysis"]] == ["มา", "แล้ว"]
    assert "resent" not in results[1]
    assert stats == {"first_failed": 1, "still_failed": 0}


def test_sentence_failing_twice_keeps_first_result_and_is_not_resent_again(use_client, monkeypatch):
    client = use_client(respond_with(BAD))
    stats = {}
    results = gpt_teacher.analyze_long_text(transcript("มาแล้ว"), stats=stats)
    assert len(client.calls) == 2
    assert [item["word"] for item in results[0]["analysis"]] == ["มา"]
    assert results[0]["resent"] is True
    assert stats == {"first_failed": 1, "still_failed": 1}

    # 重跑時這一句已經重送過，不再花錢
    def fail(**kwargs):
        raise AssertionError("不應該呼叫 OpenAI")

    monkeypatch.setattr(gpt_teacher, "OpenAI", fail)
    assert gpt_teacher.analyze_long_text(transcript("มาแล้ว"), cached=results) == results


def test_cached_failure_that_was_never_resent_is_resent(use_client):
    # 上次在第一輪和重送之間中斷：快取裡有沒通過檢查、也還沒重送過的結果
    client = use_client(respond_with(GOOD))
    cached = {0: {"thai": "มาแล้ว", "v": storage.ANALYSIS_VERSION, **result(BAD["มาแล้ว"])}}
    results = gpt_teacher.analyze_long_text(transcript("มาแล้ว"), cached=cached)
    assert len(client.calls) == 1
    assert [item["word"] for item in results[0]["analysis"]] == ["มา", "แล้ว"]


def test_progress_is_reported_with_results_and_total(use_client):
    use_client(respond_with(GOOD))
    seen = []
    gpt_teacher.analyze_long_text(
        transcript("มาแล้ว", "ไม่เป็นไรค่ะ"), on_progress=lambda results, total: seen.append((len(results), total))
    )
    assert seen[0] == (0, 2)
    assert seen[-1] == (2, 2)


def test_resend_without_a_response_is_tried_again_on_the_next_run(use_client):
    attempts = []

    def respond(payload):
        attempts.append(len(payload))
        if len(attempts) == 2:
            raise RuntimeError("網路斷線")
        return respond_with(BAD if len(attempts) == 1 else GOOD)(payload)

    use_client(respond)
    stats = {}
    results = gpt_teacher.analyze_long_text(transcript("มาแล้ว"), stats=stats)
    assert "resent" not in results[0]
    assert stats == {"first_failed": 1, "still_failed": 1}

    # 下次重跑會再重送一次，這次有回應就換成正確的拆法
    results = gpt_teacher.analyze_long_text(transcript("มาแล้ว"), cached=results)
    assert attempts == [1, 1, 1]
    assert [item["word"] for item in results[0]["analysis"]] == ["มา", "แล้ว"]


def test_symbol_only_line_is_analyzed_once_and_never_resent(use_client, monkeypatch):
    client = use_client(lambda payload: {key: result([]) for key in payload})
    stats = {}
    results = gpt_teacher.analyze_long_text(transcript("♪♪"), stats=stats)
    assert len(client.calls) == 1
    assert results[0]["analysis"] == []
    assert stats == {"first_failed": 0, "still_failed": 0}

    def fail(**kwargs):
        raise AssertionError("不應該呼叫 OpenAI")

    monkeypatch.setattr(gpt_teacher, "OpenAI", fail)
    assert gpt_teacher.analyze_long_text(transcript("♪♪"), cached=results) == results
