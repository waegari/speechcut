import csv
import numpy as np
import tensorflow as tf
import tensorflow_hub as tfhub

class YamnetWrapper:
  def __init__(self, model_path="https://tfhub.dev/google/yamnet/1"):
    self.model = tfhub.load(model_path)
    self.class_names = self.get_class_names()

  def predict(self, waveform) -> np.ndarray:
    scores, _, _ = self.model(waveform)
    scores_np = scores.numpy()
    return scores_np

  def get_class_names(self):
    class_names = []
    csv_path = self.model.class_map_path().numpy().decode()
    with tf.io.gfile.GFile(csv_path, 'r') as f:
      reader = csv.reader(f)
      next(reader)
      class_names = [row[2] for row in reader]
    return class_names