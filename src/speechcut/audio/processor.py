import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Union
import ffmpeg

from speechcut.config.settings import settings
from speechcut.utils.subproc import no_window_kwargs

log = logging.getLogger('speechcut.scheduler')
AUDIO_EXTS = {'.wav', '.mp3', '.flac'}

class AudioProcessor:
  '''
  A class that provides audio conversion and silence detection using FFmpeg.

  Attributes:
    source_audio_path (Path): Input audio file path
    output_sr (int): Output sampling rate (Hz)
    output_br (str): Output MP3 bitrate (e.g., '192k')
    output_ch (int): Output number of audio channels
    max_bytes (int): Maximum buffer size allowed (in bytes)
    silence_boundaries (list): Detected silence intervals (start, end)
    audio_info (dict): Cached audio metadata
  '''

  def __init__(
    self,
    path: Union[str, Path],
    sr: int = settings.PROCESSING_SR,
    channels: int = settings.PROCESSING_CH,
    
    output_sr: int = settings.OUTPUT_SR,
    output_br: str = settings.OUTPUT_BR,
    output_ch: int = settings.OUTPUT_CH,
    max_bytes: int = settings.MAX_AUDIO_BYTES,
  ):
    self.source_audio_path = Path(path) if isinstance(path, str) else path

    self.processing_sr = sr
    self.processing_ch = channels
    
    self.output_sr = output_sr
    self.output_br = output_br
    self.output_ch = output_ch
    self.max_bytes = max_bytes

    self.silence_boundaries: list[tuple[float, float]] | None = None
    self.audio_info: dict | None = None

  def get_audio_info(self, get_new_info: bool = False) -> dict:
    if self.audio_info and not get_new_info:
      return self.audio_info

    path = str(self.source_audio_path)
    cmd = [
      'ffprobe', '-v', 'error',
      '-select_streams', 'a:0',
      '-show_entries', 'stream=codec_name,sample_rate,channels,bit_rate,duration',
      '-show_entries', 'format=duration',
      '-of', 'json', path,
    ]
    info = subprocess.check_output(cmd, text=True, **no_window_kwargs())
    stream_info = json.loads(info)['streams'][0]
    format_info = json.loads(info)['format']
    format_dur = float(format_info.get('duration'))
    stream_dur = float(stream_info.get('duration', format_dur))
    stream_info['duration'] = stream_dur

    self.audio_info = stream_info
    return stream_info

  def _detect_silence(
    self,
    noise: str = settings.SILENCE_DB or '-30dB',
    d: float = settings.SILENCE_DURATION or 3.0,
    pad: float = settings.SILENCE_PADDING or 0.3,
    get_new_boundaries: bool = False,
  ) -> list[tuple[float, float]]:
    '''
    Detect silence intervals using FFmpeg 'silencedetect' filter.

    Parameters:
      noise (str): Silence threshold (e.g., '-30dB')
      d (float): Minimum silence duration (in seconds)
      pad (float): Padding duration to add to each boundary (in seconds)
      get_new_boundaries (bool): Force new detection even if cached

    Returns:
      List of (start_time, end_time) tuples representing silence intervals
    '''
    if self.silence_boundaries and not get_new_boundaries:
      return self.silence_boundaries

    a_info: dict = self.get_audio_info()
    dur: float = a_info['duration']

    _, stderr = (
      ffmpeg
      .input(str(self.source_audio_path))
      .filter('silencedetect', noise=noise, d=d)
      .output('null', format='null')
      .run(capture_stdout=True, capture_stderr=True, quiet=True)
    )

    if isinstance(stderr, (bytes, bytearray)):
      stderr = stderr.decode('utf-8', errors='ignore')

    starts = [float(x) for x in re.findall(r'silence_start:\s*([\d.]+)', stderr)]
    ends = [float(x) for x in re.findall(r'silence_end:\s*([\d.]+)', stderr)]

    # If silence at end, ffmpeg may omit silence_end; add full duration
    if len(ends) < len(starts):
      ends.append(dur)

    # Add padding
    padded = []
    for s, e in zip(starts, ends):
      s_pad = max(0.0, s - min(d, pad))
      e_pad = min(dur, e + min(d, pad))
      padded.append((s_pad, e_pad))

    self.silence_boundaries = padded
    return padded

  def find_extended_silence_boundary(
    self,
    ts: float,
    *,
    direction: str = 'forward',
    min_silence_sec: float = 3.0,
    noise: str = '-30dB',
  ) -> float:
    '''
    Search for a long silence near timestamp `ts`.

    Parameters:
      ts (float): Reference timestamp in seconds
      direction (str): 'forward' to search after `ts`, 'backward' to search before
      min_silence_sec (float): Minimum silence duration to qualify
      noise (str): Silence threshold in dB

    Returns:
      float: Found silence boundary timestamp (start or end) or 0.0 if not found
    '''
    if direction not in ('forward', 'backward'):
      raise ValueError("direction must be 'forward' or 'backward'")

    intervals = self.silence_boundaries or self._detect_silence(noise=noise, d=min_silence_sec)

    if direction == 'forward':
      for s, e in intervals:
        if s >= ts or (s <= ts < e):
          if e - max(s, ts) >= min_silence_sec:
            return e
    else:
      for s, e in reversed(intervals):
        if e <= ts or (s < ts <= e):
          if min(e, ts) - s >= min_silence_sec:
            return s

    return 0.0