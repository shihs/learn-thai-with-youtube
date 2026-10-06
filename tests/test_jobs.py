import pytest

from backend import gpt_teacher, jobs, storage
from backend.dictionary import add_entries
from tests.conftest import FakeClient

VIDEO_ID = "aaaaaaaaaaa"
ANALYSES = {
    "มาแล้ว": [("มา", "word"), ("แล้ว", "word")],
    "ไม่เป็นไรค่ะ": [("ไม่เป็นไร", "expression"), ("ค่ะ", "particle")],
}


def entry_for(word):
    return {"rtgs": "rtgs", "parts": [], "senses": "意思", "usage": "用法"}


def respond(payload, skip=()):
    """同一個假 client 同時回答逐句解析（有 thai）和查詞（有 word）；skip 裡的字查詞時會失敗"""
    results = {}
    for key, item in payload.items():
        if "thai" in item:
            results[key] = {
                "rtgs": "rtgs",
                "translation": "翻譯",
                "analysis": [
                    {"word": word, "type": kind, "meaning": "意思", "more": ""} for word, kind in ANALYSES[item["thai"]]
                ],
            }
        elif item["word"] in skip:
            raise RuntimeError("網路斷線")
        else:
            results[key] = entry_for(item["word"])
    return results


@pytest.fixture
def video(data_dir):
    storage.save_json_file(
        storage.transcript_file(VIDEO_ID),
        {"0": {"text": "มาแล้ว", "start": 0}, "1": {"text": "ไม่เป็นไรค่ะ", "start": 1}, "2": {"text": " ", "start": 2}},
    )
    jobs.jobs.clear()
    jobs.start_job(VIDEO_ID)
    yield
    jobs.jobs.clear()


def install(monkeypatch, respond_function):
    client = FakeClient(respond_function)
    monkeypatch.setattr(gpt_teacher, "OpenAI", lambda **kwargs: client)
    return client


def saved_subtitles():
    return storage.load_json_file(storage.subtitle_file(VIDEO_ID))


def test_subtitles_are_saved_with_sentence_and_dictionary_fields(video, monkeypatch):
    install(monkeypatch, respond)
    jobs.long_analyze_and_save(VIDEO_ID)

    subtitles = saved_subtitles()
    assert subtitles["0"]["start"] == 0
    assert subtitles["0"]["explanation"]["analysis"][0] == {
        "word": "มา",
        "type": "word",
        "meaning": "意思",
        "more": "",
        "rtgs": "rtgs",
        "parts": [],
        "senses": "意思",
        "usage": "用法",
    }
    assert "explanation" not in subtitles["2"]
    assert storage.is_subtitle_complete(VIDEO_ID)
    assert jobs.jobs[VIDEO_ID] == {"status": "done", "stage": "done", "done": 2, "total": 2, "message": ""}


def test_known_words_are_not_looked_up_again(video, monkeypatch):
    add_entries({word: entry_for(word) for word in ("มา", "แล้ว", "ไม่เป็นไร")})
    client = install(monkeypatch, respond)
    jobs.long_analyze_and_save(VIDEO_ID)

    lookups = [call for call in client.calls if "word" in call["item_1"]]
    assert lookups == [{"item_1": {"word": "ค่ะ", "example": "ไม่เป็นไรค่ะ"}}]


def test_failed_lookup_leaves_partial_lines_and_a_hint(video, monkeypatch):
    install(monkeypatch, lambda payload: respond(payload, skip=("มา", "แล้ว", "ไม่เป็นไร", "ค่ะ")))
    jobs.long_analyze_and_save(VIDEO_ID)

    subtitles = saved_subtitles()
    assert subtitles["0"]["explanation"]["partial"] is True
    assert subtitles["0"]["explanation"]["analysis"][0]["meaning"] == "意思"
    assert not storage.is_subtitle_complete(VIDEO_ID)
    assert jobs.jobs[VIDEO_ID]["status"] == "done"
    assert "2 句的單字還沒有詞庫資料" in jobs.jobs[VIDEO_ID]["message"]


def test_rerun_after_failed_lookup_only_looks_up_words(video, monkeypatch):
    install(monkeypatch, lambda payload: respond(payload, skip=("มา", "แล้ว", "ไม่เป็นไร", "ค่ะ")))
    jobs.long_analyze_and_save(VIDEO_ID)

    _, should_run = jobs.start_job(VIDEO_ID)
    assert should_run
    client = install(monkeypatch, respond)
    jobs.long_analyze_and_save(VIDEO_ID)

    assert all("word" in call["item_1"] for call in client.calls)  # 沒有重新解析句子
    assert storage.is_subtitle_complete(VIDEO_ID)
    assert "partial" not in saved_subtitles()["0"]["explanation"]
    assert jobs.jobs[VIDEO_ID]["message"] == ""


def test_dictionary_stage_is_reported(video, monkeypatch):
    stages = []

    def recording(payload):
        stages.append(dict(jobs.jobs[VIDEO_ID]))
        return respond(payload)

    install(monkeypatch, recording)
    jobs.long_analyze_and_save(VIDEO_ID)

    assert stages[-1] == {"status": "running", "stage": "dictionary", "done": 0, "total": 4, "message": "建立詞庫中"}


def test_fatal_error_during_lookup_keeps_paid_analysis_for_the_rerun(video, monkeypatch):
    class OutOfQuota(Exception):
        pass

    def respond_until_lookup(payload):
        if "word" in payload["item_1"]:
            raise OutOfQuota("額度用完")
        return respond(payload)

    monkeypatch.setattr(gpt_teacher, "is_fatal_error", lambda e: isinstance(e, OutOfQuota))
    install(monkeypatch, respond_until_lookup)
    jobs.run_job(VIDEO_ID)

    assert jobs.jobs[VIDEO_ID]["status"] == "error"
    assert len(storage.load_gpt_cache(VIDEO_ID)) == 2

    _, should_run = jobs.start_job(VIDEO_ID)
    assert should_run
    client = install(monkeypatch, respond)
    jobs.run_job(VIDEO_ID)

    assert all("word" in call["item_1"] for call in client.calls)  # 句子沒有重新付費
    assert jobs.jobs[VIDEO_ID]["status"] == "done"
    assert storage.is_subtitle_complete(VIDEO_ID)
