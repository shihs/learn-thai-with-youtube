# 單字拆解改進、詞庫與 Forvo 連結 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 單字解析改成以字典詞條為單位並涵蓋整句，重複的字改由本機詞庫提供拼音與說明，每張單字卡可以連到 Forvo 聽真人發音。

**Architecture:** 解析分兩步。第一步逐句送 GPT，只取整句拼音、翻譯，以及每個字「在這句的意思」；結果用 pythainlp 檢查，沒通過的句子重送一次。第二步把詞庫沒有的字集中查一次，寫進 `data/dictionary.json`。存字幕檔時把兩邊合併，前端讀到的仍是自帶完整資料的字幕檔。

**Tech Stack:** Python 3.10（本機 3.9 也可執行）、FastAPI、OpenAI `gpt-4.1-mini`（structured outputs）、pythainlp 5.3.8、pytest 8.3.5、React 19 + Vite + Tailwind、lucide-react。

**Spec:** `docs/superpowers/specs/2026-10-06-word-segmentation-forvo-design.md`

## Global Constraints

- `ANALYSIS_VERSION = 2`，定義在 `backend/storage.py`。
- `type` 只能是 `word`、`particle`、`classifier`、`name`、`expression`。
- 詞庫檔是 `data/dictionary.json`，格式 `{泰文單字: {"rtgs", "parts", "senses", "usage"}}`；已經存在的字不覆蓋。
- 粒度檢查的門檻：`type` 不是 `name` 的單字，pythainlp 斷詞後超過 4 個 token 就算沒拆好。
- 每句最多重送一次；查詞每 40 個字一批、失敗的批次重試一次；同時最多 5 個請求。
- 環境變數 `SEGMENT_HINT`（`on` / `off`）只控制要不要把 pythainlp 的切法附給 GPT；檢查永遠用 pythainlp。
- Forvo 連結用 `<a target="_blank" rel="noopener noreferrer">`、圖示 `Headphones`、`title` 與 `aria-label` 是「在 Forvo 聽真人發音（另開分頁）」；`type` 是 `name` 的不顯示。
- 測試不可以呼叫 OpenAI。會花 OpenAI 費用的兩個步驟（Task 9 的對照實驗、Task 10 的重跑範例）執行前一定要先問使用者。
- 程式碼註解用繁體中文，風格跟現有檔案一致；不使用 Python 3.10 才有的語法（`X | Y` 型別、`match`）。
- Commit 訊息用英文、動詞開頭（例如 `Add …`），結尾加上 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。

## Review Focus

1. **只有符號、音符或空白以外沒有文字的字幕**（例如 `♪♪`）：GPT 回空的單字清單時應該算通過，不該每次都重送。→ Task 2 的測試。
2. **舊格式的字幕檔**（沒有 `v`、`type`、`parts`）：清單上要顯示為未完成，但畫面要照常顯示舊解析，不能壞掉。→ Task 3 的測試、Task 8 的畫面檢查。
3. **兩支影片同時寫詞庫**：兩邊新增的字都要留下來，不能互相蓋掉。→ Task 4 的測試。
4. **詞庫檔不存在或內容壞掉**：當成空詞庫，不能讓任務失敗。→ Task 4 的測試。
5. **查詞中途失敗**：已經解析的句子不能重新付費；再按一次「抓取字幕」只補查詞。→ Task 7 的測試。

---

## File Structure

| 檔案 | 責任 |
|---|---|
| `backend/segmenter.py`（新） | `tokenize(text)`：pythainlp 斷詞 |
| `backend/analysis_check.py`（新） | `check_analysis(thai, analysis)`：涵蓋與粒度檢查 |
| `backend/dictionary.py`（新） | 詞庫的讀取、加鎖寫入、找缺的字、合併 |
| `backend/gpt_teacher.py` | 兩種 GPT 請求（逐句解析、查詞）、`SEGMENT_HINT`、兩輪重送 |
| `backend/jobs.py` | 串起解析、查詞、合併存檔與任務進度 |
| `backend/storage.py` | `ANALYSIS_VERSION`、詞庫檔路徑、完成度判斷 |
| `frontend/src/VideoSubtitleApp.jsx` | `WordCard` 元件、Forvo 連結、進度單位 |
| `scripts/compare_segmentation.py`（新） | 對照實驗 |
| `tests/`（新） | pytest |

---

### Task 1: 環境與斷詞模組

**Files:**
- Create: `backend/segmenter.py`, `requirements-dev.txt`, `tests/__init__.py`, `tests/conftest.py`, `tests/test_segmenter.py`
- Modify: `requirements.txt`, `.gitignore`, `.dockerignore`

**Interfaces:**
- Produces: `backend.segmenter.tokenize(text: str) -> list[str]`；pytest fixture `data_dir`（把 `storage.DATA_DIR` 指到暫存目錄，回傳該 `Path`）；`tests.conftest.FakeClient(respond)`。

- [ ] **Step 1: 開分支並提交 spec 與計畫**

```bash
git checkout -b word-segmentation-forvo
git add docs/superpowers
git commit -m "Add design and plan for word segmentation, dictionary and Forvo links

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 2: 加入套件並建立虛擬環境**

在 `requirements.txt` 最後加一行：

```
pythainlp==5.3.8
```

建立 `requirements-dev.txt`：

```
-r requirements.txt
pytest==8.3.5
```

在 `.gitignore` 的 `# Python` 區塊加上 `.venv/` 和 `.pytest_cache/`。執行 `grep -n "venv" .dockerignore`，沒有結果的話在 `.dockerignore` 加一行 `.venv`。

```bash
python3.10 -m venv .venv || python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

Expected: 安裝成功，最後沒有 `ERROR`。

- [ ] **Step 3: 寫測試共用工具**

建立空的 `tests/__init__.py`，以及 `tests/conftest.py`：

```python
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
```

- [ ] **Step 4: 寫會失敗的測試**

`tests/test_segmenter.py`：

```python
from backend.segmenter import tokenize


def test_tokenize_splits_thai_into_words():
    assert tokenize("ไม่เป็นไรค่ะ") == ["ไม่เป็นไร", "ค่ะ"]


def test_tokenize_drops_whitespace_tokens():
    tokens = tokenize("ตู้เย็น อยู่ไหน\nน้ำแข็ง")
    assert tokens == ["ตู้เย็น", "อยู่", "ไหน", "น้ำแข็ง"]
    assert all(token.strip() for token in tokens)


def test_tokenize_empty_text():
    assert tokenize("") == []
```

- [ ] **Step 5: 執行測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_segmenter.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'backend.segmenter'`

- [ ] **Step 6: 實作**

`backend/segmenter.py`：

```python
# 斷詞：用 pythainlp 把泰文切成詞。切法給 GPT 當提示，也用來檢查 GPT 拆得夠不夠細
from pythainlp.tokenize import word_tokenize


def tokenize(text):
    """泰文斷詞（查字典做最長匹配），去掉純空白的 token"""
    return [token for token in word_tokenize(text, engine="newmm") if token.strip()]
```

- [ ] **Step 7: 執行測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_segmenter.py -v`
Expected: 3 passed

- [ ] **Step 8: Commit**

```bash
git add requirements.txt requirements-dev.txt .gitignore .dockerignore backend/segmenter.py tests
git commit -m "Add pythainlp tokenizer and pytest setup

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 解析檢查

**Files:**
- Create: `backend/analysis_check.py`, `tests/test_analysis_check.py`

**Interfaces:**
- Consumes: `backend.segmenter.tokenize(text) -> list[str]`
- Produces: `backend.analysis_check.check_analysis(thai: str, analysis: list[dict]) -> list[str]`。`analysis` 的每筆至少有 `word`，`type` 可以沒有。回傳沒通過的原因；空清單代表通過。

- [ ] **Step 1: 寫會失敗的測試**

`tests/test_analysis_check.py`：

```python
from backend.analysis_check import check_analysis


def words(*items):
    """("字", "type") → analysis 清單；只給字串時 type 是 word"""
    return [
        {"word": item, "type": "word"} if isinstance(item, str) else {"word": item[0], "type": item[1]}
        for item in items
    ]


# 涵蓋


def test_full_coverage_passes():
    assert check_analysis("ไม่เป็นไรค่ะ", words(("ไม่เป็นไร", "expression"), ("ค่ะ", "particle"))) == []


def test_missing_word_fails():
    assert check_analysis("ไม่เป็นไรค่ะ", words(("ไม่เป็นไร", "expression"))) != []


def test_changed_spelling_fails():
    assert check_analysis("มาแล้ว", words("มา", "เเล้ว")) != []


def test_wrong_order_fails():
    assert check_analysis("มาแล้ว", words("แล้ว", "มา")) != []


def test_whitespace_and_punctuation_are_ignored():
    assert check_analysis("มา แล้ว!\nค่ะ", words("มา", "แล้ว", ("ค่ะ", "particle"))) == []


def test_symbol_only_line_passes_with_empty_analysis():
    assert check_analysis("♪♪ ~", []) == []


def test_text_line_with_empty_analysis_fails():
    assert check_analysis("มาแล้ว", []) != []


# 粒度


def test_whole_clause_as_one_word_fails():
    clause = "พร้อมที่จะส่งเราให้ไปแบบใช่กันไปเรื่อยๆ"
    problems = check_analysis(clause, words(clause))
    assert len(problems) == 1
    assert clause in problems[0]


def test_compound_word_passes():
    assert check_analysis("เครื่องเขียน", words("เครื่องเขียน")) == []


def test_four_token_idiom_passes():
    assert check_analysis("ชี้เป็นชี้ตาย", words(("ชี้เป็นชี้ตาย", "expression"))) == []


def test_long_name_passes_only_as_name():
    name = "ภัทราภัทรโบว์รัชตะสุวรรณ"
    assert check_analysis(name, words((name, "name"))) == []
    assert check_analysis(name, words(name)) != []


def test_items_without_type_are_treated_as_words():
    clause = "พร้อมที่จะส่งเราให้ไปแบบใช่กันไปเรื่อยๆ"
    assert check_analysis(clause, [{"word": clause}]) != []
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_analysis_check.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'backend.analysis_check'`

- [ ] **Step 3: 實作**

`backend/analysis_check.py`：

```python
# 解析檢查：確認 GPT 拆出來的單字涵蓋整句，而且沒有把片語當成一個字
import unicodedata

from .segmenter import tokenize

# 一個字被機器斷詞切成超過這麼多段，就當成沒拆開（人名除外）
MAX_TOKENS_PER_WORD = 4


def _letters(text):
    """只留下文字、聲調符號和數字；空白、標點、音符這類符號不比對"""
    return "".join(ch for ch in unicodedata.normalize("NFC", text) if unicodedata.category(ch)[0] in "LMN")


def check_analysis(thai, analysis):
    """回傳沒通過的原因清單，空清單代表通過"""
    problems = []
    if _letters("".join(item["word"] for item in analysis)) != _letters(thai):
        problems.append("單字接起來和原句不一樣")
    for item in analysis:
        if item.get("type") != "name" and len(tokenize(item["word"])) > MAX_TOKENS_PER_WORD:
            problems.append(f"「{item['word']}」沒有拆開")
    return problems
```

