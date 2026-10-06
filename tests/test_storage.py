from backend import storage

VIDEO_ID = "aaaaaaaaaaa"
CURRENT = {"thai": "มา", "v": storage.ANALYSIS_VERSION, "analysis": []}
OLD = {"thai": "มา", "analysis": []}
PARTIAL = {**CURRENT, "partial": True}


def save_subtitles(*explanations):
    lines = {str(index): {"text": "มา", "explanation": e} for index, e in enumerate(explanations)}
    lines[str(len(lines))] = {"text": "   "}  # 沒有內容的字幕不需要解析
    storage.save_json_file(storage.subtitle_file(VIDEO_ID), lines)


def test_is_current_explanation():
    assert storage.is_current_explanation(CURRENT)
    assert not storage.is_current_explanation(OLD)
    assert not storage.is_current_explanation(PARTIAL)
    assert not storage.is_current_explanation(None)


def test_complete_when_every_line_is_current(data_dir):
    save_subtitles(CURRENT, CURRENT)
    assert storage.is_subtitle_complete(VIDEO_ID)


def test_incomplete_with_old_version(data_dir):
    save_subtitles(CURRENT, OLD)
    assert not storage.is_subtitle_complete(VIDEO_ID)


def test_incomplete_with_partial_line(data_dir):
    save_subtitles(CURRENT, PARTIAL)
    assert not storage.is_subtitle_complete(VIDEO_ID)


def test_incomplete_when_a_line_has_no_explanation(data_dir):
    storage.save_json_file(storage.subtitle_file(VIDEO_ID), {"0": {"text": "มา"}})
    assert not storage.is_subtitle_complete(VIDEO_ID)


def test_list_counts_only_current_explanations(data_dir):
    save_subtitles(CURRENT, OLD, PARTIAL)
    (video,) = storage.list_subtitle_videos()
    assert video["lines"] == 3
    assert video["explained"] == 1


def test_dictionary_file_is_inside_data_dir(data_dir):
    assert storage.dictionary_file() == f"{data_dir}/dictionary.json"
