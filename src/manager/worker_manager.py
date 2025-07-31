import queue
import multiprocessing as mp
from src.workers.worker_server import WorkerServer

class WorkerManager:
  '''
  - Maintain a single worker process (models stay resident)
  - When `process(audio_path, timeout)` is called:
    * Enqueue the task and wait on `result_queue` for the response with the matching `task_id` within the timeout.
    * If a timeout occurs, forcibly terminate the worker and recreate the queues/worker (a fresh worker will start on the next call).
    * If processing completes successfully, keep the worker alive for reuse.
  '''
  def __init__(self, default_timeout: int = 600):
    self.ctx = mp.get_context('spawn')
    self.default_timeout = default_timeout
    self._make_queues()
    self.worker = None
    self._task_seq = 0

  def _make_queues(self):
    self.task_queue = self.ctx.Queue()
    self.result_queue = self.ctx.Queue()

  def _start_worker_if_needed(self):
    if self.worker is None or not self.worker.is_alive():
      print('[manager] starting worker...')
      self.worker = WorkerServer(self.task_queue, self.result_queue)
      self.worker.daemon = False  # On Windows, it’s recommended to explicitly set `daemon=False`.
      self.worker.start()
      print(f'[manager] worker started pid={self.worker.pid}')

  def _kill_worker(self):
    if self.worker and self.worker.is_alive():
      print(f'[manager] terminating worker pid={self.worker.pid}')
      self.worker.terminate()
      self.worker.join(5)
      print('[manager] worker terminated')
    self.worker = None
    # Also recreate the queues cleanly (to prevent zombie/stale messages).
    try:
      self.task_queue.close()
      self.result_queue.close()
    except Exception:
      pass
    self._make_queues()

  def process(self, audio_path: str, timeout: int | None = None) -> str:
    '''
    Return value: `'ok' | 'timeout' | 'error'`.
    '''
    self._start_worker_if_needed()
    self._task_seq += 1
    task_id = self._task_seq

    self.task_queue.put({'type': 'process', 'id': task_id, 'path': str(audio_path)})

    to = timeout or self.default_timeout
    try:
      while True:
        msg = self.result_queue.get(timeout=to)
        mtype = msg.get('type')
        if mtype == 'fatal':
          self._kill_worker()
          return 'error'

        if mtype in ('done', 'error'):
          if msg.get('id') != task_id:
            continue
          if mtype == 'done':
            return 'ok'
          else:
            self._kill_worker()
            return 'error'
    except queue.Empty:
      self._kill_worker()
      return 'timeout'
    
  def shutdown(self):
    '''Attempt to gracefully shut down the worker when the program exits.'''
    try:
      if self.worker and self.worker.is_alive():
        self.task_queue.put({'type': 'shutdown'})
        self.worker.join(3)
    finally:
      self._kill_worker()