- [ ] **Step 4: 執行測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_analysis_check.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add backend/analysis_check.py tests/test_analysis_check.py
git commit -m "Add coverage and granularity check for word analysis

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 版本號與完成度判斷

**Files:**
- Modify: `backend/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: fixture `data_dir`
- Produces:
  - `backend.storage.ANALYSIS_VERSION: int`（值是 `2`）
  - `backend.storage.dictionary_file() -> str`
  - `backend.storage.is_current_explanation(explanation) -> bool`
  - `is_subtitle_complete(video_id)` 與 `list_subtitle_videos()` 的 `explained` 改用 `is_current_explanation`

- [ ] **Step 1: 寫會失敗的測試**

`tests/test_storage.py`：

```python
from backend import storage

VIDEO_ID = "aaaaaaaaaaa"
CURRENT = {"thai": "มา", "v": storage.ANALYSIS_VERSION, "analysis": []}
OLD = {"thai": "มา", "analysis": []}
PARTIAL = {**CURRENT, "partial": True}


def save_subtitles(*explanations):
    lines = {str(index): {"text": "มา", "explanation": e} for index, e in enumerate(explanations)}
    lines[str(len(lines))] = {"text": "   "}  # 沒有內容的字幕不需要解析
    storage.save_json_file(storage.subtitle_file(VIDEO_ID), lines)


def test_is_current_explanation():
    assert storage.is_current_explanation(CURRENT)
    assert not storage.is_current_explanation(OLD)
    assert not storage.is_current_explanation(PARTIAL)
    assert not storage.is_current_explanation(None)


def test_complete_when_every_line_is_current(data_dir):
    save_subtitles(CURRENT, CURRENT)
    assert storage.is_subtitle_complete(VIDEO_ID)


def test_incomplete_with_old_version(data_dir):
    save_subtitles(CURRENT, OLD)
    assert not storage.is_subtitle_complete(VIDEO_ID)


def test_incomplete_with_partial_line(data_dir):
    save_subtitles(CURRENT, PARTIAL)
    assert not storage.is_subtitle_complete(VIDEO_ID)


def test_incomplete_when_a_line_has_no_explanation(data_dir):
    storage.save_json_file(storage.subtitle_file(VIDEO_ID), {"0": {"text": "มา"}})
    assert not storage.is_subtitle_complete(VIDEO_ID)


def test_list_counts_only_current_explanations(data_dir):
    save_subtitles(CURRENT, OLD, PARTIAL)
    (video,) = storage.list_subtitle_videos()
    assert video["lines"] == 3
    assert video["explained"] == 1


def test_dictionary_file_is_inside_data_dir(data_dir):
    assert storage.dictionary_file() == f"{data_dir}/dictionary.json"
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_storage.py -v`
Expected: FAIL，`AttributeError: module 'backend.storage' has no attribute 'ANALYSIS_VERSION'`

- [ ] **Step 3: 實作**

在 `backend/storage.py`：

把檔案開頭的資料目錄註解加上詞庫那一行，並在 `TITLE_CACHE_FILE` 後面加上版本號：

```python
# data/
#   subtitles/{id}.json      最終給前端用的字幕（含解析）
#   transcripts/{id}.json    抓回來的原始字幕（不含解析）
#   explanations/{id}.json   GPT 逐句解析的快取
#   dictionary.json          詞庫：每個單字的拼音、組成、常見意思與用法
#   elevenlabs/{id}.json     ElevenLabs 的原始轉錄回應
#   tts/{hash}.mp3           唸字幕的語音快取
#   video_titles.json        影片標題的快取
DATA_DIR = "./data"
SUBTITLE_DIR = f"{DATA_DIR}/subtitles"
TITLE_CACHE_FILE = f"{DATA_DIR}/video_titles.json"

# 解析格式的版本。改了 prompt 規則或欄位就加一，舊版的解析會被當成過期，重跑時重新產生
ANALYSIS_VERSION = 2
```

在 `gpt_cache_file` 後面加上：

```python
def dictionary_file():
    """詞庫：所有影片共用"""
    return f"{DATA_DIR}/dictionary.json"


def is_current_explanation(explanation):
    """目前版本、而且每個單字都查得到詞庫的解析"""
    return (
        isinstance(explanation, dict)
        and explanation.get("v") == ANALYSIS_VERSION
        and not explanation.get("partial")
    )
```

把 `is_subtitle_complete` 改成：

```python
def is_subtitle_complete(video_id):
    """字幕檔存在，而且每一句有內容的字幕都有目前版本的完整解析"""
    subtitles = load_json_file(subtitle_file(video_id))
    if not isinstance(subtitles, dict) or not subtitles:
        return False
    return all(
        is_current_explanation(line.get("explanation")) for line in subtitles.values() if line.get("text", "").strip()
    )
```

在 `list_subtitle_videos` 裡，把

```python
                "explained": sum(1 for line in lines if "explanation" in line),
```

改成

```python
                "explained": sum(1 for line in lines if is_current_explanation(line.get("explanation"))),
```

- [ ] **Step 4: 執行測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_storage.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add backend/storage.py tests/test_storage.py
git commit -m "Version explanations so outdated ones count as incomplete

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 詞庫模組

**Files:**
- Create: `backend/dictionary.py`, `tests/test_dictionary.py`

**Interfaces:**
- Consumes: `storage.dictionary_file()`, `storage.load_json_file(path)`, `storage.save_json_file(path, content)`, fixture `data_dir`
- Produces:
  - `load_dictionary() -> dict`：`{字: {"rtgs": str, "parts": list, "senses": str, "usage": str}}`
  - `add_entries(entries: dict) -> dict`：寫入新字（已存在的不覆蓋），回傳寫入後的整個詞庫
  - `missing_words(explanations: dict, dictionary: dict) -> dict`：`{字: 第一次出現的那一句}`
  - `merge_explanation(explanation: dict, dictionary: dict) -> dict`

- [ ] **Step 1: 寫會失敗的測試**

`tests/test_dictionary.py`：

```python
import threading

from backend import storage
from backend.dictionary import add_entries, load_dictionary, merge_explanation, missing_words


def entry(rtgs):
    return {"rtgs": rtgs, "parts": [], "senses": "意思", "usage": "用法"}


def explanation(thai, *word_list):
    return {
        "thai": thai,
        "v": storage.ANALYSIS_VERSION,
        "rtgs": "",
        "translation": "",
        "analysis": [{"word": word, "type": "word", "meaning": "本句意思", "more": ""} for word in word_list],
    }


# 讀寫


def test_missing_file_is_an_empty_dictionary(data_dir):
    assert load_dictionary() == {}


def test_corrupt_file_is_an_empty_dictionary(data_dir):
    (data_dir / "dictionary.json").write_text("{ not json", encoding="utf-8")
    assert load_dictionary() == {}


def test_non_object_file_is_an_empty_dictionary(data_dir):
    (data_dir / "dictionary.json").write_text("[1, 2]", encoding="utf-8")
    assert load_dictionary() == {}


def test_add_entries_persists(data_dir):
    returned = add_entries({"มา": entry("ma")})
    assert returned == {"มา": entry("ma")}
    assert load_dictionary() == {"มา": entry("ma")}


def test_add_entries_does_not_overwrite_existing_words(data_dir):
    add_entries({"มา": entry("ma")})
    add_entries({"มา": entry("WRONG"), "แล้ว": entry("laeo")})
    assert load_dictionary() == {"มา": entry("ma"), "แล้ว": entry("laeo")}


