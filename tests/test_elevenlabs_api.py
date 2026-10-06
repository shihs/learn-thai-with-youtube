from backend import storage
from backend.elevenlabs_api import generate_transcript_json, merge_zero_length_segments, segment_speakers

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
