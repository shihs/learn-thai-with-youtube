from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
import json
import os
import re

from .storage import elevenlabs_file, load_json_file, save_json_file, subtitle_file, transcript_file

load_dotenv()

# SRT 會在每個泰文字元之間插入空格，只移除泰文與泰文之間的空格，保留英文單字間的空格
THAI_SPACING = re.compile(r"(?<=[\u0E00-\u0E7F])\s+(?=[\u0E00-\u0E7F])")


def to_seconds(ts: str) -> float:
    h, m, s = ts.replace(',', '.').split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)


def request_ele_api(video_id):

    elevenlabs = ElevenLabs(
        api_key=os.getenv("ELEVENLABS_API_KEY"),
    )

    audio_url = (
        "https://www.youtube.com/watch?v=" + video_id
    )


    transcription = elevenlabs.speech_to_text.convert(
        source_url=audio_url,
        model_id="scribe_v2", # Model to use
        tag_audio_events=True, # Tag audio events like laughter, applause, etc.
        language_code="tha", # Language of the audio file. If set to None, the model will detect the language automatically.
        diarize=True, # Whether to annotate who is speaking,
        timestamps_granularity=None, # The granularity of the timestamps in the transcription.
        additional_formats= [{"format": "srt", "include_timestamps": True}]
    )


    # transcription.json() 回傳的是字串，先轉回 dict 再存，檔案才不會被編碼兩次
    thai_script = json.loads(transcription.json())

    save_json_file(elevenlabs_file(video_id), thai_script)

    return thai_script


def load_or_request_transcription(video_id, refetch=False):
    """refetch：不用存過的回應，重新付費轉錄；成功後才會蓋掉舊的"""
    thai_script = None if refetch else load_json_file(elevenlabs_file(video_id))
    if thai_script is not None:
        print(f"使用已存在的 ElevenLabs 轉錄結果：{elevenlabs_file(video_id)}")
        return thai_script

    print(f"呼叫 ElevenLabs API 轉錄 {video_id}......")
    return request_ele_api(video_id)


# 零長度字幕找不到下一句可合併時，最多顯示這麼久（秒）
MAX_ZERO_LENGTH_DURATION = 2.0


def segment_speakers(segments, words):
    """
    SRT 沒有講者，講者只在原始回應的 words 裡（泰文一個字元一筆）。
    把每句字幕對回 words，回傳 (第一個字的講者, 最後一個字的講者)；對不上的是 None。
    """
    owners = []
    for word in words:
        if word.get("type") == "word":
            owners += [word.get("speaker_id")] * len(re.sub(r"\s+", "", word["text"]))
    spoken = "".join(re.sub(r"\s+", "", word["text"]) for word in words if word.get("type") == "word")

    speakers = []
    position = 0
    for seg in segments:
        text = re.sub(r"\s+", "", seg["text"])
        found = spoken.find(text, position) if text else -1
        if found < 0:
            speakers.append(None)
            continue
        position = found + len(text)
        speakers.append((owners[found], owners[position - 1]))
    return speakers


THAI_CHAR = re.compile(r"[฀-๿]")


def join_text(first, second):
    """把切開的兩段接回同一句：泰文直接相連，其他情況以空格分隔"""
    if THAI_CHAR.match(first[-1:]) and THAI_CHAR.match(second[:1]):
        return first + second
    return f"{first} {second}"


def stacked(rows):
    """同時開始的幾句疊成同一列：文字以換行分隔，有講者的話一行一位"""
    fields = {"text": "\n".join(row["text"] for row in rows)}
    if any("speakers" in row for row in rows):
        fields["speakers"] = [speaker for row in rows for speaker in row.get("speakers", [None])]
    return fields


