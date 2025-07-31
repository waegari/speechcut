import os
import re
import time
from multiprocessing import Process
from speechcut.ml.vad.silero import SileroVADWrapper
from speechcut.ml.classifier.yamnet import YamnetWrapper
from speechcut.pipelines.speech_extractor import SpeechExtractor

DELAY_PATTERN = re.compile(r'__delay(\d+)', re.IGNORECASE)

def _maybe_delay(audio_path: str):
  '''Sleep for the specified number of seconds if the filename contains `__delay{sec}` (for testing).'''
  basename = os.path.basename(audio_path)
  m = DELAY_PATTERN.search(basename)
  if m:
    sec = int(m.group(1))
    print(f'[worker] simulate delay: {sec}s for {basename}')
    time.sleep(sec)

class WorkerProcess(Process):
  def __init__(self, task_queue, result_queue):
    super().__init__()
    self.task_queue = task_queue
    self.result_queue = result_queue

  def run(self):
    try:
      print(f'[worker] starting, pid={os.getpid()}')
      vad_model = SileroVADWrapper()
      cls_model = YamnetWrapper()
      print(f'[worker] models loaded, pid={os.getpid()}')
    except Exception as e:
      self.result_queue.put({'type': 'fatal', 'error': f'model_load_failed: {e}'})
      return

    while True:
      msg = self.task_queue.get()
      if not isinstance(msg, dict):
        continue

      mtype = msg.get('type')
      if mtype == 'shutdown':
        print(f'[worker] shutdown, pid={os.getpid()}')
        return

      if mtype == 'process':
        task_id = msg.get('id')
        audio_path = msg.get('path')

        try:
          _maybe_delay(audio_path)  # ← Test delay hook
          speechExtractor = SpeechExtractor(
            audio_path,
            vad_model=vad_model,
            classification_model=cls_model
          )
          speechExtractor.speech_music_separate()
          self.result_queue.put({'type': 'done', 'id': task_id})
        except Exception as e:
          self.result_queue.put({'type': 'error', 'id': task_id, 'error': str(e)})
