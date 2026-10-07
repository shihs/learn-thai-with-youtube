import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Headphones,
  Info,
  Library,
  Loader2,
  ListVideo,
  Moon,
  Play,
  RotateCcw,
  Search,
  Sparkles,
  Square,
  Sun,
  Volume2,
  X,
} from "lucide-react";

// 後端 API 位址，可在 frontend/.env 用 VITE_API_URL 覆寫
const API_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

const VIDEO_ID_PATTERN = /^[A-Za-z0-9_-]{11}$/;

// 接受影片 ID 或各種 YouTube 網址（watch?v=、youtu.be/、shorts/、embed/、live/），無法辨識時回傳 null
function extractVideoId(input) {
  const value = input.trim();
  if (VIDEO_ID_PATTERN.test(value)) return value;
  try {
    const url = new URL(value.includes("://") ? value : `https://${value}`);
    const host = url.hostname.replace(/^(www|m|music)\./, "");
    let id = null;
    if (host === "youtu.be") {
      id = url.pathname.split("/")[1];
    } else if (host === "youtube.com" || host === "youtube-nocookie.com") {
      id = url.searchParams.get("v") || url.pathname.match(/^\/(?:shorts|embed|live|v)\/([^/?]+)/)?.[1];
    }
    return id && VIDEO_ID_PATTERN.test(id) ? id : null;
  } catch {
    return null;
  }
}

// index.html 的 iframe_api 是非同步載入的，等它準備好再建立播放器
function whenYouTubeReady() {
  return new Promise((resolve) => {
    if (window.YT?.Player) return resolve();
    const timer = setInterval(() => {
      if (window.YT?.Player) {
        clearInterval(timer);
        resolve();
      }
    }, 100);
  });
}

function getInitialDarkMode() {
  let saved = null;
  try {
    saved = localStorage.getItem("theme");
  } catch {
    // 無痕模式等情況讀不到 localStorage，用預設值
  }
  const dark = saved ? saved === "dark" : document.documentElement.classList.contains("dark");
  document.documentElement.classList.toggle("dark", dark);
  return dark;
}

// 朗讀可選的語速，按一下按鈕就換下一個
const SPEECH_RATES = [1, 0.75, 0.5];

function getInitialSpeechRate() {
  try {
    const saved = Number(localStorage.getItem("speechRate"));
    if (SPEECH_RATES.includes(saved)) return saved;
  } catch {
    // 讀不到 localStorage 就用正常語速
  }
  return 1;
}

function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

const thumbnailUrl = (id) => `https://img.youtube.com/vi/${id}/mqdefault.jpg`;

const iconButtonClass =
  "focus-ring inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-slate-600 transition-colors hover:bg-slate-100 disabled:opacity-40 disabled:hover:bg-transparent dark:text-slate-300 dark:hover:bg-slate-800";

// Forvo 的泰語搜尋頁：沒收錄的字會顯示「找不到」和相近的結果，不會是 404
const forvoUrl = (word) => `https://forvo.com/search/${encodeURIComponent(word)}/th/`;
const FORVO_LABEL = "在 Forvo 聽真人發音（另開分頁）";

// 單字類型的標籤；一般單字（word）不顯示
const WORD_TYPE_LABELS = {
  particle: "語氣詞",
  classifier: "量詞",
  name: "專有名詞",
  expression: "固定說法",
};

// 泰國國旗：紅、白、藍、白、紅，比例 1:1:2:1:1
const THAI_FLAG = { red: "#A51931", white: "#F4F5F8", blue: "#2D2A4A" };

// 頂部細條用的橫向版本，同樣的顏色順序與比例
const THAI_FLAG_STRIPES = `linear-gradient(to right, ${THAI_FLAG.red} 0 16.67%, ${THAI_FLAG.white} 16.67% 33.33%, ${THAI_FLAG.blue} 33.33% 66.67%, ${THAI_FLAG.white} 66.67% 83.33%, ${THAI_FLAG.red} 83.33% 100%)`;

function ThaiFlag({ className }) {
  return (
    <svg viewBox="0 0 36 36" preserveAspectRatio="none" aria-hidden="true" className={`overflow-hidden ${className}`}>
      <rect width="36" height="36" fill={THAI_FLAG.red} />
      <rect y="6" width="36" height="24" fill={THAI_FLAG.white} />
      <rect y="12" width="36" height="12" fill={THAI_FLAG.blue} />
    </svg>
  );
}

