# GPT 解析：把字幕分段送給 OpenAI，取得每一句的拼音、翻譯與單字解析
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

from dotenv import load_dotenv
from openai import AuthenticationError, OpenAI, PermissionDeniedError, RateLimitError

load_dotenv()


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
EXPLANATION_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "rtgs": {"type": "string", "description": "整句的皇家轉寫系統拼音（RTGS），單字之間空格"},
        "translation": {"type": "string", "description": "整句的繁體中文翻譯"},
        "analysis": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "word": {"type": "string", "description": "泰文單字或片語"},
                    "rtgs": {"type": "string", "description": "該單字的 RTGS 拼音"},
                    "meaning": {"type": "string", "description": "該單字的繁體中文意思"},
                    "more": {"type": "string", "description": "用法或文法的補充說明"},
                },
                "required": ["word", "rtgs", "meaning", "more"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["rtgs", "translation", "analysis"],
    "additionalProperties": False,
}


@lru_cache(maxsize=None)
def explanation_schema(count):
    keys = [f"item_{n}" for n in range(1, count + 1)]
    return {
        "name": f"thai_explanations_{count}",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {key: {"$ref": "#/$defs/explanation"} for key in keys},
            "required": keys,
            "additionalProperties": False,
            "$defs": {"explanation": EXPLANATION_ITEM_SCHEMA},
        },
    }


# 同時送給 GPT 的段數上限
MAX_WORKERS = 5


def is_fatal_error(e):
    """金鑰無效、沒有權限、額度用完：重試也沒用，應該中止整個任務。一般的速率限制不算。"""
    if isinstance(e, (AuthenticationError, PermissionDeniedError)):
        return True
    if isinstance(e, RateLimitError):
        reasons = (getattr(e, "type", None), getattr(e, "code", None))
        return "insufficient_quota" in reasons or "credit_balance_exhausted" in reasons
    return False


# 分析函式：送給 GPT 逐段分析，回傳 {id: 解析}
def gpt_teacher(client, items):
    # 送出時用 item_1、item_2... 當 key，回來後再對回各句的 id
    keyed_items = {f"item_{n}": item for n, item in enumerate(items, start=1)}
    thai_by_key = {key: item["thai"] for key, item in keyed_items.items()}

    prompt = f"""
        下面是一個 JSON 物件，每個 key（item_1、item_2...）對應一句泰文字幕。
        幫我分析每一句，並解析和說明用法：整句的拼音（RTGS）、繁體中文翻譯、逐字的文法解析（附上單字的拼音），拼音的每個單字中間要空格。

        規則：
        - 每個 key 都要回傳一筆結果，放在相同的 key 底下。
        - 逐句分析，不要合併或拆開句子，也不要省略任何一句。
        - 如果泰文裡面有換行，rtgs 和 translation 也要在對應的位置換行。

        這是要分析的泰文：
        {json.dumps(thai_by_key, ensure_ascii=False)}
        """

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "你是泰語老師，要以台灣繁體中文的角度進行語言教學。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_schema", "json_schema": explanation_schema(len(items))},
        )
        results = json.loads(response.choices[0].message.content)
    except Exception as e:
        if is_fatal_error(e):
            raise
        # 單一段失敗（網路、速率限制、回應被截斷）不影響其他段，缺的 id 會在 analyze_chunk 重試
        print(f"⚠️ GPT 分析失敗：{e}")
        return {}

    return {
        item["id"]: {"thai": item["thai"], **results[key]}
        for key, item in keyed_items.items()
        if key in results
    }


def analyze_chunk(client, chunk):
    result = gpt_teacher(client, chunk)

    # 沒有回傳的 id 只重試一次
    missing = [item for item in chunk if item["id"] not in result]
    if missing:
        print(f"⚠️ 有 {len(missing)} 句沒有解析，重試中...")
        result.update(gpt_teacher(client, missing))

    return result


# 主流程：自動分段、並行送出並彙整，回傳 {id: 解析}
# cached：之前已經分析過的 {id: 解析}，泰文內容沒變的句子不會重送
# on_progress(目前的結果, 總句數)：每完成一段呼叫一次
def analyze_long_text(transcript_with_time, max_lines=10, cached=None, on_progress=None):
    lines = {line_id: snippet["text"].strip() for line_id, snippet in transcript_with_time.items()}
    total = sum(1 for text in lines.values() if text)

    all_results = {
        line_id: explanation
        for line_id, explanation in (cached or {}).items()
        if lines.get(line_id) and explanation.get("thai") == lines[line_id]
    }
    todo = {line_id: snippet for line_id, snippet in transcript_with_time.items() if line_id not in all_results}
    chunks = split_transcript(todo, max_lines=max_lines)
    print(f"⏳ 共 {total} 句，快取已有 {len(all_results)} 句，分成 {len(chunks)} 段送出分析...")
    if on_progress:
        on_progress(all_results, total)

    if chunks:
        # 速率限制交給 client 自動退避重試
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"), max_retries=5)
        executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        try:
            futures = [executor.submit(analyze_chunk, client, chunk) for chunk in chunks]
            for future in as_completed(futures):
                all_results.update(future.result())
                if on_progress:
                    on_progress(all_results, total)
        finally:
            # 遇到無法重試的錯誤時，還沒開始的段不要再送
            executor.shutdown(wait=False, cancel_futures=True)

    if len(all_results) < total:
        print(f"⚠️ 共有 {total - len(all_results)} 句沒有解析")
    return all_results
