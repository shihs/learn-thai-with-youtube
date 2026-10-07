# 補上講者：用已存的 ElevenLabs 回應，把每句是誰講的補進之前存好的字幕檔。
# 不會呼叫 ElevenLabs 或 OpenAI；YouTube 手動字幕的影片沒有講者資訊，不會被動到。
#
#   python scripts/backfill_speakers.py    更新 data/transcripts/ 與 data/subtitles/
import glob
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

from backend import storage  # noqa: E402
from backend.elevenlabs_api import backfill_speakers  # noqa: E402


def main():
    for file_name in sorted(glob.glob(f"{storage.DATA_DIR}/elevenlabs/*.json")):
        video_id = os.path.splitext(os.path.basename(file_name))[0]
        print(f"{video_id}：補上 {backfill_speakers(video_id)} 句")


if __name__ == "__main__":
    main()