def test_concurrent_writers_keep_every_word(data_dir):
    def write(prefix):
        for index in range(25):
            add_entries({f"{prefix}{index}": entry("x")})

    threads = [threading.Thread(target=write, args=(prefix,)) for prefix in ("ก", "ข", "ค", "ง")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(load_dictionary()) == 100


# 找缺的字


def test_missing_words_dedupes_and_keeps_first_sentence():
    explanations = {
        2: explanation("แล้วมา", "แล้ว", "มา"),
        1: explanation("มาแล้ว", "มา", "แล้ว", "มา"),
    }
    assert missing_words(explanations, {}) == {"มา": "มาแล้ว", "แล้ว": "มาแล้ว"}


def test_missing_words_skips_known_words():
    explanations = {1: explanation("มาแล้ว", "มา", "แล้ว")}
    assert missing_words(explanations, {"มา": entry("ma")}) == {"แล้ว": "มาแล้ว"}


def test_missing_words_with_nothing_missing():
    explanations = {1: explanation("มา", "มา")}
    assert missing_words(explanations, {"มา": entry("ma")}) == {}


# 合併


def test_merge_adds_dictionary_fields_and_keeps_sentence_fields():
    merged = merge_explanation(explanation("มา", "มา"), {"มา": entry("ma")})
    assert merged["analysis"] == [
        {
            "word": "มา",
            "type": "word",
            "meaning": "本句意思",
            "more": "",
            "rtgs": "ma",
            "parts": [],
            "senses": "意思",
            "usage": "用法",
        }
    ]
    assert merged["thai"] == "มา"
    assert merged["v"] == storage.ANALYSIS_VERSION
    assert "partial" not in merged


def test_merge_marks_partial_when_a_word_is_unknown():
    merged = merge_explanation(explanation("มาแล้ว", "มา", "แล้ว"), {"มา": entry("ma")})
    assert merged["partial"] is True
    assert merged["analysis"][0]["rtgs"] == "ma"
    assert merged["analysis"][1] == {
        "word": "แล้ว",
        "type": "word",
        "meaning": "本句意思",
        "more": "",
        "rtgs": "",
        "parts": [],
        "senses": "",
        "usage": "",
    }


def test_merge_does_not_modify_its_input():
    original = explanation("มา", "มา")
    merge_explanation(original, {"มา": entry("ma")})
    assert "rtgs" not in original["analysis"][0]
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_dictionary.py -v`
Expected: FAIL，`ModuleNotFoundError: No module named 'backend.dictionary'`

- [ ] **Step 3: 實作**

`backend/dictionary.py`：

```python
# 詞庫：每個單字不隨句子改變的資料（拼音、組成、常見意思、用法），所有影片共用。
# 一個字只問 GPT 一次，之後每部影片都直接沿用。
import threading

from .storage import dictionary_file, load_json_file, save_json_file

# 詞庫裡找不到的字，合併時先填這些空值
EMPTY_ENTRY = {"rtgs": "", "parts": [], "senses": "", "usage": ""}

# 兩部影片可能同時在跑，讀寫詞庫檔都要排隊
_lock = threading.RLock()


def load_dictionary():
    """{泰文單字: {"rtgs", "parts", "senses", "usage"}}；檔案不存在或壞掉時是空的"""
    with _lock:
        saved = load_json_file(dictionary_file())
    return saved if isinstance(saved, dict) else {}


def add_entries(entries):
    """把新查到的字寫進詞庫，已經有的字不覆蓋。回傳寫入後的整個詞庫"""
    with _lock:
        dictionary = load_dictionary()
        for word, entry in entries.items():
            dictionary.setdefault(word, entry)
        save_json_file(dictionary_file(), dictionary)
        return dictionary


def missing_words(explanations, dictionary):
    """解析裡出現、但詞庫沒有的字：{字: 第一次出現的那一句}"""
    missing = {}
    for line_id in sorted(explanations):
        explanation = explanations[line_id]
        for item in explanation.get("analysis", []):
            word = item["word"]
            if word not in dictionary and word not in missing:
                missing[word] = explanation["thai"]
    return missing


def merge_explanation(explanation, dictionary):
    """把一句的解析和詞庫合併成前端要的格式；有字查不到詞庫時標成 partial"""
    analysis = []
    partial = False
    for item in explanation.get("analysis", []):
        entry = dictionary.get(item["word"])
        if entry is None:
            partial = True
            entry = EMPTY_ENTRY
        analysis.append({**item, **{field: entry[field] for field in EMPTY_ENTRY}})
    merged = {**explanation, "analysis": analysis}
    if partial:
        merged["partial"] = True
    return merged
```

- [ ] **Step 4: 執行測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_dictionary.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add backend/dictionary.py tests/test_dictionary.py
git commit -m "Add shared word dictionary with locked writes and merging

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 逐句解析（新 prompt、提示開關、檢查後重送）

**Files:**
- Modify: `backend/gpt_teacher.py`（整個檔案換成下面的內容）
- Test: `tests/test_gpt_sentences.py`

**Interfaces:**
- Consumes: `check_analysis(thai, analysis) -> list[str]`, `tokenize(text) -> list[str]`, `storage.ANALYSIS_VERSION`, `tests.conftest.FakeClient`
- Produces:
  - `segment_hint_enabled() -> bool`
  - `build_payload(items: list[dict], hint: bool) -> dict`：`items` 是 `[{"id", "thai"}]`，回傳 `{"item_1": {"thai": …, "tokens": […]}}`，`hint` 是 `False` 時沒有 `tokens`
  - `build_prompt(payload: dict, hint: bool) -> str`：最後兩行是 `這是要分析的泰文：` 和 payload 的 JSON
  - `analyze_long_text(transcript_with_time, max_lines=10, cached=None, on_progress=None, stats=None) -> dict`：回傳 `{id: {"thai", "v", "rtgs", "translation", "analysis": [{"word", "type", "meaning", "more"}]}}`；重送後仍沒通過檢查的句子多一個 `"resent": True`。`stats` 給一個 dict 時會填入 `first_failed` 與 `still_failed`。
  - `is_fatal_error(e)`、`split_transcript(...)`、`MAX_WORKERS` 維持不變

- [ ] **Step 1: 寫會失敗的測試**

`tests/test_gpt_sentences.py`：

```python
import pytest

from backend import gpt_teacher, storage
from tests.conftest import FakeClient

# 每一句正確的拆法
GOOD = {
    "ไม่เป็นไรค่ะ": [("ไม่เป็นไร", "expression"), ("ค่ะ", "particle")],
    "มาแล้ว": [("มา", "word"), ("แล้ว", "word")],
}
# 漏掉後半句的拆法，過不了涵蓋檢查
BAD = {
    "ไม่เป็นไรค่ะ": [("ไม่เป็นไร", "expression")],
    "มาแล้ว": [("มา", "word")],
}


def result(pairs):
    return {
        "rtgs": "rtgs",
        "translation": "翻譯",
        "analysis": [{"word": word, "type": kind, "meaning": "意思", "more": ""} for word, kind in pairs],
    }


def respond_with(table):
    return lambda payload: {key: result(table[item["thai"]]) for key, item in payload.items()}


def transcript(*texts):
    return {index: {"text": text} for index, text in enumerate(texts)}


@pytest.fixture
def use_client(monkeypatch):
    def install(respond):
        client = FakeClient(respond)
        monkeypatch.setattr(gpt_teacher, "OpenAI", lambda **kwargs: client)
        return client

    return install


@pytest.fixture
def no_client(monkeypatch):
    def fail(**kwargs):
        raise AssertionError("不應該呼叫 OpenAI")

    monkeypatch.setattr(gpt_teacher, "OpenAI", fail)


# 提示開關


def test_hint_defaults_to_on(monkeypatch):
    monkeypatch.delenv("SEGMENT_HINT", raising=False)
    assert gpt_teacher.segment_hint_enabled() is (gpt_teacher.SEGMENT_HINT_DEFAULT == "on")


def test_hint_follows_environment(monkeypatch):
    monkeypatch.setenv("SEGMENT_HINT", "off")
    assert gpt_teacher.segment_hint_enabled() is False
    monkeypatch.setenv("SEGMENT_HINT", "ON")
    assert gpt_teacher.segment_hint_enabled() is True


def test_payload_with_hint_includes_tokens():
    payload = gpt_teacher.build_payload([{"id": 7, "thai": "ไม่เป็นไรค่ะ"}], hint=True)
    assert payload == {"item_1": {"thai": "ไม่เป็นไรค่ะ", "tokens": ["ไม่เป็นไร", "ค่ะ"]}}


def test_payload_and_prompt_without_hint_never_mention_tokens():
    payload = gpt_teacher.build_payload([{"id": 7, "thai": "ไม่เป็นไรค่ะ"}], hint=False)
    assert payload == {"item_1": {"thai": "ไม่เป็นไรค่ะ"}}
    assert "tokens" not in gpt_teacher.build_prompt(payload, hint=False)
    assert "tokens" in gpt_teacher.build_prompt(gpt_teacher.build_payload([{"id": 7, "thai": "มา"}], True), True)


# 解析結果


def test_results_carry_version_and_original_thai(use_client):
    use_client(respond_with(GOOD))
    results = gpt_teacher.analyze_long_text(transcript("มาแล้ว"))
    assert results[0]["thai"] == "มาแล้ว"
    assert results[0]["v"] == storage.ANALYSIS_VERSION
    assert [item["word"] for item in results[0]["analysis"]] == ["มา", "แล้ว"]
    assert "resent" not in results[0]


def test_blank_words_are_dropped(use_client):
    use_client(respond_with({"มาแล้ว": [("มา", "word"), ("  ", "word"), ("แล้ว", "word")]}))
    results = gpt_teacher.analyze_long_text(transcript("มาแล้ว"))
    assert [item["word"] for item in results[0]["analysis"]] == ["มา", "แล้ว"]


def test_empty_lines_are_not_sent(use_client):
    client = use_client(respond_with(GOOD))
    results = gpt_teacher.analyze_long_text(transcript("มาแล้ว", "   "))
    assert list(results) == [0]
    assert len(client.calls) == 1


# 快取


def test_current_cache_is_reused_without_calling_openai(no_client):
    cached = {0: {"thai": "มาแล้ว", "v": storage.ANALYSIS_VERSION, **result(GOOD["มาแล้ว"])}}
    assert gpt_teacher.analyze_long_text(transcript("มาแล้ว"), cached=cached) == cached


def test_old_version_cache_is_analyzed_again(use_client):
    client = use_client(respond_with(GOOD))
    cached = {0: {"thai": "มาแล้ว", **result(GOOD["มาแล้ว"])}}
    results = gpt_teacher.analyze_long_text(transcript("มาแล้ว"), cached=cached)
    assert len(client.calls) == 1
    assert results[0]["v"] == storage.ANALYSIS_VERSION


def test_cache_for_changed_text_is_analyzed_again(use_client):
    client = use_client(respond_with(GOOD))
    cached = {0: {"thai": "ไม่เป็นไรค่ะ", "v": storage.ANALYSIS_VERSION, **result(GOOD["ไม่เป็นไรค่ะ"])}}
    gpt_teacher.analyze_long_text(transcript("มาแล้ว"), cached=cached)
    assert len(client.calls) == 1


# 檢查後重送


def test_failed_sentence_is_resent_alone_and_replaced(use_client):
    attempts = []

    def respond(payload):
        attempts.append([item["thai"] for item in payload.values()])
        table = BAD if len(attempts) == 1 else GOOD
        return {key: result(table[item["thai"]] if item["thai"] == "มาแล้ว" else GOOD[item["thai"]]) for key, item in payload.items()}

    use_client(respond)
    stats = {}
    results = gpt_teacher.analyze_long_text(transcript("ไม่เป็นไรค่ะ", "มาแล้ว"), stats=stats)
    assert attempts == [["ไม่เป็นไรค่ะ", "มาแล้ว"], ["มาแล้ว"]]
    assert [item["word"] for item in results[1]["analysis"]] == ["มา", "แล้ว"]
    assert "resent" not in results[1]
    assert stats == {"first_failed": 1, "still_failed": 0}


def test_sentence_failing_twice_keeps_first_result_and_is_not_resent_again(use_client, monkeypatch):
    client = use_client(respond_with(BAD))
    stats = {}
    results = gpt_teacher.analyze_long_text(transcript("มาแล้ว"), stats=stats)
    assert len(client.calls) == 2
    assert [item["word"] for item in results[0]["analysis"]] == ["มา"]
    assert results[0]["resent"] is True
    assert stats == {"first_failed": 1, "still_failed": 1}

    # 重跑時這一句已經重送過，不再花錢
    def fail(**kwargs):
        raise AssertionError("不應該呼叫 OpenAI")

    monkeypatch.setattr(gpt_teacher, "OpenAI", fail)
    assert gpt_teacher.analyze_long_text(transcript("มาแล้ว"), cached=results) == results


def test_cached_failure_that_was_never_resent_is_resent(use_client):
    # 上次在第一輪和重送之間中斷：快取裡有沒通過檢查、也還沒重送過的結果
    client = use_client(respond_with(GOOD))
    cached = {0: {"thai": "มาแล้ว", "v": storage.ANALYSIS_VERSION, **result(BAD["มาแล้ว"])}}
    results = gpt_teacher.analyze_long_text(transcript("มาแล้ว"), cached=cached)
    assert len(client.calls) == 1
    assert [item["word"] for item in results[0]["analysis"]] == ["มา", "แล้ว"]


def test_progress_is_reported_with_results_and_total(use_client):
    use_client(respond_with(GOOD))
    seen = []
    gpt_teacher.analyze_long_text(
        transcript("มาแล้ว", "ไม่เป็นไรค่ะ"), on_progress=lambda results, total: seen.append((len(results), total))
    )
    assert seen[0] == (0, 2)
    assert seen[-1] == (2, 2)
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_gpt_sentences.py -v`
Expected: FAIL，第一個錯誤是 `AttributeError: module 'backend.gpt_teacher' has no attribute 'segment_hint_enabled'`

- [ ] **Step 3: 實作**

把 `backend/gpt_teacher.py` 整個換成：

```python
# GPT 解析：把字幕分段送給 OpenAI，取得每一句的拼音、翻譯與單字拆解
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

from dotenv import load_dotenv
from openai import AuthenticationError, OpenAI, PermissionDeniedError, RateLimitError

from .analysis_check import check_analysis
from .segmenter import tokenize
from .storage import ANALYSIS_VERSION

load_dotenv()

MODEL = "gpt-4.1-mini"
SYSTEM_PROMPT = "你是泰語老師，要以台灣繁體中文的角度進行語言教學。"

# 同時送給 GPT 的請求數上限
MAX_WORKERS = 5

# SEGMENT_HINT 沒設定時的值：on 會把機器斷詞的結果附給 GPT 當參考
SEGMENT_HINT_DEFAULT = "on"


def segment_hint_enabled():
    return os.getenv("SEGMENT_HINT", SEGMENT_HINT_DEFAULT).strip().lower() != "off"


# 分段工具：每 N 行字幕切一段，每行帶著自己的 id
def split_transcript(transcript_with_time, max_lines=10):
    items = [
        {"id": line_id, "thai": snippet["text"].strip()}
        for line_id, snippet in transcript_with_time.items()
        if snippet["text"].strip()
    ]
    return [items[i : i + max_lines] for i in range(0, len(items), max_lines)]


# Structured outputs：OpenAI 保證回傳內容符合 schema，不需要再處理格式錯誤的 JSON。
# 每一句對應一個必填的 key（item_1、item_2...），GPT 沒辦法少回任何一句；
# 如果用陣列，GPT 有時只回前幾句就結束。
# 單字這裡只放會隨句子改變的欄位；拼音、組成這些不變的資料在詞庫（dictionary.py）。
EXPLANATION_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "rtgs": {"type": "string", "description": "整句的皇家轉寫系統拼音（RTGS），單字之間空格"},
        "translation": {"type": "string", "description": "整句的繁體中文翻譯"},
        "analysis": {
            "type": "array",
            "description": "照原句順序、涵蓋整句的單字清單",
            "items": {
                "type": "object",
                "properties": {
                    "word": {"type": "string", "description": "一個泰文詞條，和原句裡的寫法完全相同"},
                    "type": {
                        "type": "string",
                        "enum": ["word", "particle", "classifier", "name", "expression"],
                        "description": "這個字在這一句裡的類型",
                    },
                    "meaning": {"type": "string", "description": "這個字在這一句裡的繁體中文意思，要簡短"},
                    "more": {"type": "string", "description": "這一句特有的用法或句型補充，沒有就給空字串"},
                },
                "required": ["word", "type", "meaning", "more"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["rtgs", "translation", "analysis"],
    "additionalProperties": False,
}


def keyed_schema(name, item_schema, count):
    keys = [f"item_{n}" for n in range(1, count + 1)]
    return {
        "name": f"{name}_{count}",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {key: {"$ref": "#/$defs/item"} for key in keys},
            "required": keys,
            "additionalProperties": False,
            "$defs": {"item": item_schema},
        },
    }


@lru_cache(maxsize=None)
def explanation_schema(count):
    return keyed_schema("thai_explanations", EXPLANATION_ITEM_SCHEMA, count)


def is_fatal_error(e):
    """金鑰無效、沒有權限、額度用完：重試也沒用，應該中止整個任務。一般的速率限制不算。"""
    if isinstance(e, (AuthenticationError, PermissionDeniedError)):
        return True
    if isinstance(e, RateLimitError):
        reasons = (getattr(e, "type", None), getattr(e, "code", None))
        return "insufficient_quota" in reasons or "credit_balance_exhausted" in reasons
    return False


def ask_gpt(client, prompt, schema):
    """送一個請求，回傳解析好的 JSON。無法重試的錯誤往外丟，其他錯誤印出來並回傳空的結果"""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_schema", "json_schema": schema},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        if is_fatal_error(e):
            raise
        # 單一請求失敗（網路、速率限制、回應被截斷）不影響其他請求
        print(f"⚠️ GPT 請求失敗：{e}")
        return {}


def build_payload(items, hint):
    """送給 GPT 的內容：{item_n: {"thai": 原句, "tokens": 機器斷詞}}，hint 關掉時沒有 tokens"""
    payload = {}
    for n, item in enumerate(items, start=1):
        entry = {"thai": item["thai"]}
        if hint:
            entry["tokens"] = tokenize(item["thai"])
        payload[f"item_{n}"] = entry
    return payload


def build_prompt(payload, hint):
    hint_rule = (
        "\n- tokens 是機器斷詞的結果，只能當參考：人名常被切碎、慣用語常被拆散，要自己合併或修正。" if hint else ""
    )
    return f"""下面是一個 JSON 物件，每個 key（item_1、item_2...）對應一句泰文字幕（thai）。
幫我分析每一句：整句的拼音（RTGS，單字之間空格）、繁體中文翻譯，以及把整句拆成單字的清單（analysis）。

拆單字的規則：
- 以字典詞條為單位：會是泰語字典裡一個詞條的東西就是一筆。
- 照原句的順序列出每一個詞，不能漏，也不能改字；所有 word 接起來要等於原句。
- 複合詞（例如 เครื่องเขียน）和固定說法、慣用語（例如 ไม่เป็นไร）整個一筆。
- 語氣詞、量詞各自一筆。人名、品牌、外文整個一筆，不要拆。
- 數字和時間照詞拆開（例如 สองทุ่มครึ่ง 拆成 สอง、ทุ่ม、ครึ่ง）。
- 不可以把片語或子句當成一筆。
- type：一般單字（包含複合詞、疊字）是 word，語氣詞是 particle，量詞是 classifier，人名品牌外文是 name，固定說法和慣用語是 expression。
- meaning：這個字在這一句裡的意思，要簡短。
- more：只有這一句有特別的用法或句型時才寫，否則給空字串。{hint_rule}

其他規則：
- 每個 key 都要回傳一筆結果，放在相同的 key 底下。
- 逐句分析，不要合併或拆開句子，也不要省略任何一句。
- 如果泰文裡面有換行，rtgs 和 translation 也要在對應的位置換行。

這是要分析的泰文：
{json.dumps(payload, ensure_ascii=False)}"""


# 分析函式：送給 GPT 逐段分析，回傳 {id: 解析}
def gpt_teacher(client, items, hint):
    # 送出時用 item_1、item_2... 當 key，回來後再對回各句的 id
    payload = build_payload(items, hint)
    results = ask_gpt(client, build_prompt(payload, hint), explanation_schema(len(items)))

    explanations = {}
    for key, item in zip(payload, items):
        if key not in results:
            continue
        # GPT 偶爾會回空白的單字，留著的話詞庫永遠查不到它
        analysis = [word for word in results[key]["analysis"] if word["word"].strip()]
        explanations[item["id"]] = {"thai": item["thai"], "v": ANALYSIS_VERSION, **results[key], "analysis": analysis}
    return explanations


def analyze_chunk(client, chunk, hint):
    result = gpt_teacher(client, chunk, hint)

    # 沒有回傳的 id 只重試一次
    missing = [item for item in chunk if item["id"] not in result]
    if missing:
        print(f"⚠️ 有 {len(missing)} 句沒有解析，重試中...")
        result.update(gpt_teacher(client, missing, hint))

    return result


# 主流程：自動分段、並行送出並彙整，回傳 {id: 解析}
# cached：之前已經分析過的 {id: 解析}，泰文內容沒變、版本也相同的句子不會重送
# on_progress(目前的結果, 總句數)：每完成一段呼叫一次
# stats：給一個 dict 的話，會填入第一輪沒通過檢查的句數與重送後仍沒通過的句數
def analyze_long_text(transcript_with_time, max_lines=10, cached=None, on_progress=None, stats=None):
    lines = {line_id: snippet["text"].strip() for line_id, snippet in transcript_with_time.items()}
    total = sum(1 for text in lines.values() if text)

    all_results = {
        line_id: explanation
        for line_id, explanation in (cached or {}).items()
        if lines.get(line_id) and explanation.get("thai") == lines[line_id] and explanation.get("v") == ANALYSIS_VERSION
    }
    todo = {line_id: snippet for line_id, snippet in transcript_with_time.items() if line_id not in all_results}
    chunks = split_transcript(todo, max_lines=max_lines)
    print(f"⏳ 共 {total} 句，快取已有 {len(all_results)} 句，分成 {len(chunks)} 段送出分析...")
    if on_progress:
        on_progress(all_results, total)

    hint = segment_hint_enabled()
    client = None
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    first_failed = still_failed = 0
    try:
        if chunks:
            # 速率限制交給 client 自動退避重試
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), max_retries=5)
            futures = [executor.submit(analyze_chunk, client, chunk, hint) for chunk in chunks]
            for future in as_completed(futures):
                all_results.update(future.result())
                if on_progress:
                    on_progress(all_results, total)

        # 第二輪：沒通過檢查、也還沒重送過的句子，各自單獨重送一次
        failed = [
            {"id": line_id, "thai": explanation["thai"]}
            for line_id, explanation in all_results.items()
            if not explanation.get("resent") and check_analysis(explanation["thai"], explanation["analysis"])
        ]
        first_failed = len(failed)
        if failed:
            print(f"⚠️ 有 {first_failed} 句沒通過檢查，重送中...")
            client = client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"), max_retries=5)
            futures = {executor.submit(gpt_teacher, client, [item], hint): item for item in failed}
            for future in as_completed(futures):
                line_id = futures[future]["id"]
                retry = future.result().get(line_id)
                problems = check_analysis(retry["thai"], retry["analysis"]) if retry else ["沒有回應"]
                if problems:
                    # 保留第一次的結果，並記下已經重送過，之後重跑不再花錢
                    still_failed += 1
                    all_results[line_id] = {**all_results[line_id], "resent": True}
                    print(f"⚠️ 第 {line_id} 句重送後仍沒通過檢查：{'；'.join(problems)}")
                else:
                    all_results[line_id] = retry
            if on_progress:
                on_progress(all_results, total)
    finally:
        # 遇到無法重試的錯誤時，還沒開始的請求不要再送
        executor.shutdown(wait=False, cancel_futures=True)

    if stats is not None:
        stats.update(first_failed=first_failed, still_failed=still_failed)
    if len(all_results) < total:
        print(f"⚠️ 共有 {total - len(all_results)} 句沒有解析")
    return all_results
