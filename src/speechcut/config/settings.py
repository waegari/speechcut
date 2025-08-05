from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
  # Directories
  INPUT_DIR = Path(os.getenv('INPUT_DIR', BASE_DIR / 'input'))
  OUTPUT_DIR = Path(os.getenv('OUTPUT_DIR', BASE_DIR / 'output'))
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
