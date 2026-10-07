from backend import elevenlabs_api, storage
from backend.elevenlabs_api import (
    backfill_speakers,
    generate_transcript_json,
    merge_zero_length_segments,
    segment_speakers,
)

VIDEO_ID = "aaaaaaaaaaa"


def seg(text, start, duration):
    return {"text": text, "start": start, "duration": duration, "start_time": ""}


def words(*parts):
    """parts 是 (文字, 講者)；和 ElevenLabs 一樣，泰文一個字元一筆"""
    return [
        {"text": char, "type": "spacing" if char == " " else "word", "speaker_id": speaker}
        for text, speaker in parts
        for char in text
    ]


def texts(segments):
    return [s["text"] for s in segments]


def test_segment_speakers_gives_first_and_last_speaker_of_each_line():
    segments = [seg("กาข", 0, 1), seg("ค", 1, 1)]
    assert segment_speakers(segments, words(("กา", "a"), ("ข", "b"), ("ค", "b"))) == [("a", "b"), ("b", "b")]


def test_segment_speakers_ignores_spacing():
    segments = [seg("Hi there", 0, 1), seg("กา", 1, 1)]
    assert segment_speakers(segments, words(("Hi there", "a"), (" ", "a"), ("กา", "b"))) == [("a", "a"), ("b", "b")]


def test_segment_speakers_is_none_for_a_line_missing_from_words():
    segments = [seg("กา", 0, 1), seg("xyz", 1, 1), seg("ขา", 2, 1)]
    assert segment_speakers(segments, words(("กา", "a"), ("ขา", "b"))) == [("a", "a"), None, ("b", "b")]


def test_tail_of_previous_speaker_joins_previous_line():
    segments = [seg("อะไรอย่าง", 31.82, 3.7), seg("งี้", 35.52, 0), seg("ใช่", 35.52, 2.2)]
    speakers = [("1", "1"), ("1", "1"), ("0", "0")]
    assert merge_zero_length_segments(segments, speakers) == [seg("อะไรอย่างงี้", 31.82, 3.7), seg("ใช่", 35.52, 2.2)]


def test_head_of_next_speaker_joins_next_line():
    segments = [seg("เท่าไหร่", 343.44, 0.84), seg("ห้า", 344.28, 0), seg("สิบ", 344.5, 1.0)]
    speakers = [("1", "1"), ("0", "0"), ("0", "0")]
    assert merge_zero_length_segments(segments, speakers) == [seg("เท่าไหร่", 343.44, 0.84), seg("ห้าสิบ", 344.5, 1.0)]


def test_interjection_from_another_speaker_stays_on_its_own_row():
    segments = [seg("หลับ", 159.66, 3.74), seg("ใช่", 163.56, 0), seg("หลับได้เลย", 163.56, 0.62)]
    speakers = [("1", "1"), ("0", "0"), ("1", "1")]
    assert texts(merge_zero_length_segments(segments, speakers)) == ["หลับ", "ใช่\nหลับได้เลย"]


def test_tail_then_interjection():
    segments = [seg("อะไรอย่าง", 31.82, 3.7), seg("งี้", 35.52, 0), seg("อือ", 35.52, 0), seg("ใช่", 35.52, 2.2)]
    speakers = [("1", "1"), ("1", "1"), ("0", "0"), ("1", "1")]
    assert texts(merge_zero_length_segments(segments, speakers)) == ["อะไรอย่างงี้", "อือ\nใช่"]


def test_same_speaker_on_both_sides_goes_to_next_line():
    segments = [seg("กา", 0, 1), seg("ขา", 1, 0), seg("คา", 1, 1)]
    speakers = [("0", "0"), ("0", "0"), ("0", "0")]
    assert texts(merge_zero_length_segments(segments, speakers)) == ["กา", "ขา\nคา"]


def test_unknown_speaker_goes_to_next_line():
    segments = [seg("กา", 0, 1), seg("ขา", 1, 0), seg("คา", 1, 1)]
    assert texts(merge_zero_length_segments(segments, [("0", "0"), None, ("1", "1")])) == ["กา", "ขา\nคา"]
    assert texts(merge_zero_length_segments(segments)) == ["กา", "ขา\nคา"]


