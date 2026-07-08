import logging
from typing import Union
from pathlib import Path
import numpy as np
import torch
from silero_vad import load_silero_vad, get_speech_timestamps, read_audio

from eve.config.settings import settings

log = logging.getLogger(__name__)


class SileroVADWrapper:
  def __init__(self, sr=settings.PROCESSING_SR):
    self.sr = sr
    self.model = load_silero_vad()
    requested_device = settings.INFERENCE_DEVICE
    use_cuda = requested_device in {'auto', 'cuda'} and torch.cuda.is_available()
    self.device = 'cuda' if use_cuda else 'cpu'
    try:
      if hasattr(self.model, 'to'):
        self.model.to(torch.device(self.device))
      else:
        self.device = 'cpu'
    except Exception:
      self.device = 'cpu'
      if hasattr(self.model, 'to'):
        self.model.to(torch.device('cpu'))
    if hasattr(self.model, 'eval'):
      self.model.eval()
    log.info('Silero VAD backend=pytorch device=%s', self.device)

  def describe_backend(self) -> dict[str, object]:
    return {
      'backend': 'pytorch',
      'device': self.device,
      'providers': [],
    }

  def _prepare_audio(self, audio: np.ndarray | torch.Tensor) -> torch.Tensor:
    if isinstance(audio, torch.Tensor):
      return audio.to(self.device)
    return torch.as_tensor(audio, dtype=torch.float32, device=self.device)

  def get_speech_timestamps(self, audio: np.ndarray | torch.Tensor, sampling_rate: int):
    prepared = self._prepare_audio(audio)
    return get_speech_timestamps(prepared, self.model, sampling_rate=self.sr or sampling_rate)

  def read_audio(self, path: Union[str, Path], sampling_rate):
    '''read audio file and keep it on CPU for downstream slicing/classification.'''
    return read_audio(str(path), sampling_rate=self.sr or sampling_rate)
