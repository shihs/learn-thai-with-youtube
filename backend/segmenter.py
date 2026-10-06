# 斷詞：用 pythainlp 把泰文切成詞。切法給 GPT 當提示，也用來檢查 GPT 拆得夠不夠細
from pythainlp.tokenize import word_tokenize


def tokenize(text):
    """泰文斷詞（查字典做最長匹配），去掉純空白的 token"""
    return [token for token in word_tokenize(text, engine="newmm") if token.strip()]