def test_zero_length_line_before_a_later_line_is_shown_until_then():
    segments = [seg("กา", 0, 1), seg("ขา", 1, 0), seg("คา", 1.5, 1)]
    assert merge_zero_length_segments(segments) == [seg("กา", 0, 1), seg("ขา", 1, 0.5), seg("คา", 1.5, 1)]


def test_transcript_uses_speakers_from_saved_response(data_dir):
    srt = (
        "1\n00:00:31,820 --> 00:00:35,520\nอ ย่ า ง\n\n"
        "2\n00:00:35,520 --> 00:00:35,520\nงี้\n\n"
        "3\n00:00:35,520 --> 00:00:37,720\nใ ช่\n"
    )
    storage.save_json_file(
        storage.elevenlabs_file(VIDEO_ID),
        {
            "words": words(("อย่าง", "speaker_1"), ("งี้", "speaker_1"), ("ใช่", "speaker_0")),
            "additional_formats": [{"content": srt}],
        },
    )

    transcript, whole_script = generate_transcript_json(VIDEO_ID)

    assert texts(transcript.values()) == ["อย่างงี้", "ใช่"]
    assert whole_script == "อย่างงี้\nใช่\n"


def test_joining_a_tail_keeps_the_row_break_of_an_earlier_interjection():
    segments = [seg("กา", 0, 1), seg("อือ", 1, 0), seg("ขา", 1, 1), seg("ค", 2, 0), seg("งา", 2, 1)]
    speakers = [("0", "0"), ("1", "1"), ("0", "0"), ("0", "0"), ("1", "1")]
    assert texts(merge_zero_length_segments(segments, speakers)) == ["กา", "อือ\nขาค", "งา"]


def test_english_fragment_is_joined_with_a_space():
    segments = [seg("thank", 0, 1), seg("you", 1, 0), seg("ครับ", 1, 1)]
    speakers = [("0", "0"), ("0", "0"), ("1", "1")]
    assert texts(merge_zero_length_segments(segments, speakers)) == ["thank you", "ครับ"]


def spoken(text, start, duration, *speakers):
    return {**seg(text, start, duration), "speakers": list(speakers)}


def save_response(srt, *parts):
    storage.save_json_file(
        storage.elevenlabs_file(VIDEO_ID),
        {"words": words(*parts), "additional_formats": [{"content": srt}]},
    )


INTERJECTION_SRT = (
    "1\n00:00:00,000 --> 00:00:01,000\nห ลั บ\n\n"
    "2\n00:00:01,000 --> 00:00:01,000\nใ ช่\n\n"
    "3\n00:00:01,000 --> 00:00:02,000\nไ ด้\n"
)


def test_transcript_lines_carry_their_speaker(data_dir):
    srt = "1\n00:00:00,000 --> 00:00:01,000\nก า\n\n2\n00:00:01,000 --> 00:00:02,000\nข า\n"
    save_response(srt, ("กา", "speaker_1"), ("ขา", "speaker_0"))

    transcript, _ = generate_transcript_json(VIDEO_ID)

    assert [line["speakers"] for line in transcript.values()] == [["speaker_1"], ["speaker_0"]]


def test_transcript_without_speaker_data_has_no_speakers(data_dir):
    storage.save_json_file(
        storage.elevenlabs_file(VIDEO_ID),
        {"additional_formats": [{"content": "1\n00:00:00,000 --> 00:00:01,000\nก า\n"}]},
    )

    transcript, _ = generate_transcript_json(VIDEO_ID)

    assert "speakers" not in transcript[0]


def test_interjection_row_has_one_speaker_per_text_line(data_dir):
    save_response(INTERJECTION_SRT, ("หลับ", "speaker_1"), ("ใช่", "speaker_0"), ("ได้", "speaker_1"))

    transcript, _ = generate_transcript_json(VIDEO_ID)

    assert texts(transcript.values()) == ["หลับ", "ใช่\nได้"]
    assert transcript[1]["speakers"] == ["speaker_0", "speaker_1"]


def test_joined_fragment_keeps_the_speaker_of_the_line_it_joins():
    segments = [spoken("อย่าง", 0, 1, "1"), spoken("งี้", 1, 0, "1"), spoken("ใช่", 1, 1, "0")]
    speakers = [("1", "1"), ("1", "1"), ("0", "0")]
    assert merge_zero_length_segments(segments, speakers) == [spoken("อย่างงี้", 0, 1, "1"), spoken("ใช่", 1, 1, "0")]