// 同一句裡重複出現的字只留第一張卡片；意思不一樣的（一字多義）才分開顯示
function uniqueWords(analysis) {
  const seen = new Set();
  return analysis.filter((item) => {
    const key = `${item.word}\n${item.meaning}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

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

// 講者標籤的顏色，依講者第一次出現的順序輪流使用
const SPEAKER_COLORS = [
  "bg-sky-100 text-sky-800 dark:bg-sky-500/20 dark:text-sky-200",
  "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-200",
  "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-200",
  "bg-rose-100 text-rose-800 dark:bg-rose-500/20 dark:text-rose-200",
  "bg-violet-100 text-violet-800 dark:bg-violet-500/20 dark:text-violet-200",
  "bg-teal-100 text-teal-800 dark:bg-teal-500/20 dark:text-teal-200",
];

// 講者編號：{講者 id: 第幾位開口（從 0 開始）}。只有一位講者或沒有講者資料時是空的，不需要標示
function numberSpeakers(subtitleData) {
  const numbers = {};
  for (const line of subtitleData) {
    for (const speaker of line.speakers || []) {
      if (speaker && !(speaker in numbers)) numbers[speaker] = Object.keys(numbers).length;
    }
  }
  return Object.keys(numbers).length > 1 ? numbers : {};
}

// 小元件：一句字幕的文字，有講者時每一行前面標上是誰講的
function SpokenText({ line, speakerNumbers }) {
  return line.text.split("\n").map((text, index) => {
    const number = speakerNumbers[line.speakers?.[index]];
    return (
      <span key={index} className="block">
        {number !== undefined && (
          <span
            className={`mr-2 inline-block whitespace-nowrap rounded px-1.5 py-0.5 align-middle text-xs font-medium leading-none ${
              SPEAKER_COLORS[number % SPEAKER_COLORS.length]
            }`}
          >
            講者 {number + 1}
          </span>
        )}
        {text}
      </span>
    );
  });
}

// 小元件：目前這句字幕與它的解析
function SubtitlePanel({ line, speakerNumbers, hasPrev, hasNext, onPrev, onNext, onReplay, speechState, onSpeak, speechRate, onCycleSpeechRate }) {
  if (!line) {
    return (
      <div className="card flex min-h-40 items-center justify-center p-6 text-sm text-slate-500 dark:text-slate-400">
        播放影片後，這裡會顯示目前這句的拼音、翻譯和單字解析
      </div>
    );
  }
  const explanation = line.explanation;
  return (
    <div className="card p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
        <p className="min-w-0 flex-1 basis-64 whitespace-pre-line text-2xl font-semibold leading-relaxed text-slate-900 dark:text-white">
          <SpokenText line={line} speakerNumbers={speakerNumbers} />
        </p>
        <button
          onClick={onSpeak}
          disabled={speechState === "loading"}
          aria-label={speechState === "playing" ? "停止朗讀" : "AI 唸這句"}
          title={speechState === "playing" ? "停止朗讀" : "AI 唸這句"}
          className="focus-ring flex h-10 shrink-0 items-center gap-1.5 rounded-full bg-indigo-600 px-4 text-sm font-semibold text-white transition-colors hover:bg-indigo-700 disabled:opacity-70"
        >
          {speechState === "loading" ? (
            <Loader2 size={16} className="animate-spin motion-reduce:animate-none" />
          ) : speechState === "playing" ? (
            <Square size={14} fill="currentColor" />
          ) : (
            <Volume2 size={16} />
          )}
          {speechState === "loading" ? "產生中" : speechState === "playing" ? "停止" : "唸給我聽"}
        </button>
        <button
          onClick={onCycleSpeechRate}
          aria-label={`朗讀語速 ${speechRate} 倍，按一下切換`}
          title="朗讀語速，按一下切換"
          className="focus-ring h-10 w-14 shrink-0 rounded-full border border-slate-200 text-sm font-semibold tabular-nums text-slate-700 transition-colors hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          {speechRate}x
        </button>
        <div className="flex shrink-0 items-center rounded-full border border-slate-200 dark:border-slate-700">
          <button onClick={onPrev} disabled={!hasPrev} aria-label="上一句" title="上一句" className={iconButtonClass}>
            <ChevronLeft size={18} />
          </button>
          <button onClick={onReplay} aria-label="重播這句" title="重播這句" className={iconButtonClass}>
            <RotateCcw size={16} />
          </button>
          <button onClick={onNext} disabled={!hasNext} aria-label="下一句" title="下一句" className={iconButtonClass}>
            <ChevronRight size={18} />
          </button>
        </div>
      </div>

      {explanation ? (
        <>
          <p className="mt-2 whitespace-pre-line text-base text-indigo-600 dark:text-indigo-300">{explanation.rtgs}</p>
          <p className="mt-3 whitespace-pre-line text-lg text-slate-700 dark:text-slate-200">
            {explanation.translation}
          </p>

          {explanation.analysis?.length > 0 && (
            <div className="mt-5 border-t border-slate-200 pt-4 dark:border-slate-800">
              <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                單字解析
              </p>
              <ul className="grid gap-3 sm:grid-cols-2">
                {uniqueWords(explanation.analysis).map((item, index) => (
                  <WordCard key={index} item={item} />
                ))}
              </ul>
            </div>
          )}
        </>
      ) : (
        <p className="mt-3 text-sm text-amber-600 dark:text-amber-400">
          這句還沒有解析，按上方的「抓取字幕」可以補上
        </p>
      )}
    </div>
  );
}

// 小元件：完整逐字稿，點任一句跳到該時間
function TranscriptList({ subtitleData, speakerNumbers, currentIndex, onSeek }) {
  const listRef = useRef(null);
  const activeRef = useRef(null);

  // 目前這句保持在清單中間
  useEffect(() => {
    const list = listRef.current;
    const active = activeRef.current;
    if (!list || !active) return;
    list.scrollTo({
      top: active.offsetTop - list.clientHeight / 2 + active.clientHeight / 2,
      // 分頁在背景時平滑捲動不會執行，直接跳到定位
      behavior: prefersReducedMotion() || document.hidden ? "auto" : "smooth",
    });
  }, [currentIndex]);

  return (
    <div ref={listRef} className="relative h-full overflow-y-auto p-2">
      {subtitleData.map((line, index) => {
        const isActive = index === currentIndex;
        return (
          <button
            key={index}
            ref={isActive ? activeRef : null}
            onClick={() => onSeek(line.start)}
            className={`focus-ring block w-full rounded-lg border-l-2 px-3 py-2 text-left text-sm transition-colors ${
              isActive
                ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-500/15"
                : "border-transparent hover:bg-slate-100 dark:hover:bg-slate-800"
            }`}
          >
            <span
              className={`block whitespace-pre-line font-medium ${
                isActive ? "text-indigo-900 dark:text-indigo-100" : "text-slate-800 dark:text-slate-200"
              }`}
            >
              <SpokenText line={line} speakerNumbers={speakerNumbers} />
            </span>
            {line.explanation?.translation && (
              <span className="mt-0.5 block whitespace-pre-line text-slate-500 dark:text-slate-400">
                {line.explanation.translation}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function VideoMeta({ video }) {
  const isComplete = video.explained >= video.lines;
  return isComplete ? (
    <span className="text-xs text-slate-500 dark:text-slate-400">{video.lines} 句</span>
  ) : (
    <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-500/15 dark:text-amber-300">
      解析 {video.explained} / {video.lines}
    </span>
  );
}

// 小元件：影片庫首頁用的大卡片
function VideoCard({ video, onClick }) {
  return (
    <button
      onClick={onClick}
      className="card focus-ring group overflow-hidden text-left transition-shadow hover:shadow-md"
    >
      <span className="relative block aspect-video overflow-hidden bg-slate-200 dark:bg-slate-800">
        <img src={thumbnailUrl(video.id)} alt="" loading="lazy" className="h-full w-full object-cover" />
        <span className="absolute inset-0 flex items-center justify-center bg-black/0 transition-colors group-hover:bg-black/30">
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-white/95 text-indigo-600 opacity-0 transition-opacity group-hover:opacity-100">
            <Play size={20} fill="currentColor" />
          </span>
        </span>
      </span>
      <span className="block p-3">
        <span className="line-clamp-2 text-sm font-medium text-slate-900 dark:text-slate-100">
          {video.title || video.id}
        </span>
        <span className="mt-2 block">
          <VideoMeta video={video} />
        </span>
      </span>
    </button>
  );
}

// 小元件：側邊面板用的精簡列
function VideoRow({ video, isActive, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`focus-ring flex w-full gap-3 rounded-lg p-2 text-left transition-colors ${
        isActive ? "bg-indigo-50 dark:bg-indigo-500/15" : "hover:bg-slate-100 dark:hover:bg-slate-800"
      }`}
    >
      <img
        src={thumbnailUrl(video.id)}
        alt=""
        loading="lazy"
        className="aspect-video w-24 shrink-0 rounded-md bg-slate-200 object-cover dark:bg-slate-800"
      />
      <span className="min-w-0">
        <span className="line-clamp-2 text-sm font-medium text-slate-900 dark:text-slate-100">
          {video.title || video.id}
        </span>
        <span className="mt-1 block">
          <VideoMeta video={video} />
        </span>
      </span>
    </button>
  );
}

function LibraryFilter({ value, onChange }) {
  return (
    <label className="relative block">
      <span className="sr-only">搜尋影片庫</span>
      <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="搜尋影片標題"
        className="focus-ring h-10 w-full rounded-lg border border-slate-200 bg-white pl-9 pr-3 text-sm placeholder:text-slate-400 dark:border-slate-700 dark:bg-slate-900"
      />
    </label>
  );
}

function TabButton({ isActive, onClick, icon, children }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={isActive}
      className={`focus-ring flex h-10 flex-1 items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors ${
        isActive
          ? "bg-white text-indigo-700 shadow-sm dark:bg-slate-700 dark:text-white"
          : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
      }`}
    >
      {icon}
      {children}
    </button>
  );
}

export default function VideoSubtitleApp() {
  const ytplayerRef = useRef(null);
  const playerRef = useRef(null);

  // 輸入框的內容（網址或影片 ID）
  const [inputValue, setInputValue] = useState("");
  // 目前載入的影片
  const [videoId, setVideoId] = useState("");
  const [subtitleData, setSubtitleData] = useState([]);
  // 最近播到的那一句；句與句之間的空檔會停在上一句，方便繼續看解析
  const [currentIndex, setCurrentIndex] = useState(-1);
  const [isDark, setIsDark] = useState(getInitialDarkMode);
  // 後端回報的抓取任務狀態：{ videoId, status, stage, done, total, message }
  // stage 是 dictionary（建立詞庫）時 done / total 是字數，其餘是句數
  const [job, setJob] = useState(null);
  // 後端目前有字幕的影片：[{ id, title, lines, explained }]
  const [videos, setVideos] = useState([]);
  // 畫面上方的提示訊息：{ type: "error" | "info", text }
  const [notice, setNotice] = useState(null);
  const [sideTab, setSideTab] = useState("transcript");
  const [libraryQuery, setLibraryQuery] = useState("");
  // 抓取時是否連字幕本身都重新取得（預設沿用存過的字幕，只補 GPT 解析）
  const [refetchTranscript, setRefetchTranscript] = useState(false);
  // AI 朗讀目前這句的狀態：null（沒在唸）、"loading"（產生語音中）、"playing"
  const [speechState, setSpeechState] = useState(null);
  const audioRef = useRef(null);
  const [speechRate, setSpeechRate] = useState(getInitialSpeechRate);
  // 每次開始或停止朗讀就加一，用來丟掉已經過期的請求
  const speechRequestRef = useRef(0);

  const currentLine = subtitleData[currentIndex] ?? null;
  const currentVideo = videos.find((video) => video.id === videoId);

  const speakerNumbers = useMemo(() => numberSpeakers(subtitleData), [subtitleData]);

  const filteredVideos = useMemo(() => {
    const query = libraryQuery.trim().toLowerCase();
    if (!query) return videos;
    return videos.filter((video) => `${video.title || ""} ${video.id}`.toLowerCase().includes(query));
  }, [videos, libraryQuery]);

  const showError = useCallback((text) => setNotice({ type: "error", text }), []);

  const toggleDarkMode = useCallback(() => {
    const next = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("theme", next ? "dark" : "light");
    } catch {
      // 存不了就只在這次瀏覽生效
    }
    setIsDark(next);
  }, []);

  const refreshVideos = useCallback(() => {
    fetch(`${API_URL}/videos`)
      .then((res) => (res.ok ? res.json() : []))
      .then(setVideos)
      .catch(() => {
        showError(`無法連線到後端（${API_URL}），請確認後端已啟動`);
      });
  }, [showError]);

  useEffect(() => {
    refreshVideos();
  }, [refreshVideos]);

  const destroyPlayer = useCallback(() => {
    if (playerRef.current) {
      try {
        playerRef.current.destroy();
      } catch {
        // 播放器可能已經被移除，忽略
      }
      playerRef.current = null;
    }
  }, []);

  const closeVideo = useCallback(() => {
    destroyPlayer();
    setVideoId("");
    setSubtitleData([]);
    setCurrentIndex(-1);
  }, [destroyPlayer]);

  const loadSubtitles = useCallback(
    (id) => {
      fetch(`${API_URL}/subtitles/${encodeURIComponent(id)}`)
        .then((res) => {
          if (!res.ok) throw new Error(`${res.status}`);
          return res.json();
        })
        .then((data) => {
          // 保留每一句在後端的編號，朗讀時要用
          setSubtitleData(Object.entries(data).map(([id, line]) => ({ id, ...line })));
          setCurrentIndex(-1);
          setVideoId(id);
          setSideTab("transcript");
          setNotice(null);
          window.scrollTo({ top: 0 });
        })
        .catch((err) => {
          closeVideo();
          if (err.message === "404") {
            showError("這部影片還沒有字幕，請按「抓取字幕」");
          } else {
            showError(`無法連線到後端（${API_URL}），請確認後端已啟動`);
          }
        });
    },
    [closeVideo, showError]
  );

  // 把輸入框的內容轉成影片 ID，無法辨識時提示並回傳 null
  const getInputVideoId = useCallback(() => {
    if (!inputValue.trim()) return null;
    const id = extractVideoId(inputValue);
    if (!id) showError("無法辨識，請輸入 YouTube 網址或 11 個字元的影片 ID");
    return id;
  }, [inputValue, showError]);

  const handleLoadSubtitles = useCallback(() => {
    const id = getInputVideoId();
    if (id) loadSubtitles(id);
  }, [getInputVideoId, loadSubtitles]);

  const applyJobStatus = useCallback(
    (id, status) => {
      setJob({ ...status, videoId: id });
      // 完成後自動載入字幕，並更新影片庫
      if (status.status === "done") {
        loadSubtitles(id);
        refreshVideos();
      }
    },
    [loadSubtitles, refreshVideos]
  );

  const handleFetchSubtitles = useCallback(async () => {
    const id = getInputVideoId();
    if (!id) return;
    setNotice(null);
    let response;
    try {
      response = await fetch(`${API_URL}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_id: id, refetch_transcript: refetchTranscript }),
      });
    } catch {
      showError(`無法連線到後端（${API_URL}），請確認後端已啟動`);
      return;
    }
    if (!response.ok) {
      showError("影片 ID 格式不正確，請輸入 11 個字元的 YouTube 影片 ID");
      return;
    }
    applyJobStatus(id, await response.json());
  }, [getInputVideoId, applyJobStatus, showError, refetchTranscript]);

  // 任務進行中時，每 2 秒向後端查詢一次進度
  useEffect(() => {
    if (job?.status !== "running") return;
    const timer = setTimeout(async () => {
      try {
        const res = await fetch(`${API_URL}/status/${encodeURIComponent(job.videoId)}`);
        if (!res.ok) throw new Error(`${res.status}`);
        const status = await res.json();
        if (status.status === "not_found") {
          // 後端重啟後任務狀態會消失
          applyJobStatus(job.videoId, { status: "error", message: "任務已中斷（後端可能重啟了），請再按一次「抓取字幕」" });
        } else {
          applyJobStatus(job.videoId, status);
        }
      } catch {
        // 暫時連不上後端，保留目前狀態，下一輪再查
        setJob({ ...job });
      }
    }, 2000);
    return () => clearTimeout(timer);
  }, [job, applyJobStatus]);

  // 切換影片時重建播放器
  useEffect(() => {
    if (!videoId) return;
    let cancelled = false;
    whenYouTubeReady().then(() => {
      const container = ytplayerRef.current;
      if (cancelled || !container) return;
      destroyPlayer();
      // YT.Player 會把目標元素換成 iframe，所以掛在子元素上，外層容器留給 React 管
      const mount = document.createElement("div");
      container.replaceChildren(mount);
      playerRef.current = new window.YT.Player(mount, {
        videoId,
        width: "100%",
        height: "100%",
      });
    });
    return () => {
      cancelled = true;
    };
  }, [videoId, destroyPlayer]);

  // 追蹤播放器時間，只有換到另一句字幕時才更新畫面
  useEffect(() => {
    const interval = setInterval(() => {
      const player = playerRef.current;
      if (!player || typeof player.getCurrentTime !== "function") return;
      const time = player.getCurrentTime();
      const index = subtitleData.findIndex((item) => time >= item.start && time < item.start + item.duration);
      if (index !== -1) setCurrentIndex(index);
    }, 300);
    return () => clearInterval(interval);
  }, [subtitleData]);

  const seekTo = useCallback((seconds) => {
    const player = playerRef.current;
    if (!player || typeof player.seekTo !== "function") return;
    player.seekTo(seconds, true);
    player.playVideo();
  }, []);

  const stopSpeech = useCallback(() => {
    speechRequestRef.current += 1;
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    setSpeechState(null);
  }, []);

  // 換句或換影片時停止朗讀
  useEffect(() => stopSpeech, [currentIndex, videoId, stopSpeech]);

  const speakCurrentLine = useCallback(() => {
    if (speechState === "playing") {
      stopSpeech();
      return;
    }
    if (!currentLine || !videoId) return;
    stopSpeech();
    const requestId = speechRequestRef.current;
    // 影片先暫停，避免和朗讀的聲音疊在一起
    playerRef.current?.pauseVideo?.();

    // play() 要在點擊的當下呼叫，瀏覽器才不會把它當成自動播放擋掉；
    // 語音由瀏覽器自己向後端載入，第一次產生時會等幾秒
    const url = `${API_URL}/tts/${encodeURIComponent(videoId)}/${encodeURIComponent(currentLine.id)}`;
    const audio = new Audio(url);
    // 放慢時維持原本的音高，只改速度
    audio.preservesPitch = true;
    audio.defaultPlaybackRate = speechRate;
    audio.playbackRate = speechRate;
    audioRef.current = audio;
    setSpeechState("loading");
    audio.onplaying = () => {
      if (audioRef.current === audio) setSpeechState("playing");
    };
    audio.onended = () => {
      if (audioRef.current === audio) {
        audioRef.current = null;
        setSpeechState(null);
      }
    };
    audio.play().catch(async (err) => {
      // 期間已經換句或按了停止，就不用回報
      if (requestId !== speechRequestRef.current) return;
      audioRef.current = null;
      setSpeechState(null);
      // 音訊元素拿不到後端的錯誤內容，再問一次後端原因
      let message = err.message;
      try {
        const res = await fetch(url);
        if (!res.ok) message = (await res.json()).detail || `${res.status}`;
      } catch {
        message = `無法連線到後端（${API_URL}）`;
      }
      showError(`朗讀失敗：${message}`);
    });
  }, [speechState, currentLine, videoId, stopSpeech, showError, speechRate]);

  const cycleSpeechRate = useCallback(() => {
    const next = SPEECH_RATES[(SPEECH_RATES.indexOf(speechRate) + 1) % SPEECH_RATES.length];
    setSpeechRate(next);
    // 正在唸的話立刻套用
    if (audioRef.current) audioRef.current.playbackRate = next;
    try {
      localStorage.setItem("speechRate", String(next));
    } catch {
      // 存不了就只在這次瀏覽生效
    }
  }, [speechRate]);

  const seekToIndex = useCallback(
    (index) => {
      const line = subtitleData[index];
      if (!line) return;
      setCurrentIndex(index);
      seekTo(line.start);
    },
    [subtitleData, seekTo]
  );

  const openVideo = useCallback(
    (video) => {
      setInputValue(video.id);
      loadSubtitles(video.id);
    },
    [loadSubtitles]
  );

  const jobPercent = job?.total > 0 ? Math.round((job.done / job.total) * 100) : 0;

  return (
    <div className="min-h-screen">
      {/* 頂部列：標題、網址輸入、深色模式 */}
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/85 backdrop-blur dark:border-slate-800 dark:bg-slate-950/85">
        <div aria-hidden="true" className="h-1" style={{ background: THAI_FLAG_STRIPES }}></div>
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-4 gap-y-3 px-4 py-3 sm:px-6">
          <button
            onClick={closeVideo}
            title="回到影片庫"
            className="focus-ring flex items-center gap-2.5 rounded-lg"
          >
            <ThaiFlag className="h-9 w-9 rounded-xl shadow-sm ring-1 ring-black/10 dark:ring-white/15" />
            <span className="text-lg font-bold tracking-tight text-slate-900 dark:text-white">看 YouTube 學泰文</span>
          </button>

          <form
            className="order-last flex w-full flex-wrap gap-2 md:order-none md:w-auto md:flex-1 lg:flex-nowrap"
            onSubmit={(e) => {
              e.preventDefault();
              handleLoadSubtitles();
            }}
          >
            <label className="relative min-w-0 flex-1 basis-full sm:basis-0">
              <span className="sr-only">YouTube 網址或影片 ID</span>
              <input
                type="text"
                placeholder="貼上 YouTube 網址或影片 ID"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                className="focus-ring h-11 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 text-sm placeholder:text-slate-400 dark:border-slate-700 dark:bg-slate-900"
              />
            </label>
            <button
              type="submit"
              className="focus-ring h-11 shrink-0 rounded-xl bg-indigo-600 px-4 text-sm font-semibold text-white transition-colors hover:bg-indigo-700"
            >
              載入
            </button>
            <button
              type="button"
              role="switch"
              aria-checked={refetchTranscript}
              onClick={() => setRefetchTranscript((prev) => !prev)}
              title={
                refetchTranscript
                  ? "抓取時會重新向 YouTube 取得字幕，再重跑解析"
                  : "抓取時沿用存過的字幕，只補上缺少的解析"
              }
              className={`focus-ring flex h-11 shrink-0 items-center gap-2 rounded-xl border px-3 text-sm font-medium transition-colors ${
                refetchTranscript
                  ? "border-emerald-600 bg-emerald-50 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-200"
                  : "border-slate-200 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              }`}
            >
              <span
                className={`relative h-5 w-9 rounded-full transition-colors ${
                  refetchTranscript ? "bg-emerald-600" : "bg-slate-300 dark:bg-slate-600"
                }`}
              >
                <span
                  className={`absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
                    refetchTranscript ? "translate-x-4" : ""
                  }`}
                ></span>
              </span>
              重抓字幕
            </button>
            <button
              type="button"
              onClick={handleFetchSubtitles}
              disabled={job?.status === "running"}
              className="focus-ring flex h-11 shrink-0 items-center gap-1.5 rounded-xl bg-emerald-600 px-4 text-sm font-semibold text-white transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Sparkles size={16} />
              抓取字幕
            </button>
          </form>

          <button
            onClick={toggleDarkMode}
            aria-label={isDark ? "切換成淺色模式" : "切換成深色模式"}
            title={isDark ? "淺色模式" : "深色模式"}
            className={`${iconButtonClass} ml-auto md:ml-0`}
          >
            {isDark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-7xl space-y-4 px-4 py-6 sm:px-6">
        {notice && (
          <div
            role="alert"
            className={`flex items-start gap-3 rounded-xl border px-4 py-3 text-sm ${
              notice.type === "error"
                ? "border-red-200 bg-red-50 text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200"
                : "border-indigo-200 bg-indigo-50 text-indigo-800 dark:border-indigo-500/30 dark:bg-indigo-500/10 dark:text-indigo-200"
            }`}
          >
            <AlertCircle size={18} className="mt-0.5 shrink-0" />
            <p className="flex-1">{notice.text}</p>
            <button onClick={() => setNotice(null)} aria-label="關閉提示" className="focus-ring shrink-0 rounded-md">
              <X size={18} />
            </button>
          </div>
        )}

        {job?.status === "running" && (
          <div className="card px-4 py-3" role="status">
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="font-medium text-slate-800 dark:text-slate-100">
                {job.message}，請稍候…
              </span>
              {job.total > 0 && (
                <span className="tabular-nums text-slate-500 dark:text-slate-400">
                  {job.done} / {job.total} {job.stage === "dictionary" ? "字" : "句"}
                </span>
              )}
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
              <div
                className={`h-full rounded-full bg-indigo-600 transition-all duration-500 ${
                  job.total > 0 ? "" : "w-1/4 animate-pulse motion-reduce:animate-none"
                }`}
                style={job.total > 0 ? { width: `${jobPercent}%` } : undefined}
              ></div>
            </div>
          </div>
        )}

        {job?.status === "error" && (
          <div
            role="alert"
            className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200"
          >
            <AlertCircle size={18} className="mt-0.5 shrink-0" />
            <p>抓取失敗：{job.message}</p>
          </div>
        )}

        {job?.status === "done" && job.message && (
          <div className="flex items-start gap-3 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-800 dark:border-indigo-500/30 dark:bg-indigo-500/10 dark:text-indigo-200">
            <Info size={18} className="mt-0.5 shrink-0" />
            <p>{job.message}</p>
          </div>
        )}

        {videoId ? (
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
            {/* 影片與目前這句 */}
            <div className="min-w-0 space-y-4">
              <div
                ref={ytplayerRef}
                className="aspect-video w-full overflow-hidden rounded-2xl bg-black shadow-lg"
              ></div>
              {currentVideo?.title && (
                <h2 className="text-lg font-semibold text-slate-900 dark:text-white">{currentVideo.title}</h2>
              )}
              <SubtitlePanel
                speakerNumbers={speakerNumbers}
                line={currentLine}
                hasPrev={currentIndex > 0}
                hasNext={currentIndex < subtitleData.length - 1}
                onPrev={() => seekToIndex(currentIndex - 1)}
                onNext={() => seekToIndex(currentIndex + 1)}
                onReplay={() => seekToIndex(currentIndex)}
                speechState={speechState}
                onSpeak={speakCurrentLine}
                speechRate={speechRate}
                onCycleSpeechRate={cycleSpeechRate}
              />
            </div>

            {/* 側邊面板：固定高度，內容在面板裡捲動 */}
            <aside className="card flex h-[32rem] flex-col overflow-hidden lg:sticky lg:top-24 lg:h-[calc(100vh-7.5rem)]">
              <div className="flex gap-1 border-b border-slate-200 bg-slate-100 p-1 dark:border-slate-800 dark:bg-slate-800/60">
                <TabButton
                  isActive={sideTab === "transcript"}
                  onClick={() => setSideTab("transcript")}
                  icon={<ListVideo size={16} />}
                >
                  逐字稿
                </TabButton>
                <TabButton
                  isActive={sideTab === "library"}
                  onClick={() => setSideTab("library")}
                  icon={<Library size={16} />}
                >
                  影片庫（{videos.length}）
                </TabButton>
              </div>

              {sideTab === "transcript" ? (
                <div className="min-h-0 flex-1">
                  <TranscriptList subtitleData={subtitleData} speakerNumbers={speakerNumbers} currentIndex={currentIndex} onSeek={seekTo} />
                </div>
              ) : (
                <>
                  <div className="border-b border-slate-200 p-2 dark:border-slate-800">
                    <LibraryFilter value={libraryQuery} onChange={setLibraryQuery} />
                  </div>
                  <div className="min-h-0 flex-1 space-y-1 overflow-y-auto p-2">
                    {filteredVideos.map((video) => (
                      <VideoRow
                        key={video.id}
                        video={video}
                        isActive={video.id === videoId}
                        onClick={() => openVideo(video)}
                      />
                    ))}
                    {filteredVideos.length === 0 && (
                      <p className="p-4 text-center text-sm text-slate-500 dark:text-slate-400">找不到符合的影片</p>
                    )}
                  </div>
                </>
              )}
            </aside>
          </div>
        ) : (
          /* 影片庫首頁 */
          <section>
            <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold text-slate-900 dark:text-white">影片庫</h2>
                <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                  {videos.length} 部影片已有字幕。想加新的，在上方貼上網址後按「抓取字幕」。
                </p>
              </div>
              {videos.length > 0 && (
                <div className="w-full sm:w-72">
                  <LibraryFilter value={libraryQuery} onChange={setLibraryQuery} />
                </div>
              )}
            </div>

            {filteredVideos.length > 0 ? (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {filteredVideos.map((video) => (
                  <VideoCard key={video.id} video={video} onClick={() => openVideo(video)} />
                ))}
              </div>
            ) : (
              <div className="card flex flex-col items-center gap-2 px-6 py-16 text-center">
                <Library size={32} className="text-slate-400" />
                <p className="font-medium text-slate-800 dark:text-slate-100">
                  {videos.length === 0 ? "影片庫還是空的" : "找不到符合的影片"}
                </p>
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  {videos.length === 0 ? "在上方貼上 YouTube 網址，按「抓取字幕」開始" : "換個關鍵字試試"}
                </p>
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
