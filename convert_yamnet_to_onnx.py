from __future__ import annotations

from pathlib import Path

import tensorflow as tf
import tf2onnx


ROOT_DIR = Path(__file__).resolve().parent
MODEL_DIR = ROOT_DIR / 'src' / 'eve' / 'ml' / 'classifier' / 'models' / 'yamnet_saved'
OUT_PATH = ROOT_DIR / 'src' / 'eve' / 'ml' / 'classifier' / 'models' / 'yamnet.onnx'


def main() -> None:
  if not MODEL_DIR.exists():
    raise FileNotFoundError(f'SavedModel directory not found: {MODEL_DIR}')

  OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

  model = tf.saved_model.load(str(MODEL_DIR))
  concrete_fn = model.__call__.get_concrete_function(
    tf.TensorSpec([None], tf.float32)
  )

  tf2onnx.convert.from_function(
    concrete_fn,
    input_signature=None,
    opset=14,
    output_path=str(OUT_PATH),
  )

  print(f'saved: {OUT_PATH}')


if __name__ == '__main__':
  main()
