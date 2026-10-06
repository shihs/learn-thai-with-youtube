# RTGS 拼音的格式檢查：詞庫的拼音每部影片都會沿用，不能混進帶聲調符號或別套系統的寫法
import re
import unicodedata

THAI_LETTER = re.compile(r"[฀-๿]")
LETTERS_AND_SPACES = re.compile(r"^[A-Za-z0-9 ]+$")
# RTGS 不標母音長短（aa、ii…），也沒有 bp、dt、j 這些其他拼音系統的子音寫法
NOT_RTGS = re.compile(r"aa|ee|ii|oo|uu|bp|dt|j", re.IGNORECASE)


def rtgs_problems(word, rtgs):
    """回傳拼音不符合 RTGS 格式的原因，空清單代表通過。不含泰文字母的字（外文、品牌）不檢查"""
    if not THAI_LETTER.search(word):
        return []
    if not rtgs.strip():
        return ["沒有拼音"]
    problems = []
    if not LETTERS_AND_SPACES.match(rtgs):
        problems.append("有聲調符號或連字號")
    if NOT_RTGS.search(rtgs):
        problems.append("不是 RTGS 的寫法")
    return problems


def plain_rtgs(rtgs):
    """去掉聲調符號，連字號換成空格"""
    text = unicodedata.normalize("NFD", rtgs)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[-‐-―]", " ", text).split())