def test_zero_length_rows_stacked_before_a_later_line_keep_each_speaker():
    segments = [spoken("กา", 0, 1, "0"), spoken("ขา", 1, 0, "1"), spoken("คา", 1, 0, "0"), spoken("งา", 1.5, 1, "1")]
    speakers = [("0", "0"), ("1", "1"), ("0", "0"), ("1", "1")]
    assert merge_zero_length_segments(segments, speakers)[1] == spoken("ขา\nคา", 1, 0.5, "1", "0")


def test_backfill_adds_speakers_to_saved_transcript_and_subtitles(data_dir):
    save_response(INTERJECTION_SRT, ("หลับ", "speaker_1"), ("ใช่", "speaker_0"), ("ได้", "speaker_1"))
    saved = {"0": seg("หลับ", 0, 1), "1": seg("ใช่\nได้", 1, 1)}
    storage.save_json_file(storage.transcript_file(VIDEO_ID), saved)
    storage.save_json_file(storage.subtitle_file(VIDEO_ID), {"0": {**saved["0"], "explanation": {"v": 2}}, "1": saved["1"]})

    assert backfill_speakers(VIDEO_ID) == 4

    transcript = storage.load_json_file(storage.transcript_file(VIDEO_ID))
    subtitles = storage.load_json_file(storage.subtitle_file(VIDEO_ID))
    assert [line["speakers"] for line in transcript.values()] == [["speaker_1"], ["speaker_0", "speaker_1"]]
    assert subtitles["0"] == {**saved["0"], "explanation": {"v": 2}, "speakers": ["speaker_1"]}


def test_backfill_skips_lines_whose_text_no_longer_matches(data_dir):
    save_response(INTERJECTION_SRT, ("หลับ", "speaker_1"), ("ใช่", "speaker_0"), ("ได้", "speaker_1"))
    storage.save_json_file(storage.subtitle_file(VIDEO_ID), {"0": seg("หลับ", 0, 1), "1": seg("อื่น", 1, 1)})

    assert backfill_speakers(VIDEO_ID) == 1

    subtitles = storage.load_json_file(storage.subtitle_file(VIDEO_ID))
    assert subtitles["0"]["speakers"] == ["speaker_1"]
    assert "speakers" not in subtitles["1"]


def test_backfill_is_a_no_op_when_run_again(data_dir):
    save_response(INTERJECTION_SRT, ("หลับ", "speaker_1"), ("ใช่", "speaker_0"), ("ได้", "speaker_1"))
    storage.save_json_file(storage.subtitle_file(VIDEO_ID), {"0": seg("หลับ", 0, 1)})

    backfill_speakers(VIDEO_ID)

    assert backfill_speakers(VIDEO_ID) == 0


def test_audio_event_tags_are_left_out_of_the_transcript(data_dir):
    srt = (
        "1\n00:00:00,000 --> 00:00:01,000\nก า [เสียงหัวเราะ]\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\n[เสียงหัวเราะ]\n\n"
        "3\n00:00:02,000 --> 00:00:03,000\nข า\n"
    )
    laughter = {"text": "[เสียงหัวเราะ]", "type": "audio_event", "speaker_id": "speaker_0"}
    storage.save_json_file(
        storage.elevenlabs_file(VIDEO_ID),
        {
            "words": words(("กา", "speaker_0")) + [laughter, laughter] + words(("ขา", "speaker_1")),
            "additional_formats": [{"content": srt}],
        },
    )

    transcript, whole_script = generate_transcript_json(VIDEO_ID)

    assert texts(transcript.values()) == ["กา", "ขา"]
    assert [line["speakers"] for line in transcript.values()] == [["speaker_0"], ["speaker_1"]]
    assert whole_script == "กา\nขา\n"


def test_refetch_ignores_the_saved_response(data_dir, monkeypatch):
    save_response("1\n00:00:00,000 --> 00:00:01,000\nก า\n", ("กา", "speaker_0"))
    fresh = {"words": [], "additional_formats": [{"content": "1\n00:00:00,000 --> 00:00:01,000\nข า\n"}]}
    monkeypatch.setattr(elevenlabs_api, "request_ele_api", lambda video_id: fresh)

    assert texts(generate_transcript_json(VIDEO_ID)[0].values()) == ["กา"]
    assert texts(generate_transcript_json(VIDEO_ID, refetch=True)[0].values()) == ["ขา"]
