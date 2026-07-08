from __future__ import annotations

from pathlib import Path

import numpy as np
import tensorflow as tf
from tensorflow.python.framework.convert_to_constants import convert_variables_to_constants_v2
import tf2onnx


ROOT_DIR = Path(__file__).resolve().parent
MODEL_DIR = ROOT_DIR / 'src' / 'eve' / 'ml' / 'classifier' / 'models' / 'yamnet_saved'
OUT_PATH = ROOT_DIR / 'src' / 'eve' / 'ml' / 'classifier' / 'models' / 'yamnet.onnx'


def main() -> None:
  if not MODEL_DIR.exists():
    raise FileNotFoundError(f'SavedModel directory not found: {MODEL_DIR}')

  OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

  model = tf.saved_model.load(str(MODEL_DIR))

  # Force a named serving signature so weights freeze into constants.
  @tf.function(input_signature=[tf.TensorSpec([None], tf.float32, name='waveform')])
  def serving_fn(waveform):
    return model(waveform)

  concrete_fn = serving_fn.get_concrete_function()
  frozen_fn = convert_variables_to_constants_v2(concrete_fn, lower_control_flow=False)
  graph_def = frozen_fn.graph.as_graph_def(add_shapes=True)

  input_names = [tensor.name for tensor in frozen_fn.inputs if tensor.dtype != tf.resource]
  output_names = [tensor.name for tensor in frozen_fn.outputs]

  print('frozen_inputs =', input_names)
  print('frozen_outputs =', output_names)

  if len(input_names) != 1:
    raise RuntimeError(
      'expected exactly 1 frozen input (waveform); '
      f'got {len(input_names)}: {input_names}'
    )

  model_proto, _ = tf2onnx.convert.from_graph_def(
    graph_def,
    name='yamnet',
    input_names=input_names,
    output_names=output_names,
    opset=14,
  )
  OUT_PATH.write_bytes(model_proto.SerializeToString())
  print(f'saved: {OUT_PATH}')

  import onnxruntime as ort

  session = ort.InferenceSession(str(OUT_PATH), providers=['CPUExecutionProvider'])
  ort_inputs = session.get_inputs()
  ort_outputs = session.get_outputs()
  print('ort_inputs =', [(item.name, item.shape, item.type) for item in ort_inputs])
  print('ort_outputs =', [(item.name, item.shape, item.type) for item in ort_outputs])
  if len(ort_inputs) != 1:
    OUT_PATH.unlink(missing_ok=True)
    raise RuntimeError(
      'converted ONNX still has unexpected inputs; removed broken file. '
      f'got {[item.name for item in ort_inputs]}'
    )

  sample = np.zeros(16000, dtype=np.float32)
  result = session.run(None, {ort_inputs[0].name: sample})
  print('smoke_ok outputs=', [tuple(arr.shape) for arr in result])


if __name__ == '__main__':
  main()
