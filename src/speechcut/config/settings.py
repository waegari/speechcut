from __future__ import annotations
from pathlib import Path
from dotenv import load_dotenv
import os

# <root>/src/speechcut/config/settings.py
_THIS = Path(__file__).resolve()
_SRC_DIR = _THIS.parents[2]
_ROOT_DIR = _SRC_DIR.parent

load_dotenv(_ROOT_DIR / '.env', override=True)

def _norm_env_path(name: str, default_rel: str | Path, base: Path = _ROOT_DIR) -> Path:

#    .env에 들어있는 상대경로를 'base'(프로젝트 루트) 기준 절대경로로 정규화
#    값이 비어있으면 default_rel을 base 기준으로 사용

  val = os.getenv(name)
  p = Path(val) if val else Path(default_rel)
  if not p.is_absolute():
    p = (base / p).resolve()
  else:
    p = p.resolve()
  return p

def _bin_default(exe: str) -> str:
  return f'bin/{exe}.exe' if os.name == 'nt' else f'bin/{exe}'

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
  ROOT_DIR: Path = _ROOT_DIR # <root>
  SRC_DIR: Path = _SRC_DIR # <root>/src

  # Directories
  INPUT_DIR: Path = _norm_env_path('INPUT_DIR', 'input', ROOT_DIR)
  OUTPUT_DIR: Path = _norm_env_path('OUTPUT_DIR', 'output', ROOT_DIR)

  FFMPEG_BIN: Path = _norm_env_path('FFMPEG_EXE', _bin_default('ffmpeg'), ROOT_DIR)
  FFPROBE_BIN: Path = _norm_env_path('FFPROBE_EXE',_bin_default('ffprobe'), ROOT_DIR)

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
