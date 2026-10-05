# 檔案存取：所有資料檔的位置，以及讀寫它們的函式
import glob
import json
import os
import re

VIDEO_ID_PATTERN = r"^[A-Za-z0-9_-]{11}$"

# data/
#   subtitles/{id}.json      最終給前端用的字幕（含解析）
#   transcripts/{id}.json    抓回來的原始字幕（不含解析）
#   explanations/{id}.json   GPT 逐句解析的快取
#   elevenlabs/{id}.json     ElevenLabs 的原始轉錄回應
#   video_titles.json        影片標題的快取
DATA_DIR = "./data"
SUBTITLE_DIR = f"{DATA_DIR}/subtitles"
TITLE_CACHE_FILE = f"{DATA_DIR}/video_titles.json"


def subtitle_file(video_id):
    return f"{SUBTITLE_DIR}/{video_id}.json"


def transcript_file(video_id):
    """抓回來的原始字幕（不含解析）"""
    return f"{DATA_DIR}/transcripts/{video_id}.json"


def gpt_cache_file(video_id):
    """GPT 逐句解析的快取"""
    return f"{DATA_DIR}/explanations/{video_id}.json"


def load_json_file(file_name):
    try:
        with open(file_name, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_json_file(file_name, json_content):
    os.makedirs(os.path.dirname(file_name), exist_ok=True)
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(json_content, f, ensure_ascii=False, indent=4)


def is_subtitle_complete(video_id):
    """字幕檔存在，而且每一句有內容的字幕都有解析"""
    subtitles = load_json_file(subtitle_file(video_id))
    if not isinstance(subtitles, dict) or not subtitles:
        return False
    return all("explanation" in line for line in subtitles.values() if line.get("text", "").strip())


def load_saved_transcript(video_id):
    """之前抓過的字幕（不含解析）；沒有就回傳 None"""
    for file_name in (transcript_file(video_id), subtitle_file(video_id)):
        saved = load_json_file(file_name)
        if isinstance(saved, dict) and saved:
            print(f"使用已存在的字幕：{file_name}")
            return {
                int(line_id): {key: value for key, value in line.items() if key != "explanation"}
                for line_id, line in saved.items()
            }
    return None


def load_gpt_cache(video_id):
    cached = load_json_file(gpt_cache_file(video_id))
    # 舊版存的是陣列，沒有 id 無法沿用
    if not isinstance(cached, dict):
        return {}
    return {int(line_id): explanation for line_id, explanation in cached.items() if line_id.isdigit()}


def list_subtitle_videos():
    """目前有字幕的影片與解析進度，最近更新的排前面"""
    videos = []
    for file_name in glob.glob(f"{SUBTITLE_DIR}/*.json"):
        video_id = os.path.splitext(os.path.basename(file_name))[0]
        subtitles = load_json_file(file_name)
        if not re.match(VIDEO_ID_PATTERN, video_id) or not isinstance(subtitles, dict):
            continue
        lines = [line for line in subtitles.values() if line.get("text", "").strip()]
        videos.append(
            {
                "id": video_id,
                "lines": len(lines),
                "explained": sum(1 for line in lines if "explanation" in line),
                "updated": os.path.getmtime(file_name),
            }
        )
    videos.sort(key=lambda video: video["updated"], reverse=True)
    return videos


def elevenlabs_file(video_id):
    """ElevenLabs 的原始轉錄回應，避免同一部影片重複付費轉錄"""
    return f"{DATA_DIR}/elevenlabs/{video_id}.json"
