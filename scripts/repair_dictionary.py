# 修復詞庫：把拼音不符合 RTGS 格式的字重新查一次，再把詞庫重新合併進已經解析過的字幕檔。
# 重查會用到 OpenAI；重新合併不會。
#
#   python scripts/repair_dictionary.py            只列出有問題的字，不做任何更動
#   python scripts/repair_dictionary.py --apply    重查並更新 data/dictionary.json 與 data/subtitles/
import argparse
import glob
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
os.chdir(REPO_ROOT)

from backend import storage  # noqa: E402
from backend.dictionary import add_entries, load_dictionary, merge_explanation  # noqa: E402
from backend.gpt_teacher import entry_problems, lookup_missing_words  # noqa: E402


def example_sentences(words):
    """從逐句解析的快取裡，找每個字第一次出現的那一句；找不到就用字本身"""
    examples = {}
    for file_name in sorted(glob.glob(f"{storage.DATA_DIR}/explanations/*.json")):
        for explanation in (storage.load_json_file(file_name) or {}).values():
            for item in explanation.get("analysis", []):
                if item["word"] in words and item["word"] not in examples:
                    examples[item["word"]] = explanation["thai"]
    return {word: examples.get(word, word) for word in words}


def remerge_subtitles(dictionary):
    """把目前的詞庫重新合併進新格式的字幕檔，回傳更新的檔案數"""
    updated = 0
    for file_name in sorted(glob.glob(f"{storage.SUBTITLE_DIR}/*.json")):
        subtitles = storage.load_json_file(file_name)
        if not isinstance(subtitles, dict):
            continue
        changed = False
        for line in subtitles.values():
            explanation = line.get("explanation")
            if not isinstance(explanation, dict) or explanation.get("v") != storage.ANALYSIS_VERSION:
                continue
            merged = merge_explanation({key: value for key, value in explanation.items() if key != "partial"}, dictionary)
            if merged != explanation:
                line["explanation"] = merged
                changed = True
        if changed:
            storage.save_json_file(file_name, subtitles)
            updated += 1
    return updated


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="實際重查並寫入；沒加的話只列出有問題的字")
    args = parser.parse_args()

    dictionary = load_dictionary()
    bad = {word: entry for word, entry in dictionary.items() if entry_problems(word, entry)}
    print(f"詞庫共 {len(dictionary)} 個字，拼音格式有問題的 {len(bad)} 個")
    for word, entry in list(bad.items())[:15]:
        print(f"  {word}  {entry['rtgs']}")
    if not args.apply or not bad:
        return

    # 先拿掉有問題的字再重查；沒查到的把舊資料放回去，不會比原本少
    storage.save_json_file(
        storage.dictionary_file(), {word: entry for word, entry in dictionary.items() if word not in bad}
    )
    try:
        lookup_missing_words(example_sentences(bad))
    finally:
        dictionary = add_entries(bad)

    still_bad = [word for word, entry in dictionary.items() if entry_problems(word, entry)]
    print(f"重查後仍有問題的 {len(still_bad)} 個：{still_bad[:15]}")
    print(f"重新合併了 {remerge_subtitles(dictionary)} 個字幕檔")


if __name__ == "__main__":
    main()
