# 🎙️ EVE — Efficient Voice Extraction

Automatically generates replay-friendly versions of radio shows by removing **all standalone music segments**, regardless of copyright status, while preserving speech and DJ talk — including speech with background music.
Designed to support compliance with replay service policies and mitigate copyright risks.

---

## 🔧 Features

* 🎛️ **Standalone music removal**
  - Removes all music-only sections from radio broadcast audio files.

* 🗣️ **Speech preservation**
  - Keeps DJ talk, narration, interviews, and announcements intact.

* 🎵 **Speech with background music**
  - Background music under speech is **not** removed — treated as part of the speech content.

* ⚡ **Automatic processing**
  - Fully automated pipeline using audio classification and voice activity detection.

---

## 🧠 Technologies

* **[YAMNet](https://github.com/tensorflow/models/tree/master/research/audioset/yamnet)** (by Google): audio classification model for detecting music vs. speech
* **[Silero-VAD](https://github.com/snakers4/silero-vad?tab=readme-ov-file)**: fast and lightweight voice activity detection model

---

## 🧭 Use Cases

* Creating **speech-only replays** of music radio programs
* Preparing **podcast versions** of live radio with music removed
* Automatically editing archives for **legal compliance**
* Speech analysis or summarization pre-processing

---

## 🚧 Why music is removed?

In many jurisdictions (e.g., Korea), live radio broadcasts may play copyrighted music under blanket licenses.
However, **on-demand replay services** require separate music permissions.
To avoid copyright issues, this tool removes **all music segments**, even if the status is unclear.

> 🔍 This tool does not make legal judgments. It simply removes music to reduce copyright risk.

---

## 🚀 Getting Started

### <span style="color:orange">**Prerequisites**</span>

* Python 3.10
* FFmpeg installed and available in PATH, OR:
  * <span style="color:orange">**project-root\bin\ffmpeg.exe, ffprobe.exe MUST be ADDED**</span>
* [VC++ runtime](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170) installed
  * [download](https://aka.ms/vs/17/release/vc_redist.x64.exe) installer
  * to <span style="color:orange">**project-root\vendor\etc**</span> and make sure the name of the installer is <span style="color:orange">**VC_redist.x64.exe**</span>.
  * then \scripts\install.ps1 install it IF VC++ redist has NOT been installed

### Installation

* download libraries
```powershell
python -m pip download -r requirements.txt -d vendor\wheelhouse
```
* install on .venv
```powershell
Remove-Item .venv -Recurse -Force -ErrorAction SilentlyContinue
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

### Run API server (development)

```powershell
.\.venv\Scripts\python.exe -m uvicorn eve.api.main:app --host 127.0.0.1 --port 8001
```

Health check: `http://127.0.0.1:8001/health`

### Deploy on Windows Server (PM2 + nginx)

Recommended production layout:

```
D:\app\eve\
├── .venv\
├── .env
├── bin\ffmpeg.exe
├── data\jobs\
├── logs\
├── ecosystem.config.cjs
└── src\eve\
```

1. Install dependencies (venv)
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

2. Copy `.env.example` to `.env` and adjust paths (`JOB_DATA_DIR`, `LOG_DIR`, etc.)

3. Start with PM2
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Setup-EVEDeploy.ps1
```

Or manually:
```powershell
# Replace C:/eve with your project root
(Get-Content ecosystem.config.cjs -Raw) -replace '__EVE_ROOT__','C:/eve' |
  Set-Content ecosystem.config.cjs -Encoding UTF8
pm2 update
pm2 delete eve-api
pm2 delete ecosystem.config.cjs   # if PM2 registered the file itself by mistake
pm2 start ecosystem.config.cjs
pm2 save
pm2 status   # name must be "eve-api", not "ecosystem.config..."
```

> **Windows note:** PM2 runs `scripts/start-eve-api.cmd` → `pythonw.exe` (no console window). If `pm2 status` shows `ecosystem.config...` instead of `eve-api`, PM2 failed to parse the config — run `pm2 update`, delete the bad process, and retry. For debugging only: `.venv\Scripts\python.exe -m uvicorn eve.api.main:app --host 127.0.0.1 --port 8001`

**PM2 keeps restarting?** Check in order:
1. `pm2 update` (in-memory PM2 version mismatch causes odd behavior)
2. `pm2 status` — process name must be `eve-api`, not `ecosystem.config.cjs`
3. `pm2 logs eve-api --lines 50` and `logs\eve-api.log`
4. Test launcher directly: `scripts\start-eve-api.cmd` (should stay running; Ctrl+C to stop)

4. Configure nginx using [`deploy/nginx.conf`](deploy/nginx.conf) as a template (proxy to `127.0.0.1:8001`)

### API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/jobs` | Upload audio + `cut_mode` → returns `job_id` |
| `GET` | `/api/v1/jobs/{job_id}` | Job status |
| `GET` | `/api/v1/jobs/{job_id}/download` | Download processed file |
| `GET` | `/health` | Health check |

### Cut modes (`cut_mode` form field)

* `aggressive` — Detect music segments with YAMNet, invert to remove music (heavy cut)
* `conservative` — Keep VAD speech segments only, connect with fade in/out (light cut)

### Job status fields

`GET /api/v1/jobs/{job_id}` includes:

| Field | Description |
|-------|-------------|
| `status` | `queued`, `processing`, `completed`, or `failed` |
| `unchanged` | `true` when aggressive mode found no music to cut (output equals input) |
| `result_message` | e.g. `오디오 파일에서 음악 구간이 검출되지 않습니다` when `unchanged` is true |
| `expires_at` | Download deadline (`completed_at` + `JOB_RETENTION_HOURS`, default 6 hours) |
| `error` | Set only when `status` is `failed` |

Completed/failed jobs and their files under `data/jobs/` are deleted automatically after `JOB_RETENTION_HOURS` (default **6 hours**).

Example:
```powershell
curl -X POST "http://127.0.0.1:8001/api/v1/jobs" `
  -F "file=@sample.wav" `
  -F "cut_mode=aggressive"
```

### Legacy batch mode (directory polling)

The original NSSM-based batch scheduler is still available but not used in the API deployment:

```powershell
.\.venv\Scripts\python.exe -m eve --poll 60 --timeout 600
powershell -ExecutionPolicy Bypass -File .\scripts\Setup-EVEService.ps1
```
---

## 📜 License

Licensed under the **Apache License 2.0**. See [`LICENSE`](./LICENSE) for details.

---

## 📝 Notes

* Music detection is handled by [YAMNet](https://github.com/tensorflow/models/tree/master/research/audioset/yamnet) audio classifier.
* Voice regions are segmented using [Silero-VAD](https://github.com/snakers4/silero-vad?tab=readme-ov-file).
* Speech with background music is preserved intentionally.
* Production deployment uses FastAPI + uvicorn on `127.0.0.1:8001`, managed by PM2 and exposed via nginx.