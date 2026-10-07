# 抓取任務：抓字幕 → GPT 逐句解析 → 查詞庫沒有的字 → 合併存檔，以及任務進度的記錄
import threading

from .dictionary import load_dictionary, merge_explanation, missing_words
from .gpt_teacher import analyze_long_text, is_fatal_error, lookup_missing_words
from .storage import (
    delete_subtitle_files,
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
# stage 是 analyzing 時 done / total 是句數，dictionary 時是字數
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


def delete_video(video_id):
    """
    把影片從字幕清單拿掉。回傳 "deleted"、"running"（任務進行中不能刪）或 "not_found"。
    ElevenLabs 的回應和 GPT 解析的快取會留著，之後再加回來不用重新付費。
    """
    with jobs_lock:
        if jobs.get(video_id, {}).get("status") == "running":
            return "running"
        jobs.pop(video_id, None)
        return "deleted" if delete_subtitle_files(video_id) else "not_found"


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
        transcripts_with_time, whole_script = fetch_yt_video_transcript(video_id, refetch=refetch_transcript)
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

    def on_dictionary_progress(done, total):
        jobs[video_id] = {
            "status": "running",
            "stage": "dictionary",
            "done": done,
            "total": total,
            "message": "建立詞庫中",
        }

    # 詞庫沒有的字集中查一次；查過的字之後每部影片都直接沿用
    missing = missing_words(response, load_dictionary())
    if missing:
        on_dictionary_progress(0, len(missing))
        lookup_missing_words(missing, on_progress=on_dictionary_progress)

    # 合併解釋：用 id 對齊，GPT 沒回傳的那幾行不影響其他行
    dictionary = load_dictionary()
    partial = 0
    for line_id, explanation in response.items():
        merged = merge_explanation(explanation, dictionary)
        partial += bool(merged.get("partial"))
        transcripts_with_time[line_id]["explanation"] = merged

    save_json_file(subtitle_file(video_id), transcripts_with_time)
    print("字幕完成！")

    total = sum(1 for snippet in transcripts_with_time.values() if snippet["text"].strip())
    notes = []
    if total > len(response):
        notes.append(f"有 {total - len(response)} 句沒有解析")
    if partial:
        notes.append(f"有 {partial} 句的單字還沒有詞庫資料")
    jobs[video_id] = {
        "status": "done",
        "stage": "done",
        "done": len(response),
        "total": total,
        "message": "、".join(notes) + "，再按一次「抓取字幕」可以補上" if notes else "",
    }
