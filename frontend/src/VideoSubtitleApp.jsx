import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Info,
  Library,
  ListVideo,
  Moon,
  Play,
  RotateCcw,
  Search,
  Sparkles,
  Sun,
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

function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

const thumbnailUrl = (id) => `https://img.youtube.com/vi/${id}/mqdefault.jpg`;

const iconButtonClass =
  "focus-ring inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-slate-600 transition-colors hover:bg-slate-100 disabled:opacity-40 disabled:hover:bg-transparent dark:text-slate-300 dark:hover:bg-slate-800";

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

// 小元件：目前這句字幕與它的解析
function SubtitlePanel({ line, hasPrev, hasNext, onPrev, onNext, onReplay }) {
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
      <div className="flex items-start justify-between gap-4">
        <p className="whitespace-pre-line text-2xl font-semibold leading-relaxed text-slate-900 dark:text-white">
          {line.text}
        </p>
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
function TranscriptList({ subtitleData, currentIndex, onSeek }) {
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
              {line.text}
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
  const [job, setJob] = useState(null);
  // 後端目前有字幕的影片：[{ id, title, lines, explained }]
  const [videos, setVideos] = useState([]);
  // 畫面上方的提示訊息：{ type: "error" | "info", text }
  const [notice, setNotice] = useState(null);
  const [sideTab, setSideTab] = useState("transcript");
  const [libraryQuery, setLibraryQuery] = useState("");
  // 抓取時是否連字幕本身都重新取得（預設沿用存過的字幕，只補 GPT 解析）
  const [refetchTranscript, setRefetchTranscript] = useState(false);

  const currentLine = subtitleData[currentIndex] ?? null;
  const currentVideo = videos.find((video) => video.id === videoId);

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
          setSubtitleData(Object.values(data));
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
                  {job.done} / {job.total} 句
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
                line={currentLine}
                hasPrev={currentIndex > 0}
                hasNext={currentIndex < subtitleData.length - 1}
                onPrev={() => seekToIndex(currentIndex - 1)}
                onNext={() => seekToIndex(currentIndex + 1)}
                onReplay={() => seekToIndex(currentIndex)}
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
                  <TranscriptList subtitleData={subtitleData} currentIndex={currentIndex} onSeek={seekTo} />
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