```

- [ ] **Step 4: 執行測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_gpt_sentences.py -v`
Expected: 14 passed

- [ ] **Step 5: 執行全部測試**

Run: `.venv/bin/python -m pytest -q`
Expected: 全部通過，沒有 failed

- [ ] **Step 6: Commit**

```bash
git add backend/gpt_teacher.py tests/test_gpt_sentences.py
git commit -m "Segment sentences into dictionary words and resend failed checks

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 查詞（替詞庫補上沒看過的字）

**Files:**
- Modify: `backend/gpt_teacher.py`（在檔案最後加入）
- Test: `tests/test_gpt_dictionary.py`

**Interfaces:**
- Consumes: `ask_gpt(client, prompt, schema) -> dict`, `keyed_schema(name, item_schema, count)`, `MAX_WORKERS`（都在 `gpt_teacher.py`）；`dictionary.add_entries(entries) -> dict`；`tests.conftest.FakeClient`；fixture `data_dir`
- Produces: `lookup_missing_words(missing: dict, on_progress=None) -> int`。`missing` 是 `{字: 例句}`；查到的字寫進詞庫；`on_progress(已查到的字數, 總字數)` 每完成一批呼叫一次；回傳沒查到的字數。

- [ ] **Step 1: 寫會失敗的測試**

`tests/test_gpt_dictionary.py`：

```python
import pytest

