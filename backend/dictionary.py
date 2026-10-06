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
