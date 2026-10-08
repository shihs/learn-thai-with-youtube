from youtube_transcript_api import TranscriptsDisabled

from backend import youtube

VIDEO_ID = "aaaaaaaaaaa"


class NoCaptions:
    def list(self, video_id):
        raise TranscriptsDisabled(video_id)


def test_video_without_thai_captions_passes_refetch_on_to_elevenlabs(monkeypatch):
    calls = []

    def generate(video_id, refetch=False):
        calls.append((video_id, refetch))
        return {}, ""

    monkeypatch.setattr(youtube, "YouTubeTranscriptApi", NoCaptions)
    monkeypatch.setattr(youtube, "generate_transcript_json", generate)

    youtube.fetch_yt_video_transcript(VIDEO_ID)
    youtube.fetch_yt_video_transcript(VIDEO_ID, refetch=True)

    assert calls == [(VIDEO_ID, False), (VIDEO_ID, True)]
