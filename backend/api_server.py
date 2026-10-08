# FastAPI 進入點：只放路由，實際的工作在 jobs / storage / youtube / gpt_teacher / elevenlabs_api
# 從專案根目錄啟動：uvicorn backend.api_server:app --reload

import os
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .jobs import delete_video, jobs, run_job, start_job
from .storage import VIDEO_ID_PATTERN, list_subtitle_videos, load_json_file, subtitle_file
from .tts import synthesize
from .youtube import get_video_titles

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 或只填你的前端網址，例如 ["http://localhost:5173"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


VideoId = Annotated[str, Path(pattern=VIDEO_ID_PATTERN)]


class VideoRequest(BaseModel):
    video_id: str = Field(pattern=VIDEO_ID_PATTERN)
    # True：不用本機存過的字幕，重新向 YouTube / ElevenLabs 取得
    refetch_transcript: bool = False


@app.post("/analyze")
def analyze_video(req: VideoRequest, background_tasks: BackgroundTasks):
    status, should_run = start_job(req.video_id, req.refetch_transcript)
    if should_run:
        print(f"開始抓取 YouTube v{req.video_id} 字幕......")
        background_tasks.add_task(run_job, req.video_id, req.refetch_transcript)
    return status


@app.get("/status/{video_id}")
def get_status(video_id: VideoId):
    if video_id in jobs:
        return jobs[video_id]
    if os.path.exists(subtitle_file(video_id)):
        return {"status": "done", "message": ""}
    return {"status": "not_found", "message": "沒有這部影片的任務"}


@app.get("/videos")
def list_videos():
    """列出目前有字幕的影片，最近更新的排前面"""
    videos = list_subtitle_videos()
    titles = get_video_titles([video["id"] for video in videos])
    for video in videos:
        video["title"] = titles.get(video["id"])
    return videos


@app.delete("/videos/{video_id}")
def remove_video(video_id: VideoId):
    """把影片從清單拿掉（轉錄與解析的快取會留著）"""
    result = delete_video(video_id)
    if result == "running":
        raise HTTPException(status_code=409, detail="這部影片還在抓取或解析中，等它跑完再刪除")
    if result == "not_found":
        raise HTTPException(status_code=404, detail="Subtitles not found")
    return {"status": "deleted"}


@app.get("/subtitles/{video_id}")
def get_subtitles(video_id: VideoId):
    subtitles = load_json_file(subtitle_file(video_id))
    if subtitles is None:
        raise HTTPException(status_code=404, detail="Subtitles not found")
    return subtitles


@app.get("/tts/{video_id}/{line_id}")
def speak_line(video_id: VideoId, line_id: Annotated[str, Path(pattern=r"^\d+$")]):
    """把某部影片的某一句字幕唸出來（mp3）。只接受已存在的字幕，不能唸任意文字"""
    subtitles = load_json_file(subtitle_file(video_id)) or {}
    line = subtitles.get(line_id)
    text = " ".join(line["text"].split()) if line else ""
    if not text:
        raise HTTPException(status_code=404, detail="Subtitle line not found")
    try:
        return FileResponse(synthesize(text), media_type="audio/mpeg")
    except Exception as e:
        print(f"語音產生失敗：{e}")
        if "missing_permissions" in str(e):
            detail = "ElevenLabs 金鑰沒有 Text to Speech 權限，請到 ElevenLabs 後台的 API Keys 頁面為這把金鑰開啟"
        else:
            detail = f"{type(e).__name__}: {str(e).strip()[:300]}"
        raise HTTPException(status_code=502, detail=detail)
