# 🎙️ speechcut — Automatic Speech-Only Radio Replayer

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

* Python 3.11+
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

### Run (at .venv)
```powershell
.\.venv\Scripts\python.exe -m speechcut --poll 60 --timeout 600
```
---

## 📜 License

Licensed under the **Apache License 2.0**. See [`LICENSE`](./LICENSE) for details.

---

## 📝 Notes

* Music detection is handled by [YAMNet](https://github.com/tensorflow/models/tree/master/research/audioset/yamnet) audio classifier.
* Voice regions are segmented using [Silero-VAD](https://github.com/snakers4/silero-vad?tab=readme-ov-file).
* Speech with background music is preserved intentionally.
* Currently designed for local or internal use on Windows.