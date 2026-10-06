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
