from __future__ import annotations

import json
import re
import os
from typing import Iterable

from pathlib import Path
from dotenv import load_dotenv

# <root>/src/speechcut/config/settings.py
_THIS = Path(__file__).resolve()
_SRC_DIR = _THIS.parents[2]
_ROOT_DIR = _SRC_DIR.parent

load_dotenv(_ROOT_DIR / '.env', override=True)

def _norm_env_path(name: str, default_rel: str | Path, base: Path = _ROOT_DIR) -> Path:
  '''
    Normalize the relative paths in the .env into absolute paths based on “base” (the project root).
    If the value is empty, use default_rel relative to base.
  '''
  val = os.getenv(name)
  p = Path(val) if val else Path(default_rel)
  if not p.is_absolute():
    p = (base / p).resolve()
  else:
    p = p.resolve()
  return p

def _bin_default(exe: str) -> str:
  return f'bin/{exe}.exe' if os.name == 'nt' else f'bin/{exe}'

def _read_input_dirs_from_env(
    name: str = 'INPUT_DIR',
    default_rel: str | Path = 'input',
    base: Path = _ROOT_DIR
) -> list[Path]:
  '''
    If INPUT_DIR in the .env is a JSON list, use that list; otherwise treat it as a single value.
    For each item, if it is a relative path, convert it to an absolute path based on base.
    If empty, use default_rel.
  '''
  raw = (os.getenv(name) or '').strip()
  if raw.startswith('['):
    try:
      arr = json.loads(raw)
    except Exception as e:
      raise ValueError(f'{name} failed to parse JSON: {e}')
    paths: list[Path] = []
    for s in arr:
      v = str(s).strip()
      if not v:
        continue
      p = Path(v)
      p = (base / p).resolve() if not p.is_absolute() else p.resolve()
      paths.append(p)
    if paths:
      return paths

  # If it is not JSON or is empty, handle it as a single value(in the list).
  return [_norm_env_path(name, default_rel, base)]

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
  ROOT_DIR: Path = _ROOT_DIR # <root>
  SRC_DIR: Path = _SRC_DIR # <root>/src

  # Directories
  INPUT_DIR: list[Path] = _read_input_dirs_from_env('INPUT_DIR')
  OUTPUT_DIR: Path = _norm_env_path('OUTPUT_DIR', 'output', ROOT_DIR)
  
  FFMPEG_BIN: Path = _norm_env_path('FFMPEG_EXE', _bin_default('ffmpeg'), ROOT_DIR)
  FFPROBE_BIN: Path = _norm_env_path('FFPROBE_EXE',_bin_default('ffprobe'), ROOT_DIR)

  XML_FILENAME = Path(os.getenv('XML_FILENAME', 'Auto_Metadata.xml'))

  # Processing audio
  PROCESSING_SR = int(os.getenv('PROCESSING_SR', 16000))
  PROCESSING_CH = int(os.getenv('PROCESSING_CH', 1))

  # Output audio
  OUTPUT_SR = int(os.getenv('OUTPUT_SR', 44100))
  OUTPUT_CH = int(os.getenv('OUTPUT_CH', 2))
  OUTPUT_BR = os.getenv('OUTPUT_BR', '192k')
  OUTPUT_FORMAT = os.getenv('OUTPUT_FORMAT', 'mp3')

  # Silence detection
  SILENCE_DB = os.getenv('SILENCE_DB', '-30dB')
  SILENCE_DURATION = float(os.getenv('SILENCE_DURATION', 3.0))
  SILENCE_PADDING = float(os.getenv('SILENCE_PADDING', 0.3))

  # VAD settings
  SPEECH_THRESHOLD = float(os.getenv('SPEECH_THRESHOLD', 0.4))
  MIN_SPEECH_MS = int(os.getenv('MIN_SPEECH_MS', 10000))
  MERGE_GAP_SECONDS = int(os.getenv('MERGE_GAP_SECONDS', 10))
  MARGIN_SECONDS = int(os.getenv('MARGIN_SECONDS', 4))
  FADE_SECONDS = float(os.getenv('FADE_SECONDS', 0.5))

  # File size limit
  MAX_AUDIO_BYTES = int(os.getenv('MAX_AUDIO_BYTES', 100 * 1024 * 1024))  # 100MB


settings = Settings()
