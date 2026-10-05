from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
import json
import os
import re

from .storage import elevenlabs_file, load_json_file, save_json_file

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
        tag_audio_events=False, # Tag audio events like laughter, applause, etc.
        language_code="tha", # Language of the audio file. If set to None, the model will detect the language automatically.
        diarize=True, # Whether to annotate who is speaking,
        timestamps_granularity=None, # The granularity of the timestamps in the transcription.
        additional_formats= [{"format": "srt", "include_timestamps": True}]
    )


    # transcription.json() 回傳的是字串，先轉回 dict 再存，檔案才不會被編碼兩次
    thai_script = json.loads(transcription.json())

    save_json_file(elevenlabs_file(video_id), thai_script)

    return thai_script


def load_or_request_transcription(video_id):
    thai_script = load_json_file(elevenlabs_file(video_id))
    if thai_script is not None:
        print(f"使用已存在的 ElevenLabs 轉錄結果：{elevenlabs_file(video_id)}")
        return thai_script

    print(f"呼叫 ElevenLabs API 轉錄 {video_id}......")
    return request_ele_api(video_id)


# 零長度字幕找不到下一句可合併時，最多顯示這麼久（秒）
MAX_ZERO_LENGTH_DURATION = 2.0


def merge_zero_length_segments(segments):
    """
    兩人同時講話時，ElevenLabs 會把插話壓成起訖時間相同的字幕，前端永遠顯示不到。
    這類字幕和下一句同時開始，所以併進下一句（以換行分隔）；
    若下一句較晚開始，則獨立成一句並延長到下一句開始為止。
    """
    merged = []
    pending = []

    def flush(until=None):
        duration = MAX_ZERO_LENGTH_DURATION
        if until is not None:
            duration = min(duration, round(until - pending[0]["start"], 3))
        merged.append({**pending[0], "text": "\n".join(s["text"] for s in pending), "duration": duration})
        pending.clear()

    for seg in segments:
        if pending and seg["start"] != pending[0]["start"]:
            flush(until=seg["start"])

        if seg["duration"] <= 0:
            pending.append(seg)
            continue

        if pending:
            seg = {**seg, "text": "\n".join([s["text"] for s in pending] + [seg["text"]])}
            pending.clear()
        merged.append(seg)

    if pending:
        flush()

    return merged


def generate_transcript_json(video_id):

    thai_script = load_or_request_transcription(video_id)

    content = thai_script["additional_formats"][0]["content"]

    # 每個 SRT 區塊：序號 / 時間軸 / 一到多行文字，區塊之間以空行分隔
    segments = []
    for block in re.split(r"\n\s*\n", content.strip()):
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        timing = next((n for n, line in enumerate(lines) if "-->" in line), None)
        if timing is None:
            continue

        start_time, end_time = [t.strip() for t in lines[timing].split("-->")]
        text = THAI_SPACING.sub("", " ".join(lines[timing + 1 :]))
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
    transcript_with_time = dict(enumerate(merge_zero_length_segments(segments)))

    whole_script = ""
    for snippet in transcript_with_time.values():
        whole_script += snippet["text"] + "\n"

    return transcript_with_time, whole_script