from backend import gpt_teacher
from backend.dictionary import add_entries, load_dictionary
from tests.conftest import FakeClient


def entry_for(word):
    return {"rtgs": f"rtgs-{word}", "parts": [], "senses": "意思", "usage": "用法"}


def respond(payload):
    return {key: entry_for(item["word"]) for key, item in payload.items()}


@pytest.fixture
def use_client(monkeypatch):
    def install(respond_function):
        client = FakeClient(respond_function)
        monkeypatch.setattr(gpt_teacher, "OpenAI", lambda **kwargs: client)
        return client

    return install


def test_words_are_looked_up_and_saved(data_dir, use_client):
    client = use_client(respond)
    left = gpt_teacher.lookup_missing_words({"มา": "มาแล้ว", "แล้ว": "มาแล้ว"})
    assert left == 0
    assert load_dictionary() == {"มา": entry_for("มา"), "แล้ว": entry_for("แล้ว")}
    assert client.calls == [
        {"item_1": {"word": "มา", "example": "มาแล้ว"}, "item_2": {"word": "แล้ว", "example": "มาแล้ว"}}
    ]


def test_words_are_sent_in_batches_of_forty(data_dir, use_client):
    client = use_client(respond)
    missing = {f"ก{index}": "例句" for index in range(45)}
    progress = []
    left = gpt_teacher.lookup_missing_words(missing, on_progress=lambda done, total: progress.append((done, total)))
    assert left == 0
    assert sorted(len(call) for call in client.calls) == [5, 40]
    assert len(load_dictionary()) == 45
    assert progress[-1] == (45, 45)


def test_nothing_to_look_up_does_not_call_openai(data_dir, monkeypatch):
    def fail(**kwargs):
        raise AssertionError("不應該呼叫 OpenAI")

    monkeypatch.setattr(gpt_teacher, "OpenAI", fail)
    assert gpt_teacher.lookup_missing_words({}) == 0


def test_failed_batch_is_retried_once(data_dir, use_client):
    attempts = []

    def flaky(payload):
        attempts.append(len(payload))
        if len(attempts) == 1:
            raise RuntimeError("網路斷線")
        return respond(payload)

    use_client(flaky)
    assert gpt_teacher.lookup_missing_words({"มา": "มาแล้ว"}) == 0
    assert attempts == [1, 1]
    assert "มา" in load_dictionary()


def test_words_that_keep_failing_are_reported_and_do_not_crash(data_dir, use_client):
    def broken(payload):
        raise RuntimeError("網路斷線")

    client = use_client(broken)
    assert gpt_teacher.lookup_missing_words({"มา": "มาแล้ว", "แล้ว": "มาแล้ว"}) == 2
    assert len(client.calls) == 2
    assert load_dictionary() == {}


def test_existing_dictionary_words_are_kept(data_dir, use_client):
    add_entries({"มา": {"rtgs": "ma", "parts": [], "senses": "來", "usage": ""}})
    use_client(respond)
    gpt_teacher.lookup_missing_words({"มา": "มาแล้ว"})
    assert load_dictionary()["มา"]["rtgs"] == "ma"
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_gpt_dictionary.py -v`
Expected: FAIL，`AttributeError: module 'backend.gpt_teacher' has no attribute 'lookup_missing_words'`

- [ ] **Step 3: 實作**

在 `backend/gpt_teacher.py` 開頭的匯入，把

```python
from .analysis_check import check_analysis
```

改成

```python
from .analysis_check import check_analysis
from .dictionary import add_entries
```

並把檔案第一行的註解改成：

```python
# GPT 解析：把字幕分段送給 OpenAI，取得每一句的拼音、翻譯與單字拆解；另外替詞庫查沒看過的字
```

在檔案最後加上：

```python
# ── 查詞：替詞庫補上沒看過的字 ──

# 一個請求查幾個字
DICTIONARY_BATCH_SIZE = 40

DICTIONARY_ENTRY_SCHEMA = {
    "type": "object",
    "properties": {
        "rtgs": {"type": "string", "description": "這個字的皇家轉寫系統拼音（RTGS）"},
        "parts": {
            "type": "array",
            "description": "複合詞或固定說法的組成；不是的話給空陣列",
            "items": {
                "type": "object",
                "properties": {
                    "word": {"type": "string", "description": "組成的泰文"},
                    "rtgs": {"type": "string", "description": "組成的 RTGS 拼音"},
                    "meaning": {"type": "string", "description": "組成的繁體中文意思"},
                },
                "required": ["word", "rtgs", "meaning"],
                "additionalProperties": False,
            },
        },
        "senses": {"type": "string", "description": "常見的繁體中文意思，多個用「、」隔開，最多三個"},
        "usage": {"type": "string", "description": "一般的用法說明，一到兩句"},
    },
    "required": ["rtgs", "parts", "senses", "usage"],
    "additionalProperties": False,
}


@lru_cache(maxsize=None)
def dictionary_schema(count):
    return keyed_schema("thai_dictionary", DICTIONARY_ENTRY_SCHEMA, count)


def build_dictionary_prompt(payload):
    return f"""下面是一個 JSON 物件，每個 key（item_1、item_2...）對應一個泰文詞條（word），以及它出現過的一句例句（example）。
幫每個詞條寫字典資料：
- rtgs：這個字的拼音（RTGS）。
- parts：複合詞或固定說法才填，列出組成的每個字（泰文、RTGS、繁體中文意思）；不是的話給空陣列。
- senses：這個字常見的意思，用繁體中文，多個意思用「、」隔開，最多三個。
- usage：一般的用法說明，一到兩句。語氣詞說明語氣和誰會用，量詞說明配什麼名詞；人名、品牌、外文只要寫明是什麼。

規則：
- 說明這個字一般的用法。例句只是幫你判斷是哪個字，不要只解釋例句裡的意思。
- 每個 key 都要回傳一筆結果，放在相同的 key 底下。

這是要查的詞條：
{json.dumps(payload, ensure_ascii=False)}"""


def lookup_words(client, batch):
    """batch：[{"word", "example"}]，回傳 {字: 詞庫資料}"""
    payload = {f"item_{n}": item for n, item in enumerate(batch, start=1)}
    results = ask_gpt(client, build_dictionary_prompt(payload), dictionary_schema(len(batch)))
    return {item["word"]: results[key] for key, item in payload.items() if key in results}


def lookup_batch(client, batch):
    entries = lookup_words(client, batch)

    # 沒查到的字只重試一次
    missing = [item for item in batch if item["word"] not in entries]
    if missing:
        print(f"⚠️ 有 {len(missing)} 個字沒有查到，重試中...")
        entries.update(lookup_words(client, missing))

    return entries


# missing：{字: 例句}。分批並行查詞，每完成一批就寫進詞庫；回傳沒查到的字數
# on_progress(已查到的字數, 總字數)：每完成一批呼叫一次
def lookup_missing_words(missing, on_progress=None):
    words = [{"word": word, "example": example} for word, example in missing.items()]
    if not words:
        return 0
    batches = [words[i : i + DICTIONARY_BATCH_SIZE] for i in range(0, len(words), DICTIONARY_BATCH_SIZE)]
    print(f"⏳ 詞庫缺 {len(words)} 個字，分成 {len(batches)} 批查詢...")

    done = 0
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), max_retries=5)
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    try:
        futures = [executor.submit(lookup_batch, client, batch) for batch in batches]
        for future in as_completed(futures):
            entries = future.result()
            add_entries(entries)
            done += len(entries)
            if on_progress:
                on_progress(done, len(words))
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    if done < len(words):
        print(f"⚠️ 共有 {len(words) - done} 個字沒有查到")
    return len(words) - done
```

- [ ] **Step 4: 執行測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_gpt_dictionary.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add backend/gpt_teacher.py tests/test_gpt_dictionary.py
git commit -m "Look up unseen words in batches and store them in the dictionary

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 任務流程（解析 → 查詞 → 合併存檔）

**Files:**
- Modify: `backend/jobs.py`
- Test: `tests/test_jobs.py`

**Interfaces:**
- Consumes:
  - `gpt_teacher.analyze_long_text(transcript_with_time, cached=None, on_progress=None) -> dict`
  - `gpt_teacher.lookup_missing_words(missing, on_progress=None) -> int`
  - `dictionary.load_dictionary() -> dict`, `dictionary.missing_words(explanations, dictionary) -> dict`, `dictionary.merge_explanation(explanation, dictionary) -> dict`
  - `storage.is_subtitle_complete(video_id)`、fixture `data_dir`、`tests.conftest.FakeClient`
- Produces: `long_analyze_and_save(video_id, refetch_transcript=False)` 寫出的字幕檔，每句的 `explanation.analysis` 每筆都有 `word`、`type`、`meaning`、`more`、`rtgs`、`parts`、`senses`、`usage`。查詞期間 `jobs[video_id]` 是 `{"status": "running", "stage": "dictionary", "done", "total", "message": "建立詞庫中"}`。

- [ ] **Step 1: 寫會失敗的測試**

`tests/test_jobs.py`：

```python
import pytest

from backend import gpt_teacher, jobs, storage
from backend.dictionary import add_entries
from tests.conftest import FakeClient

VIDEO_ID = "aaaaaaaaaaa"
ANALYSES = {
    "มาแล้ว": [("มา", "word"), ("แล้ว", "word")],
    "ไม่เป็นไรค่ะ": [("ไม่เป็นไร", "expression"), ("ค่ะ", "particle")],
}


def entry_for(word):
    return {"rtgs": f"rtgs-{word}", "parts": [], "senses": "意思", "usage": "用法"}


def respond(payload, skip=()):
    """同一個假 client 同時回答逐句解析（有 thai）和查詞（有 word）；skip 裡的字查詞時會失敗"""
    results = {}
    for key, item in payload.items():
        if "thai" in item:
            results[key] = {
                "rtgs": "rtgs",
                "translation": "翻譯",
                "analysis": [
                    {"word": word, "type": kind, "meaning": "意思", "more": ""} for word, kind in ANALYSES[item["thai"]]
                ],
            }
        elif item["word"] in skip:
            raise RuntimeError("網路斷線")
        else:
            results[key] = entry_for(item["word"])
    return results


@pytest.fixture
def video(data_dir):
    storage.save_json_file(
        storage.transcript_file(VIDEO_ID),
        {"0": {"text": "มาแล้ว", "start": 0}, "1": {"text": "ไม่เป็นไรค่ะ", "start": 1}, "2": {"text": " ", "start": 2}},
    )
    jobs.jobs.clear()
    jobs.start_job(VIDEO_ID)
    yield
    jobs.jobs.clear()


def install(monkeypatch, respond_function):
    client = FakeClient(respond_function)
    monkeypatch.setattr(gpt_teacher, "OpenAI", lambda **kwargs: client)
    return client


def saved_subtitles():
    return storage.load_json_file(storage.subtitle_file(VIDEO_ID))


