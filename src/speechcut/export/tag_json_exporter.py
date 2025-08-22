import json
import logging
import math
from pathlib import Path
from typing import Union, List, Dict

import numpy as np
from speechcut.config.settings import settings
from speechcut.ml.classifier.yamnet import YamnetWrapper

log = logging.getLogger(__name__)

class AudioTagJSONExporter:
  """
  시각화용 JSON(data.json) 생성기 (multi-label).
  - 오디오를 1초 윈도우로 분할
  - 각 초마다 classification_model.predict() -> 확률(0~1), 합=1 아님
  - 평균 확률에서 Top-K 태그를 추출해 [{t, tags:[{label, prob}..]}] 저장

  - classification_model.class_names: List[str]
  - classification_model.predict(audio: np.ndarray) -> np.ndarray
    * (frames, num_classes) 또는 (num_classes,) 형태, 값은 0~1
  """

  def __init__(
    self,
    classification_model,
    sr: int = settings.PROCESSING_SR,
    channels: int = settings.PROCESSING_CH,
    win_s: float = 1,
    hop_s: float = 1,
    topk: int = 4,
  ):
    self.classification_model = classification_model
    self.class_names: List[str] = classification_model.class_names
    self.sr = int(sr)
    self.channels = int(channels)
    self.win_s = float(win_s)
    self.hop_s = float(hop_s)
    self.topk = int(topk)

  def _read_audio(self, path: Union[str, Path]) -> np.ndarray:
    """모노, 고정 SR로 로드 (librosa 대신 soundfile+resample_poly 사용)."""
    import soundfile as sf
    from scipy.signal import resample_poly

    wav, orig_sr = sf.read(str(path), dtype="float32", always_2d=True)  # (N, C)
    wav = wav.mean(axis=1) if wav.shape[1] > 1 else wav[:, 0]
    if orig_sr != self.sr:
      wav = resample_poly(wav, self.sr, orig_sr)

    # regularization
    m = float(np.max(np.abs(wav))) if wav.size else 0.0
    if m > 1.0:
      wav = wav / m
    return wav  # (N,)

  def _classify_window(self, audio_seg: np.ndarray) -> np.ndarray:
    """
    모델이 반환하는 확률을 '그대로' 사용.
    - (T, C)면 time 평균 → (C,)
    - (C,)면 그대로
    - NaN/Inf는 0으로 치환
    """
    scores = self.classification_model.predict(audio_seg)  # (T, C) or (C,)
    if scores.ndim == 1:
      avg_probs = scores.astype(np.float32, copy=False)
    else:
      avg_probs = scores.mean(axis=0).astype(np.float32, copy=False)
    avg_probs = np.nan_to_num(avg_probs, nan=0.0, posinf=0.0, neginf=0.0)
    return avg_probs  # (C,)

  def _topk_tags(self, probs: np.ndarray) -> List[Dict]:
    idx = np.argsort(probs)[::-1][: self.topk]
    out = []
    for i in idx:
      label = self.class_names[int(i)] if int(i) < len(self.class_names) else f"cls_{int(i)}"
      p = float(probs[int(i)])
      # 시각화 안전 범위로 클램프 (0~1)
      if p < 0.0: p = 0.0
      if p > 1.0: p = 1.0
      out.append({"label": label, "prob": p})
    return out

  def run(self, audio_path: Union[str, Path], out_json_path: Union[str, Path]) -> Path:
    """
    오디오 전체를 순회하며 초 단위로 Top-K 태그 생성, JSON 저장.
    - 마지막 자투리(< win_s)는 버림. (옵션으로 포함 가능)
    """
    audio_path = Path(audio_path).resolve()
    out_json_path = Path(out_json_path).resolve()
    out_json_path.parent.mkdir(parents=True, exist_ok=True)

    wav = self._read_audio(audio_path)
    n = len(wav)
    if n == 0:
      raise ValueError("빈 오디오입니다.")

    win = int(round(self.win_s * self.sr))
    hop = int(round(self.hop_s * self.sr))
    if win <= 0 or hop <= 0:
      raise ValueError("win_s, hop_s는 양수여야 합니다.")

    num_steps = max(0, 1 + (n - win) // hop) if n >= win else 0
    if num_steps == 0:
      probs = self._classify_window(wav.astype(np.float32, copy=False))
      result = [{"t": 0, "tags": self._topk_tags(probs)}]
      out_json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
      log.info("data.json saved (short audio).")
      return out_json_path

    result: List[Dict] = []
    for step in range(num_steps):
      start = step * hop
      end = start + win
      seg = wav[start:end].astype(np.float32, copy=False)

      probs = self._classify_window(seg)
      tags = self._topk_tags(probs)

      t_sec = int(math.floor(start / self.sr))  # 윈도우 함수 적용 시작 시각(정수 초)
      result.append({"t": t_sec, "tags": tags})

    out_json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"saved: {out_json_path} (steps={len(result)}, win={self.win_s}s, hop={self.hop_s}s)")
    return out_json_path

exporter = AudioTagJSONExporter(
  classification_model=YamnetWrapper(),
  sr=16000, channels=1,
  win_s=1, hop_s=1, topk=4,
)

# exporter.run(
#   audio_path=r"D:\input_audio\test.mp3",
#   out_json_path=r"D:\input_audio\test.json",
# )
