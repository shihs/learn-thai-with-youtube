# GPT 解析：把字幕分段送給 OpenAI，取得每一句的拼音、翻譯與單字拆解；另外替詞庫查沒看過的字
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

from dotenv import load_dotenv
from openai import AuthenticationError, OpenAI, PermissionDeniedError, RateLimitError

from .analysis_check import check_analysis
from .dictionary import add_entries
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
