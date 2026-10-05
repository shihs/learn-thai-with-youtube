# 抓取任務：抓字幕 → GPT 解析 → 合併存檔，以及任務進度的記錄
import threading

from .gpt_teacher import analyze_long_text, is_fatal_error
from .storage import (
    gpt_cache_file,
    is_subtitle_complete,
    load_gpt_cache,
    load_saved_transcript,
    save_json_file,
    subtitle_file,
    transcript_file,
)
from .youtube import fetch_yt_video_transcript

# 任務狀態只存在記憶體裡，後端重啟就會清空
# {video_id: {"status": "running" | "done" | "error", "stage", "done", "total", "message"}}
jobs = {}
jobs_lock = threading.Lock()


def start_job(video_id, refetch_transcript=False):
    """
    登記一個新任務。回傳 (狀態, 是否需要實際執行)；
    同一部影片已經在跑、或字幕已經完整時不需要執行。
    """
    with jobs_lock:
        # 同一部影片已經在跑就不要再開一個
        if jobs.get(video_id, {}).get("status") == "running":
            return jobs[video_id], False
        if not refetch_transcript and is_subtitle_complete(video_id):
            return {"status": "done", "message": "字幕已存在，不需要重新抓取"}, False
        jobs[video_id] = {"status": "running", "stage": "transcript", "done": 0, "total": 0, "message": "抓取字幕中"}
        return jobs[video_id], True


def run_job(video_id, refetch_transcript=False):
    try:
        long_analyze_and_save(video_id, refetch_transcript)
    except Exception as e:
        print(f"任務失敗：{e}")
        if is_fatal_error(e):
            message = "OpenAI 金鑰無效或額度不足。已分析的部分有保留，處理後再按一次「抓取字幕」會從中斷處繼續"
        else:
            message = f"{type(e).__name__}: {str(e).strip()[:300]}"
        jobs[video_id] = {**jobs[video_id], "status": "error", "message": message}


def long_analyze_and_save(video_id, refetch_transcript=False):
    # 之前抓過字幕就直接用，不用再連 YouTube / ElevenLabs，只重跑 GPT 分析；
    # refetch_transcript 時才重新取得（失敗的話舊檔案不會被動到）
    transcripts_with_time = None if refetch_transcript else load_saved_transcript(video_id)
    if transcripts_with_time is None:
        transcripts_with_time, whole_script = fetch_yt_video_transcript(video_id)
        save_json_file(transcript_file(video_id), transcripts_with_time)

    def on_progress(results, total):
        # 每完成一段就存檔，任務中斷後重跑不用重新付費
        save_json_file(gpt_cache_file(video_id), results)
        jobs[video_id] = {
            "status": "running",
            "stage": "analyzing",
            "done": len(results),
            "total": total,
            "message": "GPT 分析中",
        }

    response = analyze_long_text(transcripts_with_time, cached=load_gpt_cache(video_id), on_progress=on_progress)

    # 合併解釋：用 id 對齊，GPT 沒回傳的那幾行不影響其他行
    for line_id, explanation in response.items():
        transcripts_with_time[line_id]["explanation"] = explanation

    save_json_file(subtitle_file(video_id), transcripts_with_time)
    print("字幕完成！")

    total = jobs[video_id]["total"]
    missing = total - len(response)
    jobs[video_id] = {
        "status": "done",
        "stage": "done",
        "done": len(response),
        "total": total,
        "message": f"有 {missing} 句沒有解析，再按一次「抓取字幕」可以補上" if missing else "",
    }
