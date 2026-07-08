import csv
import logging
from pathlib import Path
import numpy as np

from eve.config.settings import settings

MODEL_DIR = Path(__file__).parent / 'models' / 'yamnet_saved'
CLASS_MAP_PATH = MODEL_DIR / 'assets' / 'yamnet_class_map.csv'

log = logging.getLogger(__name__)


class YamnetWrapper:
  def __init__(self):
    self.backend = 'unknown'
    self.device = 'cpu'
    self.providers: list[str] = []
    self.model = None
    self.session = None
    self.input_name: str | None = None
    self.input_rank: int | None = None
    self.output_names: list[str] = []
    self.class_names = self.get_class_names()
    self._load_model()

  def _load_model(self) -> None:
    prefer_onnx = settings.INFERENCE_BACKEND in {'auto', 'onnx'}
    onnx_path = settings.YAMNET_ONNX_PATH
    if prefer_onnx and onnx_path.exists():
      try:
        import onnxruntime as ort

        self.session = ort.InferenceSession(str(onnx_path), providers=settings.ONNX_PROVIDERS)
        input_meta = self.session.get_inputs()[0]
        self.input_name = input_meta.name
        self.input_rank = len(input_meta.shape)
        self.output_names = [item.name for item in self.session.get_outputs()]
        self.providers = list(self.session.get_providers())
        self.backend = 'onnxruntime'
        self.device = 'cuda' if 'CUDAExecutionProvider' in self.providers else 'cpu'
        log.info('YAMNet backend=onnxruntime device=%s providers=%s', self.device, self.providers)
        return
      except Exception as exc:
        log.warning('YAMNet ONNX load failed, falling back to TensorFlow: %s', exc)

    import tensorflow as tf

    self.model = tf.saved_model.load(str(MODEL_DIR))
    self.backend = 'tensorflow'
    self.providers = []
    if tf.config.list_physical_devices('GPU'):
      self.device = 'gpu'
    else:
      self.device = 'cpu'
    log.info('YAMNet backend=tensorflow device=%s', self.device)

  def describe_backend(self) -> dict[str, object]:
    return {
      'backend': self.backend,
      'device': self.device,
      'providers': self.providers,
      'onnx_model_exists': settings.YAMNET_ONNX_PATH.exists(),
    }

  def _prepare_onnx_input(self, waveform) -> np.ndarray:
    arr = np.asarray(waveform, dtype=np.float32)
    if self.input_rank == 2 and arr.ndim == 1:
      arr = arr[np.newaxis, :]
    elif self.input_rank == 1 and arr.ndim > 1:
      arr = arr.reshape(-1)
    return np.ascontiguousarray(arr)

  def _predict_onnx(self, waveform) -> np.ndarray:
    if self.session is None or self.input_name is None:
      raise RuntimeError('ONNX session is not initialized')
    inputs = {self.input_name: self._prepare_onnx_input(waveform)}
    outputs = self.session.run(self.output_names or None, inputs)
    return np.asarray(outputs[0])

  def _predict_tensorflow(self, waveform) -> np.ndarray:
    scores, _, _ = self.model(waveform)
    return scores.numpy()

  def predict(self, waveform) -> np.ndarray:
    if self.session is not None:
      return self._predict_onnx(waveform)
    if self.model is None:
      raise RuntimeError('YAMNet model is not initialized')
    return self._predict_tensorflow(waveform)

  def get_class_names(self):
    class_names = []
    if CLASS_MAP_PATH.exists():
      with CLASS_MAP_PATH.open('r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader)
        class_names = [row[2] for row in reader]
      return class_names

    import tensorflow as tf

    model = self.model or tf.saved_model.load(str(MODEL_DIR))
    csv_path = model.class_map_path().numpy().decode()
    with tf.io.gfile.GFile(csv_path, 'r') as f:
      reader = csv.reader(f)
      next(reader)
      class_names = [row[2] for row in reader]
    return class_names