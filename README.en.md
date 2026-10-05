[繁體中文](README.md) | **English**

# Learn Thai from YouTube

Paste a Thai YouTube video and the app fetches its subtitles, then asks GPT to produce a romanization (RTGS), a Traditional Chinese translation and a word-by-word breakdown for every line. While the video plays, the page shows all of that for the line being spoken.

The interface and the generated explanations are in Traditional Chinese: the app is built for Chinese speakers learning Thai.

![Player view: romanization, translation and word breakdown for the current line, with a clickable transcript on the right](docs/screenshots/player.jpg)

![Library: every video that already has subtitles](docs/screenshots/library.jpg)

## Features

- **Synced subtitles**: the current line's Thai text, romanization, translation and word breakdown update as the video plays.
- **Transcript**: every line of the video in a list; click any line to jump to it, or use the previous / replay / next buttons.
- **Library**: all videos that already have subtitles, searchable by title, with a badge on videos whose explanations are incomplete.
- **Fetch subtitles**: paste a YouTube URL or video ID to add a new video, with a progress bar while it runs.
- **Dark mode**.

## Prerequisites

Create a `.env` file in the project root with two API keys:

```
OPENAI_API_KEY=your OpenAI key
ELEVENLABS_API_KEY=your ElevenLabs key
```

- `OPENAI_API_KEY`: used to generate the explanations (model: `gpt-4.1-mini`). The account needs credits.
- `ELEVENLABS_API_KEY`: only used when a video has no manually uploaded Thai subtitles, to transcribe the audio.

Watching videos that have already been processed needs neither key.

## Running it

### Option 1: Docker (just run it)

Install and start Docker Desktop first.

```bash
docker compose up --build
```

- Frontend: <http://localhost:5173>
- Backend: <http://localhost:8000>

If those ports are taken:

```bash
API_PORT=8001 WEB_PORT=5174 docker compose up --build
```

The Docker frontend is a static production build, so code changes only show up after re-running the command above.

### Option 2: Local development (live reload)

Requires Python 3.10 and Node.js 22, and two terminals.

**Backend** (run from the project root, not from inside `backend/`):

```bash
pip install -r requirements.txt
uvicorn backend.api_server:app --reload
```

**Frontend**:

```bash
cd frontend
npm install
npm run dev
```

Then open <http://localhost:5173>. Both must be running: without the backend the frontend cannot even load the library.

If the backend is not at `http://127.0.0.1:8000`, set `VITE_API_URL=<backend URL>` in `frontend/.env`.

## Usage

The buttons are labelled in Chinese; the labels are given below.

1. **Watch an existing video**: click any video in the library.
2. **Add a new video**: paste a YouTube URL or video ID at the top and press 「抓取字幕」 (fetch subtitles). It loads automatically when finished.
3. **Fill in missing explanations**: for a video marked like 「解析 19 / 280」 (19 of 280 lines explained), load it and press 「抓取字幕」 again. Only the lines without an explanation are processed.
4. **The 「重抓字幕」 (refetch) switch**: off by default, so fetching reuses the stored subtitles. Turn it on to fetch the subtitles from YouTube again before generating explanations.

A video of about 500 lines takes roughly 5 minutes. If a run fails partway (for example when credits run out), finished lines are kept and pressing the button again resumes where it stopped.

## Project structure

```
.
├── backend/                 Backend (FastAPI)
│   ├── api_server.py        Entry point, routes only
│   ├── jobs.py              The fetch job pipeline and its progress
│   ├── youtube.py           Fetches subtitles and video titles from YouTube
│   ├── elevenlabs_api.py    ElevenLabs speech-to-text and SRT parsing
│   ├── gpt_teacher.py       Sends subtitles to OpenAI in chunks for explanations
│   └── storage.py           Where every data file lives, and reading/writing them
├── frontend/                Frontend (React + Vite + Tailwind)
│   ├── src/VideoSubtitleApp.jsx   The whole UI
│   └── Dockerfile
├── data/                    All data (see below)
├── Dockerfile               Backend image
├── docker-compose.yml       Starts backend and frontend together
├── requirements.txt         Backend Python packages
└── .env                     API keys (create it yourself)
```

### What is in `data/`

Each video's files are named after its YouTube video ID.

| Location | Contents |
|---|---|
| `subtitles/{id}.json` | The finished subtitles the frontend uses: every line with timing and explanation |
| `transcripts/{id}.json` | The raw fetched subtitles, without explanations |
| `explanations/{id}.json` | Cache of GPT's per-line explanations |
| `elevenlabs/{id}.json` | The raw ElevenLabs transcription response |
| `video_titles.json` | Cache of video titles |

`subtitles/` is the end product. Everything else is intermediate output kept to avoid repeating network calls or paying twice.

This repo ships the finished subtitles for two short videos only (`subtitles/1Sk8kiYfZGg.json` and `subtitles/7tMkVWSWePg.json`) as samples. The rest of the data is not under version control and is generated when you fetch a video.

## What happens when a video is fetched

1. **Get the subtitles**
   - If subtitles for this video are already stored locally, use them.
   - Otherwise ask YouTube for manually uploaded Thai subtitles.
   - If the video has none, transcribe the audio with ElevenLabs instead.
2. **Generate explanations**: the subtitles are split into chunks of 10 lines, and 5 chunks are sent to OpenAI at a time. Each finished chunk is written to the cache.
3. **Merge and save**: each explanation is attached to its line and the result is written to `data/subtitles/`.

The cache is keyed on the line number plus the Thai text. Lines whose text has not changed are not sent again, so a re-run only handles what is missing or different.

## Backend API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/videos` | List videos that have subtitles (title, line count, explained line count) |
| `GET` | `/subtitles/{video_id}` | Get a video's subtitles and explanations |
| `POST` | `/analyze` | Start a fetch job; body is `{"video_id": "...", "refetch_transcript": false}` |
| `GET` | `/status/{video_id}` | Check a fetch job's progress |

With the backend running, <http://localhost:8000/docs> has interactive API docs.

## Known limitations

- **Fetching subtitles from YouTube sometimes fails** (a `ParseError` or a 500 error). Videos whose subtitles are already stored are unaffected; for a new video, try again later.
- **The romanization is occasionally non-standard.** This is a model accuracy issue.
- **Line breaks in the romanization of multi-line subtitles do not always match the original.** Nothing is missing, but the lines may not pair up one to one.
- **Job progress lives in memory only.** Restarting the backend drops running jobs; pressing 「抓取字幕」 again resumes from the cache.
- **To change fetch speed**, edit `MAX_WORKERS` (chunks sent at once) in `backend/gpt_teacher.py`.
