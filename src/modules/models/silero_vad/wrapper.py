from typing import Union
from pathlib import Path
import numpy as np
from silero_vad import load_silero_vad, get_speech_timestamps, read_audio

from src.settings.settings import settings

class SileroVADWrapper:
  def __init__(self, sr=settings.PROCESSING_SR):
    self.sr = sr
    self.model = load_silero_vad()

  def get_speech_timestamps(self, audio: np.ndarray, sampling_rate: int):
    return get_speech_timestamps(audio, self.model, sampling_rate=self.sr or sampling_rate)

  def read_audio(self, path: Union[str, Path], sampling_rate) -> np.ndarray:
    '''read audio file as an np.ndarray. `sr` = 16000, `ch` = 1(mono).'''
    return read_audio(str(path), sampling_rate=self.sr or sampling_rate)
