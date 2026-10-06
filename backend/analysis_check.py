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