def test_subtitles_are_saved_with_sentence_and_dictionary_fields(video, monkeypatch):
    install(monkeypatch, respond)
    jobs.long_analyze_and_save(VIDEO_ID)

    subtitles = saved_subtitles()
    assert subtitles["0"]["start"] == 0
    assert subtitles["0"]["explanation"]["analysis"][0] == {
        "word": "มา",
        "type": "word",
        "meaning": "意思",
        "more": "",
        "rtgs": "rtgs-มา",
        "parts": [],
        "senses": "意思",
        "usage": "用法",
    }
    assert "explanation" not in subtitles["2"]
    assert storage.is_subtitle_complete(VIDEO_ID)
    assert jobs.jobs[VIDEO_ID] == {"status": "done", "stage": "done", "done": 2, "total": 2, "message": ""}


def test_known_words_are_not_looked_up_again(video, monkeypatch):
    add_entries({word: entry_for(word) for word in ("มา", "แล้ว", "ไม่เป็นไร")})
    client = install(monkeypatch, respond)
    jobs.long_analyze_and_save(VIDEO_ID)

    lookups = [call for call in client.calls if "word" in call["item_1"]]
    assert lookups == [{"item_1": {"word": "ค่ะ", "example": "ไม่เป็นไรค่ะ"}}]


def test_failed_lookup_leaves_partial_lines_and_a_hint(video, monkeypatch):
    install(monkeypatch, lambda payload: respond(payload, skip=("มา", "แล้ว", "ไม่เป็นไร", "ค่ะ")))
    jobs.long_analyze_and_save(VIDEO_ID)

    subtitles = saved_subtitles()
    assert subtitles["0"]["explanation"]["partial"] is True
    assert subtitles["0"]["explanation"]["analysis"][0]["meaning"] == "意思"
    assert not storage.is_subtitle_complete(VIDEO_ID)
    assert jobs.jobs[VIDEO_ID]["status"] == "done"
    assert "2 句的單字還沒有詞庫資料" in jobs.jobs[VIDEO_ID]["message"]


def test_rerun_after_failed_lookup_only_looks_up_words(video, monkeypatch):
    install(monkeypatch, lambda payload: respond(payload, skip=("มา", "แล้ว", "ไม่เป็นไร", "ค่ะ")))
    jobs.long_analyze_and_save(VIDEO_ID)

    _, should_run = jobs.start_job(VIDEO_ID)
    assert should_run
    client = install(monkeypatch, respond)
    jobs.long_analyze_and_save(VIDEO_ID)

    assert all("word" in call["item_1"] for call in client.calls)  # 沒有重新解析句子
    assert storage.is_subtitle_complete(VIDEO_ID)
    assert "partial" not in saved_subtitles()["0"]["explanation"]
    assert jobs.jobs[VIDEO_ID]["message"] == ""


def test_dictionary_stage_is_reported(video, monkeypatch):
    stages = []

    def recording(payload):
        stages.append(dict(jobs.jobs[VIDEO_ID]))
        return respond(payload)

    install(monkeypatch, recording)
    jobs.long_analyze_and_save(VIDEO_ID)

    assert stages[-1] == {"status": "running", "stage": "dictionary", "done": 0, "total": 4, "message": "建立詞庫中"}
```

- [ ] **Step 2: 執行測試確認失敗**

Run: `.venv/bin/python -m pytest tests/test_jobs.py -v`
Expected: FAIL。第一個測試的錯誤是 `KeyError: 'rtgs'` 或斷言 `analysis[0]` 不相等（目前還沒有合併詞庫）。

- [ ] **Step 3: 實作**

在 `backend/jobs.py`：

把第一行註解和匯入改成：

```python
# 抓取任務：抓字幕 → GPT 逐句解析 → 查詞庫沒有的字 → 合併存檔，以及任務進度的記錄
import threading

from .dictionary import load_dictionary, merge_explanation, missing_words
from .gpt_teacher import analyze_long_text, is_fatal_error, lookup_missing_words
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
```

把 `jobs` 上方的狀態註解改成：

```python
# 任務狀態只存在記憶體裡，後端重啟就會清空
# {video_id: {"status": "running" | "done" | "error", "stage", "done", "total", "message"}}
# stage 是 analyzing 時 done / total 是句數，dictionary 時是字數
```

把 `long_analyze_and_save` 從 `response = analyze_long_text(...)` 那一行開始到函式結尾，換成：

```python
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
```

- [ ] **Step 4: 執行測試確認通過**

Run: `.venv/bin/python -m pytest tests/test_jobs.py -v`
Expected: 5 passed

- [ ] **Step 5: 執行全部測試**

Run: `.venv/bin/python -m pytest -q`
Expected: 全部通過，沒有 failed

- [ ] **Step 6: Commit**

```bash
git add backend/jobs.py tests/test_jobs.py
git commit -m "Run dictionary lookup after analysis and merge it into saved subtitles

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: 前端單字卡與 Forvo 連結

**Files:**
- Modify: `frontend/src/VideoSubtitleApp.jsx`

**Interfaces:**
- Consumes: `GET /subtitles/{video_id}` 的 `explanation.analysis[]`。新資料每筆有 `word`、`type`、`meaning`、`more`、`rtgs`、`parts`（`[{word, rtgs, meaning}]`）、`senses`、`usage`；舊資料只有 `word`、`rtgs`、`meaning`、`more`。`GET /status/{video_id}` 的 `stage` 可能是 `dictionary`。
- Produces: `forvoUrl(word)`、`WordCard({ item })`。

- [ ] **Step 1: 決定 Forvo 的網址格式**

用瀏覽器分別打開：

- `https://forvo.com/search/%E0%B8%8A%E0%B8%B7%E0%B9%88%E0%B8%AD/`
- `https://forvo.com/search/%E0%B8%8A%E0%B8%B7%E0%B9%88%E0%B8%AD/th/`

判斷：第二個網址如果正常顯示搜尋結果、而且只列出泰語的結果，`forvoUrl` 就用帶 `/th/` 的格式；如果是錯誤頁、被導走，或結果和第一個一樣，就用第一個格式。把選用的格式和原因寫在 commit 訊息裡。

- [ ] **Step 2: 加入圖示、網址與標籤**

在 `lucide-react` 的匯入清單裡，`ChevronRight,` 後面加一行 `Headphones,`（清單是照字母排序的）。

在 `iconButtonClass` 的定義後面加上：

```jsx
// Forvo 的搜尋頁：沒收錄的字也會顯示相近的結果，不會是 404
const forvoUrl = (word) => `https://forvo.com/search/${encodeURIComponent(word)}/`;
const FORVO_LABEL = "在 Forvo 聽真人發音（另開分頁）";

// 單字類型的標籤；一般單字（word）不顯示
const WORD_TYPE_LABELS = {
  particle: "語氣詞",
  classifier: "量詞",
  name: "專有名詞",
  expression: "固定說法",
};
```

如果 Step 1 決定用 `/th/`，把 `forvoUrl` 的結尾改成 `/th/`，並把註解改成「Forvo 的泰語搜尋頁」。

- [ ] **Step 3: 加入 `WordCard` 元件**

在 `// 小元件：目前這句字幕與它的解析` 這行註解的前面加上：

```jsx
// 小元件：單字解析裡的一張卡片。
// 舊版的解析沒有 type、parts、senses、usage，少了這些欄位時照常顯示其餘的部分
function WordCard({ item }) {
  const typeLabel = WORD_TYPE_LABELS[item.type];
  return (
    <li className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-baseline gap-x-2">
          <span className="text-lg font-semibold text-slate-900 dark:text-white">{item.word}</span>
          <span className="text-sm text-indigo-600 dark:text-indigo-300">{item.rtgs}</span>
          {typeLabel && (
            <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-700 dark:text-slate-300">
              {typeLabel}
            </span>
          )}
        </div>
        {/* 人名、品牌這類專有名詞 Forvo 通常沒有收錄 */}
        {item.type !== "name" && (
          <a
            href={forvoUrl(item.word)}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={FORVO_LABEL}
            title={FORVO_LABEL}
            className={`${iconButtonClass} -my-1.5 -mr-1.5`}
          >
            <Headphones size={16} />
          </a>
        )}
      </div>
      <p className="text-sm text-slate-700 dark:text-slate-200">{item.meaning}</p>
      {item.parts?.length > 0 && (
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
          {item.parts.map((part, index) => (
            <React.Fragment key={index}>
              {index > 0 && " + "}
              <a
                href={forvoUrl(part.word)}
                target="_blank"
                rel="noopener noreferrer"
                title={FORVO_LABEL}
                className="focus-ring rounded font-semibold underline decoration-dotted underline-offset-2 hover:text-indigo-600 dark:hover:text-indigo-300"
              >
                {part.word}
              </a>{" "}
              {part.rtgs} {part.meaning}
            </React.Fragment>
          ))}
        </p>
      )}
      {item.more && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{item.more}</p>}
      {item.senses && item.senses !== item.meaning && (
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">常見意思：{item.senses}</p>
      )}
      {item.usage && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{item.usage}</p>}
    </li>
  );
}
```

- [ ] **Step 4: 讓 `SubtitlePanel` 使用 `WordCard`**

在 `SubtitlePanel` 裡，把

```jsx
                {explanation.analysis.map((item, index) => (
                  <li key={index} className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/60">
                    <div className="flex flex-wrap items-baseline gap-x-2">
                      <span className="text-lg font-semibold text-slate-900 dark:text-white">{item.word}</span>
                      <span className="text-sm text-indigo-600 dark:text-indigo-300">{item.rtgs}</span>
                    </div>
                    <p className="text-sm text-slate-700 dark:text-slate-200">{item.meaning}</p>
                    {item.more && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{item.more}</p>}
                  </li>
                ))}
```

換成

```jsx
                {explanation.analysis.map((item, index) => (
                  <WordCard key={index} item={item} />
                ))}
```

- [ ] **Step 5: 進度的單位在查詞時顯示「字」**

把任務進度那一段的

```jsx
                  {job.done} / {job.total} 句
```

換成

```jsx
                  {job.done} / {job.total} {job.stage === "dictionary" ? "字" : "句"}
```

並把檔案裡說明任務狀態的註解

```jsx
  // 後端回報的抓取任務狀態：{ videoId, status, stage, done, total, message }
```

改成

```jsx
  // 後端回報的抓取任務狀態：{ videoId, status, stage, done, total, message }
  // stage 是 dictionary（建立詞庫）時 done / total 是字數，其餘是句數
```

- [ ] **Step 6: Lint 與 build**

```bash
cd frontend && npm install && npm run lint && npm run build
```

Expected: lint 沒有 error，build 成功輸出 `dist/`。

- [ ] **Step 7: 用舊資料實際檢查畫面**

開兩個終端機：`.venv/bin/uvicorn backend.api_server:app --reload` 和 `cd frontend && npm run dev`，打開 <http://localhost:5173>。這時 `data/subtitles/` 裡的都還是舊格式，逐項確認：

