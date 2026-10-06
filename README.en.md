[繁體中文](README.md) | **English**

# Learn Thai from YouTube

Paste a Thai YouTube video and the app fetches its subtitles, then asks GPT to produce a romanization (RTGS), a Traditional Chinese translation and a word-by-word breakdown for every line. While the video plays, the page shows all of that for the line being spoken.

The interface and the generated explanations are in Traditional Chinese: the app is built for Chinese speakers learning Thai.

![Player view: romanization, translation and word breakdown for the current line, with a clickable transcript on the right](docs/screenshots/player.jpg)

![Library: every video that already has subtitles](docs/screenshots/library.jpg)

## Features

- **Synced subtitles**: the current line's Thai text, romanization, translation and word breakdown update as the video plays.
- **Word cards**: each line is split into dictionary words. Particles, classifiers, proper nouns and fixed expressions are labeled, compound words list their parts, and every card links to [Forvo](https://forvo.com/) to hear native speakers.
- **Transcript**: every line of the video in a list; click any line to jump to it, or use the previous / replay / next buttons.
- **Read aloud**: press 「唸給我聽」 (read it to me) to hear the current line spoken by an ElevenLabs voice.
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
- `ELEVENLABS_API_KEY`: used in two places. When a video has no manually uploaded Thai subtitles, it transcribes the audio (the key needs the Speech to Text permission). When you press 「唸給我聽」, it generates the speech (the key needs the Text to Speech permission).

To change the voice used for reading aloud, add `ELEVENLABS_VOICE_ID=<voice id>` to `.env`.

By default the backend tokenizes each line with [PyThaiNLP](https://pythainlp.org/) and passes the result to GPT as a hint. Add `SEGMENT_HINT=off` to `.env` to turn this off (GPT's output is still checked against the tokenizer).

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
│   ├── gpt_teacher.py       Calls OpenAI: per-line analysis and dictionary lookups
│   ├── segmenter.py         Word tokenization with PyThaiNLP
│   ├── analysis_check.py    Checks that the words cover the line and are split finely enough
│   ├── dictionary.py        Reads, writes and merges the word dictionary
│   ├── rtgs.py              Checks that dictionary romanization is in RTGS form
│   ├── tts.py               Speaks one subtitle line with ElevenLabs
│   └── storage.py           Where every data file lives, and reading/writing them
├── frontend/                Frontend (React + Vite + Tailwind)
│   ├── src/VideoSubtitleApp.jsx   The whole UI
│   └── Dockerfile
├── data/                    All data (see below)
├── Dockerfile               Backend image
├── docker-compose.yml       Starts backend and frontend together
├── scripts/                 Scripts for comparing segmentation variants and repairing dictionary romanization
├── tests/                   Backend tests (pytest)
├── requirements.txt         Backend Python packages
├── requirements-dev.txt     Development packages (tests)
└── .env                     API keys (create it yourself)
```

### What is in `data/`

Each video's files are named after its YouTube video ID.

| Location | Contents |
|---|---|
| `subtitles/{id}.json` | The finished subtitles the frontend uses: every line with timing and explanation |
| `transcripts/{id}.json` | The raw fetched subtitles, without explanations |
| `explanations/{id}.json` | Cache of GPT's per-line analysis (romanization, translation, and what each word means in that line) |
| `dictionary.json` | Word dictionary shared by all videos: romanization, parts, common meanings and usage |
| `elevenlabs/{id}.json` | The raw ElevenLabs transcription response |
| `tts/{hash}.mp3` | Cache of read-aloud audio; each line is generated once |
| `video_titles.json` | Cache of video titles |

`subtitles/` is the end product. Everything else is intermediate output kept to avoid repeating network calls or paying twice.

This repo ships the finished subtitles for two videos only (`subtitles/1Sk8kiYfZGg.json` and `subtitles/h1r8CxHJnnc.json`) as samples. The rest of the data is not under version control and is generated when you fetch a video.

## What happens when a video is fetched

![Workflow diagram: which external services each backend step calls and which files under data/ it reads and writes](docs/screenshots/workflow.png)

The diagram is labelled in Chinese. Columns from left to right: external services, backend steps, files under `data/`. Orange lines are paid API calls; dashed lines reuse saved files and skip the earlier steps. A longer write-up (in Chinese) is in [`docs/workflow.html`](docs/workflow.html); download it and open it in a browser.

1. **Get the subtitles**
   - Subtitles already saved locally are used as they are.
   - Otherwise, manually uploaded Thai subtitles are requested from YouTube.
   - If the video has none, ElevenLabs transcribes the audio.
2. **Analyze each line**: subtitles are cut into chunks of 10 lines and 5 chunks are sent to OpenAI at a time. Each line gets its romanization, translation and a list of words with their meaning in that line. Every finished chunk is saved to the cache.
3. **Check**: the tokenizer verifies that the words cover the whole line and that no phrase was returned as a single word. Lines that fail are resent once, on their own.
4. **Look up words**: words missing from the dictionary are sent to OpenAI 40 at a time to get their romanization, parts, common meanings and usage. Known words are reused for every later video, so this step gets faster as the library grows.
5. **Merge and save**: the per-line analysis and the dictionary are merged and written to `data/subtitles/`.

The cache is keyed on line number plus Thai text: unchanged lines are not sent again, so a rerun only handles what is missing or changed.

The analysis format is versioned. After a format change, older videos show as incomplete in the library; pressing 「抓取字幕」 on one re-analyzes it in the new format, and the old analysis stays visible until then.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The tests never call OpenAI.

## Backend API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/videos` | List videos that have subtitles (title, line count, explained line count) |
| `GET` | `/subtitles/{video_id}` | Get a video's subtitles and explanations |
| `POST` | `/analyze` | Start a fetch job; body is `{"video_id": "...", "refetch_transcript": false}` |
| `GET` | `/status/{video_id}` | Check a fetch job's progress |
| `GET` | `/tts/{video_id}/{line_id}` | Speak one subtitle line; returns mp3 |

With the backend running, <http://localhost:8000/docs> has interactive API docs.

## Known limitations

- **Fetching subtitles from YouTube sometimes fails** (a `ParseError` or a 500 error). Videos whose subtitles are already stored are unaffected; for a new video, try again later.
- **The romanization is occasionally non-standard.** This is a model accuracy issue.
- **Line breaks in the romanization of multi-line subtitles do not always match the original.** Nothing is missing, but the lines may not pair up one to one.
- **Job progress lives in memory only.** Restarting the backend drops running jobs; pressing 「抓取字幕」 again resumes from the cache.
- **To change fetch speed**, edit `MAX_WORKERS` (chunks sent at once) in `backend/gpt_teacher.py`.
- **Word cards and the full line can romanize a word differently.** Card romanization comes from the dictionary, while the line's romanization is generated separately by GPT.
- **Homographs share one dictionary entry.** The dictionary is keyed on Thai spelling, so words spelled the same but pronounced differently are not kept apart.
