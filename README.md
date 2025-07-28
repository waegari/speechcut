# 🎙️ speechcut — Automatic Speech-Only Radio Replayer

Automatically generates replay-friendly versions of radio shows by removing **all standalone music segments**, regardless of copyright status, while preserving speech and DJ talk — including speech with background music.
Designed to support compliance with replay service policies and mitigate copyright risks.

---

## 🔧 Features

* 🎛️ **Standalone music removal**
  Removes all music-only sections from radio broadcast audio files.

* 🗣️ **Speech preservation**
  Keeps DJ talk, narration, interviews, and announcements intact.

* 🎵 **Speech with background music**
  Background music under speech is **not** removed — treated as part of the speech content.

* ⚡ **Automatic processing**
  Fully automated pipeline using audio classification and voice activity detection.

---

## 🧠 Technologies

* **YAMNet** (by Google): audio classification model for detecting music vs. speech
* **Silero VAD**: fast and lightweight voice activity detection model

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

### Prerequisites

* Python 3.10+
* FFmpeg installed and available in PATH

### Installation

```bash
pip install -r requirements.txt
```

### Run FastAPI server (dev)

```bash
uvicorn app.main:app --reload
```

### API Endpoints (example)

* `POST /separate` — Upload audio and get speech-only version

*Additional documentation coming soon.*

---

## 📜 License

Licensed under the **Apache License 2.0**. See [`LICENSE`](./LICENSE) for details.

---

## 📝 Notes

* Music detection is handled by YAMNet audio classifier.
* Voice regions are segmented using Silero VAD.
* Speech with background music is preserved intentionally.
* Currently designed for local or internal use on Windows (FastAPI works fine).
