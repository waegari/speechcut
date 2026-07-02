import os, re, time, logging
from multiprocessing import Process
from eve.utils.logging_setup import install_log_queue_handler
from eve.utils.editing_metadata import add_processed_program_to_xml
from eve.ml.vad.silero import SileroVADWrapper
from eve.ml.classifier.yamnet import YamnetWrapper
from eve.pipelines.speech_extractor import SpeechExtractor

AUDIO_EXTS = {'.wav', '.mp3', '.flac'}
DELAY_PATTERN = re.compile(r'__delay(\d+)', re.IGNORECASE)

def _maybe_delay(audio_path: str):
  '''Sleep for the specified number of seconds if the filename contains `__delay{sec}` (for testing).'''
  basename = os.path.basename(audio_path)
  m = DELAY_PATTERN.search(basename)
  if m:
    sec = int(m.group(1))
    logging.getLogger('eve.worker').debug(f'[worker] simulate delay: {sec}s for {basename}')
    time.sleep(sec)

class WorkerProcess(Process):
  def __init__(self, task_queue, result_queue, log_queue=None):
    super().__init__()
    self.task_queue = task_queue
    self.result_queue = result_queue
    self.log_queue = log_queue

  def run(self):
    if self.log_queue is not None:
      install_log_queue_handler(self.log_queue)
    log = logging.getLogger('eve.worker')
    try:
      log.info(f'[worker] starting, pid={os.getpid()}')
      vad_model = SileroVADWrapper()
      cls_model = YamnetWrapper()
      log.info(f'[worker] models loaded, pid={os.getpid()}')
    except Exception as e:
      log.exception("model_load_failed")
      self.result_queue.put({'type': 'fatal', 'error': f'model_load_failed: {e}'})
      return

    while True:
      msg = self.task_queue.get()
      if not isinstance(msg, dict):
        continue

      mtype = msg.get('type')
      if mtype == 'shutdown':
        log.info(f'[worker] shutdown, pid={os.getpid()}')
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
          separate_success = speechExtractor.speech_music_separate()
          if separate_success:
            add_processed_program_to_xml(audio_path)
            self.result_queue.put({'type': 'done', 'id': task_id})
          else:
            self.result_queue.put({'type': 'error', 'id': task_id, 'error': 'no music or speech only part in the audio file'})
        except Exception as e:
          self.result_queue.put({'type': 'error', 'id': task_id, 'error': str(e)})
