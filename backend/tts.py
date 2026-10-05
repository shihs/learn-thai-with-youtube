# 語音合成：用 ElevenLabs 把一句泰文唸出來
import hashlib
import os

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

from .storage import tts_file

load_dotenv()

# 唸字幕用的聲音，可在 .env 用 ELEVENLABS_VOICE_ID 換成別的
TTS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "XLXcyPK1jTjw1pYLLcM9")
TTS_MODEL_ID = "eleven_v3"
TTS_OUTPUT_FORMAT = "mp3_44100_128"


def synthesize(text):
    """
    把一句話轉成語音，回傳 mp3 檔的路徑。
    同樣的聲音、模型和文字只會向 ElevenLabs 付費一次，之後直接用存下來的檔案。
    """
    key = hashlib.sha1(f"{TTS_VOICE_ID}|{TTS_MODEL_ID}|{text}".encode("utf-8")).hexdigest()
    file_name = tts_file(key)
    if os.path.exists(file_name):
        return file_name

    elevenlabs = ElevenLabs(
        api_key=os.getenv("ELEVENLABS_API_KEY"),
    )
    audio = b"".join(
        elevenlabs.text_to_speech.convert(
            voice_id=TTS_VOICE_ID,
            text=text,
            model_id=TTS_MODEL_ID,
            language_code="th",
            output_format=TTS_OUTPUT_FORMAT,
        )
    )

    # 先寫到暫存檔再改名，避免產生到一半的檔案被當成快取
    os.makedirs(os.path.dirname(file_name), exist_ok=True)
    temp_file_name = file_name + ".part"
    with open(temp_file_name, "wb") as f:
        f.write(audio)
    os.replace(temp_file_name, file_name)
    return file_name