- 影片庫裡所有舊影片都顯示為解析未完成。
- 打開 `7tMkVWSWePg` 播放：單字卡照常顯示單字、拼音、意思和補充，沒有類型標籤，也沒有「常見意思」這幾行；console 沒有錯誤。
- 每張卡片右上角有耳機圖示，滑鼠移上去顯示「在 Forvo 聽真人發音（另開分頁）」；點了會另開分頁到 Step 1 選定的 Forvo 網址，網址裡的字和卡片上的字相同。
- 用 Tab 鍵可以聚焦到耳機圖示，有 focus 外框。
- 切換深色模式，卡片和圖示的對比正常。
- 視窗縮到 375px 寬：卡片變成單欄，單字、拼音和耳機圖示沒有重疊，也沒有超出卡片。

新格式的顯示（標籤、組成、常見意思）在 Task 10 重跑範例後檢查。

- [ ] **Step 8: Commit**

```bash
git add frontend/src/VideoSubtitleApp.jsx
git commit -m "Add Forvo links, word type labels and word parts to vocabulary cards

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: 對照實驗，決定 `SEGMENT_HINT` 的預設值

**Files:**
- Create: `scripts/compare_segmentation.py`
- Modify: `backend/gpt_teacher.py`（只在結果是 `off` 時改 `SEGMENT_HINT_DEFAULT`）

**Interfaces:**
- Consumes: `gpt_teacher.analyze_long_text(transcript, stats=…)`、`gpt_teacher.lookup_missing_words(missing)`、`gpt_teacher.OpenAI`、`dictionary.missing_words`、`dictionary.load_dictionary`、`analysis_check.check_analysis`、`storage.DATA_DIR`
- Produces: 每一組一個 `<out>/<label>.json`，以及印在終端機的比較表。

- [ ] **Step 1: 寫對照實驗的腳本**

`scripts/compare_segmentation.py`：

```python
# 對照實驗：同一批字幕分別用舊版、SEGMENT_HINT=on、SEGMENT_HINT=off 跑一次，
# 比較拆詞結果、耗時與 token 用量。每一組從空的詞庫開始，結果寫到 --out，不會動到 data/。
#
# 每一組各跑一次（舊版要先把 main 另外 checkout 出來，--backend-root 指到那裡）：
#   python scripts/compare_segmentation.py run --label old --backend-root <main 的目錄> --out <輸出目錄>
#   python scripts/compare_segmentation.py run --label on  --out <輸出目錄>
#   python scripts/compare_segmentation.py run --label off --out <輸出目錄>
# 全部跑完後：
#   python scripts/compare_segmentation.py report --out <輸出目錄>
import argparse
import collections
import inspect
import json
import os
import sys
import threading
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (影片 ID, 取前幾句)；None 是全部
SAMPLES = [("7tMkVWSWePg", None), ("muCvDSOJwSs", 60)]
LABELS = ["old", "on", "off"]


def load_sample(data_dir):
    transcript = {}
    for video_id, limit in SAMPLES:
        with open(os.path.join(data_dir, "subtitles", f"{video_id}.json"), encoding="utf-8") as f:
            saved = json.load(f)
        texts = [line["text"] for _, line in sorted(saved.items(), key=lambda pair: int(pair[0])) if line["text"].strip()]
        for text in texts[:limit]:
            transcript[len(transcript)] = {"text": text}
    return transcript