def merge_zero_length_segments(segments, speakers=None):
    """
    換講者的地方，ElevenLabs 會給出起訖時間相同的字幕，前端永遠顯示不到。
    有講者資訊時先看它是誰講的：
    - 和前一句同講者、和下一句不同：是前一句被切下來的句尾，直接接回前一句
    - 和下一句同講者、和前一句不同：是下一句被切下來的句首，直接接到下一句開頭
    其餘（另一個人的插話，或分不出來）和下一句同時開始，所以併進下一句（以換行分隔）；
    若下一句較晚開始，則獨立成一句並延長到下一句開始為止。
    """
    if speakers is None:
        speakers = [None] * len(segments)

    def same_speaker(earlier, later):
        if not 0 <= earlier < later < len(segments) or not speakers[earlier] or not speakers[later]:
            return False
        return speakers[earlier][1] == speakers[later][0]

    merged = []
    pending = []
    prefix = ""

    def flush(until=None):
        duration = MAX_ZERO_LENGTH_DURATION
        if until is not None:
            duration = min(duration, round(until - pending[0]["start"], 3))
        merged.append({**pending[0], **stacked(pending), "duration": duration})
        pending.clear()

    for index, seg in enumerate(segments):
        if prefix:
            seg = {**seg, "text": join_text(prefix, seg["text"])}
            prefix = ""

        if seg["duration"] <= 0:
            from_previous = same_speaker(index - 1, index)
            from_next = same_speaker(index, index + 1)
            if from_next and not from_previous:
                prefix = seg["text"]
                continue
            if from_previous and not from_next:
                target = pending if pending else merged
                target[-1] = {**target[-1], "text": join_text(target[-1]["text"], seg["text"])}
                continue

        if pending and seg["start"] != pending[0]["start"]:
            flush(until=seg["start"])

        if seg["duration"] <= 0:
            pending.append(seg)
            continue

        if pending:
            seg = {**seg, **stacked(pending + [seg])}
            pending.clear()
        merged.append(seg)

    if pending:
        flush()

    return merged


def generate_transcript_json(video_id, refetch=False):

    thai_script = load_or_request_transcription(video_id, refetch)

    content = thai_script["additional_formats"][0]["content"]
    words = thai_script.get("words") or []

    # tag_audio_events 開啟時字幕裡會夾著 [เสียงหัวเราะ] 這類音效標記：不是台詞，不顯示也不送去解析
    audio_events = {word["text"] for word in words if word.get("type") == "audio_event"}

    # 每個 SRT 區塊：序號 / 時間軸 / 一到多行文字，區塊之間以空行分隔
    segments = []
    for block in re.split(r"\n\s*\n", content.strip()):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        timing = next((n for n, line in enumerate(lines) if "-->" in line), None)
        if timing is None:
            continue

        start_time, end_time = [t.strip() for t in lines[timing].split("-->")]
        text = THAI_SPACING.sub("", " ".join(lines[timing + 1 :]))
        for event in audio_events:
            text = text.replace(event, " ")
        text = " ".join(text.split())
        if not text:
            continue

        start = to_seconds(start_time)
        segments.append(
            {
                "text": text,
                "start": round(start, 3),
                "duration": round(to_seconds(end_time) - start, 3),
                "start_time": start_time,
            }
        )

    # key 與 YouTube 字幕路徑一致：從 0 開始的整數
    speakers = segment_speakers(segments, words)
    # 每句記下講者給前端標示（一句裡換人講時記開頭那位）；完全沒有講者資訊就不加這個欄位
    if any(speakers):
        for seg, speaker in zip(segments, speakers):
            seg["speakers"] = [speaker[0] if speaker else None]
    transcript_with_time = dict(enumerate(merge_zero_length_segments(segments, speakers)))

    whole_script = ""
    for snippet in transcript_with_time.values():
        whole_script += snippet["text"] + "\n"

    return transcript_with_time, whole_script


def backfill_speakers(video_id):
    """
    用已存的 ElevenLabs 回應，把講者補進之前存好的字幕（不會呼叫 API，也不動解析）。
    回傳補上的句數；文字和重新產生的結果對不上的句子不動。
    """
    if load_json_file(elevenlabs_file(video_id)) is None:
        return 0

    transcript, _ = generate_transcript_json(video_id)
    fresh = {str(line_id): line for line_id, line in transcript.items()}

    updated = 0
    for file_name in (transcript_file(video_id), subtitle_file(video_id)):
        saved = load_json_file(file_name)
        if not isinstance(saved, dict):
            continue
        changed = 0
        for line_id, line in saved.items():
            source = fresh.get(line_id, {})
            if "speakers" not in source or source["text"] != line.get("text"):
                continue
            if line.get("speakers") != source["speakers"]:
                line["speakers"] = source["speakers"]
                changed += 1
        if changed:
            save_json_file(file_name, saved)
            updated += changed
    return updated
