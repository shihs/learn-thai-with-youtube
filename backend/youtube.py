# YouTube 相關：抓字幕、查影片標題
# https://github.com/jdepoix/youtube-transcript-api
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import quote
from urllib.request import urlopen

from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled, YouTubeTranscriptApi

from .elevenlabs_api import generate_transcript_json
from .storage import TITLE_CACHE_FILE, load_json_file, save_json_file


def seconds_to_time(seconds):
    return str(timedelta(seconds=seconds))


def fetch_yt_video_transcript(video_id, transcript_lang="th", refetch=False):
    ytt_api = YouTubeTranscriptApi()

    # 手動上傳字幕
    try:
        transcript = ytt_api.list(video_id).find_manually_created_transcript([transcript_lang])

    # # YT 自動產生字幕
    # elif transcript_list._generated_transcripts.get(transcript_lang):
    #     transcript = transcript_list.find_generated_transcript([transcript_lang])

    # EleventLabs API：影片完全沒有字幕（TranscriptsDisabled）或沒有手動泰文字幕（NoTranscriptFound）
    except (TranscriptsDisabled, NoTranscriptFound):
        print(f"No manually created '{transcript_lang}' transcript is found, use ElevenLabs.")
        transcript_with_time, whole_script = generate_transcript_json(video_id, refetch=refetch)

        return transcript_with_time, whole_script


    fetched_transcript = transcript.fetch()
    transcript_with_time = {}
    whole_script = ""
    for i, snippet in enumerate(fetched_transcript):

        transcript_with_time[i] = {
            "text": snippet.text,
            "start": snippet.start,
            "duration": snippet.duration,
            "start_time": seconds_to_time(snippet.start),
        }

        whole_script += snippet.text + "\n"

    return transcript_with_time, whole_script


def fetch_video_title(video_id):
    """用 YouTube oEmbed 查影片標題（不需要金鑰）；查不到回傳 None"""
    url = "https://www.youtube.com/oembed?format=json&url=" + quote(f"https://www.youtube.com/watch?v={video_id}")
    try:
        with urlopen(url, timeout=5) as response:
            return json.load(response).get("title")
    except Exception as e:
        print(f"查不到 {video_id} 的標題：{e}")
        return None


def get_video_titles(video_ids):
    """回傳 {video_id: 標題}。標題查過一次就存起來，之後不用再連 YouTube"""
    titles = load_json_file(TITLE_CACHE_FILE) or {}
    missing = [video_id for video_id in video_ids if video_id not in titles]
    if missing:
        with ThreadPoolExecutor(max_workers=8) as executor:
            for video_id, title in zip(missing, executor.map(fetch_video_title, missing)):
                if title:
                    titles[video_id] = title
        save_json_file(TITLE_CACHE_FILE, titles)
    return titles
