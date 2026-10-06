import pytest

from backend import gpt_teacher
from backend.dictionary import add_entries, load_dictionary
from tests.conftest import FakeClient


def entry_for(word):
    return {"rtgs": "rtgs", "parts": [], "senses": "意思", "usage": "用法"}


def respond(payload):
    return {key: entry_for(item["word"]) for key, item in payload.items()}


@pytest.fixture
def use_client(monkeypatch):
    def install(respond_function):
        client = FakeClient(respond_function)
        monkeypatch.setattr(gpt_teacher, "OpenAI", lambda **kwargs: client)
        return client

    return install


def test_words_are_looked_up_and_saved(data_dir, use_client):
    client = use_client(respond)
    left = gpt_teacher.lookup_missing_words({"มา": "มาแล้ว", "แล้ว": "มาแล้ว"})
    assert left == 0
    assert load_dictionary() == {"มา": entry_for("มา"), "แล้ว": entry_for("แล้ว")}
    assert client.calls == [
        {"item_1": {"word": "มา", "example": "มาแล้ว"}, "item_2": {"word": "แล้ว", "example": "มาแล้ว"}}
    ]


def test_words_are_sent_in_batches_of_forty(data_dir, use_client):
    client = use_client(respond)
    missing = {f"ก{index}": "例句" for index in range(45)}
    progress = []
    left = gpt_teacher.lookup_missing_words(missing, on_progress=lambda done, total: progress.append((done, total)))
    assert left == 0
    assert sorted(len(call) for call in client.calls) == [5, 40]
    assert len(load_dictionary()) == 45
    assert progress[-1] == (45, 45)


def test_nothing_to_look_up_does_not_call_openai(data_dir, monkeypatch):
    def fail(**kwargs):
        raise AssertionError("不應該呼叫 OpenAI")

    monkeypatch.setattr(gpt_teacher, "OpenAI", fail)
    assert gpt_teacher.lookup_missing_words({}) == 0


def test_failed_batch_is_retried_once(data_dir, use_client):
    attempts = []

    def flaky(payload):
        attempts.append(len(payload))
        if len(attempts) == 1:
            raise RuntimeError("網路斷線")
        return respond(payload)

    use_client(flaky)
    assert gpt_teacher.lookup_missing_words({"มา": "มาแล้ว"}) == 0
    assert attempts == [1, 1]
    assert "มา" in load_dictionary()


def test_words_that_keep_failing_are_reported_and_do_not_crash(data_dir, use_client):
    def broken(payload):
        raise RuntimeError("網路斷線")

    client = use_client(broken)
    assert gpt_teacher.lookup_missing_words({"มา": "มาแล้ว", "แล้ว": "มาแล้ว"}) == 2
    assert len(client.calls) == 2
    assert load_dictionary() == {}


def test_existing_dictionary_words_are_kept(data_dir, use_client):
    add_entries({"มา": {"rtgs": "ma", "parts": [], "senses": "來", "usage": ""}})
    use_client(respond)
    gpt_teacher.lookup_missing_words({"มา": "มาแล้ว"})
    assert load_dictionary()["มา"]["rtgs"] == "ma"


def test_non_rtgs_romanization_is_looked_up_again(data_dir, use_client):
    attempts = []

    def respond_badly_once(payload):
        attempts.append([item["word"] for item in payload.values()])
        results = respond(payload)
        if len(attempts) == 1:
            key = next(key for key, item in payload.items() if item["word"] == "กระเป๋า")
            results[key]["rtgs"] = "grà-bpǎo"
        return results

    use_client(respond_badly_once)
    assert gpt_teacher.lookup_missing_words({"มา": "มาแล้ว", "กระเป๋า": "กระเป๋า"}) == 0
    assert attempts == [["มา", "กระเป๋า"], ["กระเป๋า"]]
    assert load_dictionary()["กระเป๋า"]["rtgs"] == "rtgs"


def test_romanization_still_marked_after_the_retry_is_stored_without_marks(data_dir, use_client):
    def respond_badly(payload):
        results = respond(payload)
        for key in results:
            results[key]["rtgs"] = "krà-jòk"
            results[key]["parts"] = [{"word": "กระ", "rtgs": "krà", "meaning": "前綴"}]
        return results

    client = use_client(respond_badly)
    assert gpt_teacher.lookup_missing_words({"กระจก": "กระจก"}) == 0
    assert len(client.calls) == 2
    saved = load_dictionary()["กระจก"]
    assert saved["rtgs"] == "kra jok"
    assert saved["parts"] == [{"word": "กระ", "rtgs": "kra", "meaning": "前綴"}]


def test_dictionary_prompt_spells_out_the_romanization_rules():
    prompt = gpt_teacher.build_dictionary_prompt({"item_1": {"word": "มา", "example": "มาแล้ว"}})
    assert "不加聲調符號" in prompt
    assert "krapao" in prompt