def run(args):
    from dotenv import load_dotenv

    load_dotenv(args.env_file)
    if args.label != "old":
        os.environ["SEGMENT_HINT"] = args.label
    sys.path.insert(0, os.path.abspath(args.backend_root))
    from backend import gpt_teacher, storage

    # 詞庫寫到這一組自己的暫存目錄
    storage.DATA_DIR = os.path.join(os.path.abspath(args.out), f"data-{args.label}")

    # 包住 OpenAI client，記下每個請求的 token 用量
    usage = collections.Counter()
    lock = threading.Lock()
    real_openai = gpt_teacher.OpenAI

    def recording_openai(**kwargs):
        client = real_openai(**kwargs)
        create = client.chat.completions.create

        def recorded(**request):
            response = create(**request)
            name = request["response_format"]["json_schema"]["name"]
            stage = "dictionary" if name.startswith("thai_dictionary") else "sentences"
            with lock:
                usage[f"{stage}_requests"] += 1
                usage[f"{stage}_prompt_tokens"] += response.usage.prompt_tokens
                usage[f"{stage}_completion_tokens"] += response.usage.completion_tokens
            return response

        client.chat.completions.create = recorded
        return client

    gpt_teacher.OpenAI = recording_openai

    transcript = load_sample(args.data_dir)
    stats = {}
    extra = {"stats": stats} if "stats" in inspect.signature(gpt_teacher.analyze_long_text).parameters else {}
    started = time.perf_counter()
    results = gpt_teacher.analyze_long_text(transcript, **extra)
    seconds_sentences = time.perf_counter() - started

    seconds_dictionary = 0.0
    words_left = None
    if hasattr(gpt_teacher, "lookup_missing_words"):
        from backend.dictionary import load_dictionary, missing_words

        started = time.perf_counter()
        words_left = gpt_teacher.lookup_missing_words(missing_words(results, load_dictionary()))
        seconds_dictionary = time.perf_counter() - started

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, f"{args.label}.json"), "w", encoding="utf-8") as f:
        json.dump(
            {
                "label": args.label,
                "lines": len(transcript),
                "results": {str(line_id): explanation for line_id, explanation in results.items()},
                "stats": stats,
                "seconds_sentences": seconds_sentences,
                "seconds_dictionary": seconds_dictionary,
                "words_left": words_left,
                "usage": dict(usage),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"{args.label}：{len(results)} / {len(transcript)} 句，逐句解析 {seconds_sentences:.1f} 秒，查詞 {seconds_dictionary:.1f} 秒")


def report(args):
    sys.path.insert(0, REPO_ROOT)
    from backend.analysis_check import check_analysis

    rows = []
    for label in LABELS:
        path = os.path.join(args.out, f"{label}.json")
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        results = data["results"].values()
        words = [item["word"] for explanation in results for item in explanation["analysis"]]
        failing = sum(1 for explanation in results if check_analysis(explanation["thai"], explanation["analysis"]))
        usage = data["usage"]
        rows.append(
            [
                label,
                f"{len(data['results'])}/{data['lines']}",
                # 舊版沒有重送，第一輪沒通過的就是最後沒通過的
                data["stats"].get("first_failed", failing),
                failing,
                len(words),
                f"{sum(1 for word in words if len(word) >= 10) / max(len(words), 1) * 100:.1f}%",
                f"{data['seconds_sentences']:.1f}",
                usage.get("sentences_prompt_tokens", 0),
                usage.get("sentences_completion_tokens", 0),
                f"{data['seconds_dictionary']:.1f}",
                usage.get("dictionary_prompt_tokens", 0),
                usage.get("dictionary_completion_tokens", 0),
            ]
        )

    header = [
        "組別", "有解析", "第一輪沒過", "最後沒過", "單字數", "長度≥10",
        "逐句秒數", "逐句輸入", "逐句輸出", "查詞秒數", "查詞輸入", "查詞輸出",
    ]
    for row in [header] + rows:
        print(" | ".join(str(cell) for cell in row))


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    run_parser = commands.add_parser("run")
    run_parser.add_argument("--label", choices=LABELS, required=True)
    run_parser.add_argument("--backend-root", default=REPO_ROOT)
    run_parser.add_argument("--data-dir", default=os.path.join(REPO_ROOT, "data"))
    run_parser.add_argument("--env-file", default=os.path.join(REPO_ROOT, ".env"))
    run_parser.add_argument("--out", required=True)
    run_parser.set_defaults(handler=run)

    report_parser = commands.add_parser("report")
    report_parser.add_argument("--out", required=True)
    report_parser.set_defaults(handler=report)

    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 確認腳本不花錢的部分可以執行**

```bash
.venv/bin/python scripts/compare_segmentation.py report --out /tmp/does-not-exist
ls data/subtitles/7tMkVWSWePg.json data/subtitles/muCvDSOJwSs.json
```

Expected: 第一個指令只印出表頭那一行、沒有錯誤；第二個指令兩個檔案都存在。`muCvDSOJwSs.json` 不在版本控制裡，如果不存在，停下來告訴使用者。

- [ ] **Step 3: Commit 腳本**

```bash
git add scripts/compare_segmentation.py
git commit -m "Add script to compare segmentation variants

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 4: 取得使用者同意後才執行（會花 OpenAI 費用）**

先問使用者：「對照實驗要用 103 句字幕跑三組（舊版、on、off），會用到你的 OpenAI 金鑰並產生費用，可以執行嗎？」沒有明確同意就不要執行，直接跳到 Task 10，並在最後回報這一步沒有做、`SEGMENT_HINT` 的預設值維持 `on`。

同意後：

```bash
OUT="$(mktemp -d)"
git worktree add "$OUT/main" main
.venv/bin/python scripts/compare_segmentation.py run --label old --backend-root "$OUT/main" --out "$OUT"
.venv/bin/python scripts/compare_segmentation.py run --label on --out "$OUT"
.venv/bin/python scripts/compare_segmentation.py run --label off --out "$OUT"
.venv/bin/python scripts/compare_segmentation.py report --out "$OUT"
git worktree remove "$OUT/main"
```

Expected: 三組各印出一行 `<組別>：103 / 103 句，…`，`report` 印出表頭加三列。任何一組的「有解析」不是 `103/103` 時，先看那一組的終端機輸出找原因，不要直接比較。

- [ ] **Step 5: 依結果設定預設值**

比較 `on` 和 `off` 兩列的「最後沒過」：

- `on` 比 `off` 少：維持 `SEGMENT_HINT_DEFAULT = "on"`，不用改程式。
- 相同，或 `on` 比較多：把 `backend/gpt_teacher.py` 的 `SEGMENT_HINT_DEFAULT = "on"` 改成 `"off"`，註解改成 `# SEGMENT_HINT 沒設定時的值：on 會把機器斷詞的結果附給 GPT 當參考（對照實驗顯示沒有幫助，所以預設關閉）`，然後執行 `.venv/bin/python -m pytest -q` 確認全部通過。

把整張比較表貼給使用者，並說明選了哪個預設值、新版和舊版相比的耗時與 token 差異。

- [ ] **Step 6: Commit（有改預設值才需要）**

```bash
git add backend/gpt_teacher.py
git commit -m "Default SEGMENT_HINT to off based on comparison results

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: 重跑範例、更新 README、最後驗證

**Files:**
- Modify: `data/subtitles/1Sk8kiYfZGg.json`, `data/subtitles/7tMkVWSWePg.json`, `README.md`, `README.en.md`

**Interfaces:**
- Consumes: 執行中的後端（`POST /analyze`、`GET /status/{video_id}`）與前端。

- [ ] **Step 1: 取得使用者同意後重跑兩支範例（會花 OpenAI 費用）**

先問使用者：「要重跑 repo 裡的兩支範例影片（共 206 句），會用到你的 OpenAI 金鑰並產生費用，可以執行嗎？」沒有明確同意就跳過 Step 1–3，並在最後回報範例還是舊格式。

同意後，啟動後端（`.venv/bin/uvicorn backend.api_server:app`），然後：

```bash
for id in 1Sk8kiYfZGg 7tMkVWSWePg; do
  curl -s -X POST http://127.0.0.1:8000/analyze -H 'Content-Type: application/json' -d "{\"video_id\": \"$id\"}"
  echo
  until curl -s "http://127.0.0.1:8000/status/$id" | grep -Eq '"status":"(done|error)"'; do sleep 5; done
  curl -s "http://127.0.0.1:8000/status/$id"; echo
done
```

Expected: 兩支最後都是 `"status":"done"` 而且 `"message":""`。`message` 不是空的話，對同一支再送一次 `/analyze`（只會補缺的部分）；還是不行就把訊息回報給使用者。

- [ ] **Step 2: 量重跑後的結果**

```bash
.venv/bin/python - <<'EOF'
import json
from backend.analysis_check import check_analysis

for video_id in ("1Sk8kiYfZGg", "7tMkVWSWePg"):
    with open(f"data/subtitles/{video_id}.json", encoding="utf-8") as f:
        lines = [line["explanation"] for line in json.load(f).values() if "explanation" in line]
    words = [item for line in lines for item in line["analysis"]]
    failing = sum(1 for line in lines if check_analysis(line["thai"], line["analysis"]))
    long_words = sum(1 for item in words if len(item["word"]) >= 10 and item["type"] != "name")
    print(video_id, f"{len(lines)} 句、{len(words)} 個字、沒通過檢查 {failing} 句、長度≥10 的非專有名詞 {long_words} 個")
EOF
```

把這兩行數字記下來，最後要回報給使用者。重跑前的基準（寫計畫時量到的）：兩支合計 877 筆單字，長度 10 以上的有 8 筆。

- [ ] **Step 3: 用新資料檢查畫面**

啟動前端（`cd frontend && npm run dev`），打開 <http://localhost:5173>，逐項確認：

- 影片庫裡這兩支顯示為解析完整，其他舊影片仍是未完成。
- 打開 `7tMkVWSWePg`：語氣詞（例如 `ค่ะ`）有「語氣詞」標籤；人名有「專有名詞」標籤而且沒有耳機圖示。
- 找一張有組成的卡片：顯示「泰文 拼音 意思 + 泰文 拼音 意思」，點組成的泰文會另開 Forvo。
- 「常見意思」那一行只在和本句意思不同時出現。
- 同一個字在不同句子的拼音相同。
- 深色模式和 375px 寬度下，多出來的幾行不會溢出卡片。
- console 沒有錯誤。

- [ ] **Step 4: 更新 `README.md`**

「功能」清單裡，把「同步字幕」那一項換成下面兩項：

```markdown
- **同步字幕**：播放時顯示目前這句的泰文、拼音、翻譯和單字解析。
- **單字卡**：整句拆成一個個字典詞條，標出語氣詞、量詞、專有名詞和固定說法，複合詞會列出組成；每張卡片可以另開 [Forvo](https://forvo.com/) 聽真人發音。
```

「事前準備」裡，在「朗讀用的聲音可以在 `.env` 加上…」那一段後面加一段：

```markdown
解析時預設會先用 [PyThaiNLP](https://pythainlp.org/) 做機器斷詞，把結果附給 GPT 當參考。想關掉可以在 `.env` 加上 `SEGMENT_HINT=off`（GPT 回來的結果仍然會用機器斷詞檢查）。
```

如果 Task 9 把預設值改成 `off`，這一段改成：

```markdown
解析結果會用 [PyThaiNLP](https://pythainlp.org/) 的機器斷詞檢查。想把機器斷詞的結果也附給 GPT 當參考，可以在 `.env` 加上 `SEGMENT_HINT=on`。
```

「專案結構」的目錄樹裡，`gpt_teacher.py` 那一行換成下面四行，並在 `requirements.txt` 那一行前後補上新檔案：

```
│   ├── gpt_teacher.py       送給 OpenAI：逐句解析、替詞庫查沒看過的字
│   ├── segmenter.py         用 PyThaiNLP 做機器斷詞
│   ├── analysis_check.py    檢查單字有沒有涵蓋整句、有沒有拆開
│   ├── dictionary.py        詞庫的讀寫與合併
```

```
├── scripts/                 對照實驗用的腳本
├── tests/                   後端的測試（pytest）
├── requirements.txt         後端的 Python 套件
├── requirements-dev.txt     開發用的套件（測試）
```

「`data/` 裡的資料」的表格，在 `explanations/{id}.json` 那一列後面加一列，並把那一列的說明改掉：

```markdown
| `explanations/{id}.json` | GPT 逐句解析的快取（整句的拼音、翻譯、每個字在這句的意思） |
| `dictionary.json` | 詞庫：每個單字的拼音、組成、常見意思與用法，所有影片共用 |
```

「抓取一部影片時發生什麼事」整段換成：

```markdown
1. **取得字幕**
   - 本機已經存過這部影片的字幕就直接使用。
   - 否則向 YouTube 要手動上傳的泰文字幕。
   - 影片沒有手動泰文字幕時，改用 ElevenLabs 把聲音轉成文字。
2. **逐句解析**：字幕每 10 句切成一段，同時送 5 段給 OpenAI，取得整句的拼音、翻譯，以及拆成單字後每個字在這句的意思。每完成一段就存進快取。
3. **檢查**：用機器斷詞確認單字涵蓋整句，而且沒有把片語當成一個字。沒通過的句子會單獨重送一次。
4. **查詞**：詞庫裡沒有的字每 40 個一批送給 OpenAI，取得拼音、組成、常見意思與用法，寫進詞庫。看過的字之後每部影片都直接沿用，所以影片越多，這一步越快。
5. **合併存檔**：把逐句解析和詞庫合併，寫入 `data/subtitles/`。

快取以「句子編號加上泰文內容」為準：內容沒變的句子不會重新送出，所以重跑只會處理缺少或改變的部分。

解析的格式有版本號。格式更新後，舊影片在影片庫會顯示為解析未完成，對它按一次「抓取字幕」就會用新格式重跑；重跑之前舊的解析照常顯示。
```

在「後端 API」那一節前面加一節：

````markdown
## 測試

```bash
pip install -r requirements-dev.txt
python -m pytest
```

測試不會連到 OpenAI。
````

「已知限制」的清單最後加兩項：

```markdown
- 單字卡上的拼音來自詞庫，整句的拼音是 GPT 另外產生的，兩邊偶爾會有寫法不同的情況。
- 詞庫以泰文拼法區分單字，同樣拼法但讀音不同的字會共用一筆資料。
```

- [ ] **Step 5: 更新 `README.en.md`**

對應的位置做同樣的修改，內容如下。

Features，把 synced subtitles 那一項換成：

```markdown
- **Synced subtitles**: shows the Thai, romanisation, translation and word breakdown of the current line while the video plays.
- **Word cards**: each line is split into dictionary words. Particles, classifiers, proper nouns and fixed expressions are labelled, compound words list their parts, and every card links to [Forvo](https://forvo.com/) to hear native speakers.
```

Prerequisites，在更換朗讀聲音那一段後面加：

```markdown
By default the backend tokenises each line with [PyThaiNLP](https://pythainlp.org/) and passes the result to GPT as a hint. Add `SEGMENT_HINT=off` to `.env` to turn this off (GPT's output is still checked against the tokeniser).
```

如果 Task 9 把預設值改成 `off`，改用：

```markdown
The analysis is checked against the [PyThaiNLP](https://pythainlp.org/) tokeniser. Add `SEGMENT_HINT=on` to `.env` to also pass the tokeniser output to GPT as a hint.
```

Project structure 的目錄樹：

```
│   ├── gpt_teacher.py       calls OpenAI: per-line analysis and dictionary lookups
│   ├── segmenter.py         word tokenisation with PyThaiNLP
│   ├── analysis_check.py    checks that the words cover the line and are split finely enough
│   ├── dictionary.py        reading, writing and merging the word dictionary
```

```
├── scripts/                 script for comparing segmentation variants
├── tests/                   backend tests (pytest)
├── requirements.txt         backend Python packages
├── requirements-dev.txt     development packages (tests)
```

What is in `data/` 的表格：

```markdown
| `explanations/{id}.json` | Cache of GPT's per-line analysis (romanisation, translation, and what each word means in that line) |
| `dictionary.json` | Word dictionary shared by all videos: romanisation, parts, common meanings and usage |
```

What happens when a video is fetched 整段換成：

```markdown
1. **Get the subtitles**
   - Subtitles already saved locally are used as they are.
   - Otherwise, manually uploaded Thai subtitles are requested from YouTube.
   - If the video has none, ElevenLabs transcribes the audio.
2. **Analyse each line**: subtitles are cut into chunks of 10 lines and 5 chunks are sent to OpenAI at a time. Each line gets its romanisation, translation and a list of words with their meaning in that line. Every finished chunk is saved to the cache.
3. **Check**: the tokeniser verifies that the words cover the whole line and that no phrase was returned as a single word. Lines that fail are resent once, on their own.
4. **Look up words**: words missing from the dictionary are sent to OpenAI 40 at a time to get their romanisation, parts, common meanings and usage. Known words are reused for every later video, so this step gets faster as the library grows.
5. **Merge and save**: the per-line analysis and the dictionary are merged and written to `data/subtitles/`.

The cache is keyed on line number plus Thai text: unchanged lines are not sent again, so a rerun only handles what is missing or changed.

The analysis format is versioned. After a format change, older videos show as incomplete in the library; pressing "Fetch subtitles" on one re-analyses it in the new format, and the old analysis stays visible until then.
```

在 Backend API 那一節前面加：

````markdown
## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests never call OpenAI.
````

Known limitations 最後加：

```markdown
- The romanisation on word cards comes from the dictionary, while the romanisation of the whole line is generated separately by GPT, so the two can occasionally differ.
- The dictionary is keyed on Thai spelling, so words spelled the same but pronounced differently share one entry.
```

「Fetch subtitles」要換成 `README.en.md` 裡實際使用的按鈕名稱：先執行 `grep -n "Fetch" README.en.md` 確認用字，跟著它寫。

- [ ] **Step 6: 最後驗證**

```bash
.venv/bin/python -m pytest -q
cd frontend && npm run lint && npm run build && cd ..
git status --short
```

Expected: 測試全部通過；lint 沒有 error；build 成功；`git status` 只列出這個 task 改的四個檔案（沒有重跑範例的話只有兩個 README）。

電腦上有 Docker 的話再執行 `docker compose build api`，確認 `pythainlp` 在 Python 3.10 的映像檔裡裝得起來。Expected: build 成功。沒有 Docker 就在回報時說明這一項沒有驗證。

- [ ] **Step 7: Commit**

```bash
git add README.md README.en.md data/subtitles/1Sk8kiYfZGg.json data/subtitles/7tMkVWSWePg.json
git commit -m "Regenerate sample subtitles and document the dictionary and Forvo links

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

沒有重跑範例的話，`git add` 只加兩個 README，commit 訊息改成 `Document the dictionary and Forvo links`。
