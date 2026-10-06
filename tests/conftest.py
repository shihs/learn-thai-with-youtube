# 測試共用工具：把資料目錄指到暫存位置，以及假的 OpenAI client
import json
from types import SimpleNamespace

import pytest

from backend import storage


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """讓 storage 的所有檔案都寫到暫存目錄"""
    monkeypatch.setattr(storage, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(storage, "SUBTITLE_DIR", f"{tmp_path}/subtitles")
    return tmp_path


class FakeClient:
    """假的 OpenAI client：取出 prompt 最後的 JSON，交給 respond(payload) 產生回應"""

    def __init__(self, respond):
        self.respond = respond
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        content = kwargs["messages"][1]["content"]
        payload = json.loads(content.rsplit("：\n", 1)[1])
        self.calls.append(payload)
        body = json.dumps(self.respond(payload), ensure_ascii=False)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=body))])
