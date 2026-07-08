from __future__ import annotations

import logging
import queue
import threading
from datetime import timedelta
from pathlib import Path

from eve.api.job_store import JobStore
from eve.api.schemas import JobStatus
from eve.app.manager import Supervisor
from eve.config.settings import settings
from eve.utils.timezone import now_kst

log = logging.getLogger('eve.api.worker_bridge')


class WorkerBridge:
  def __init__(self, job_store: JobStore):
    self.job_store = job_store
    self._queue: queue.Queue[str] = queue.Queue()
    self._supervisor = Supervisor(default_timeout=settings.JOB_TIMEOUT_SECONDS)
    self._thread: threading.Thread | None = None
    self._cleanup_thread: threading.Thread | None = None
    self._stop = threading.Event()

  def start(self) -> None:
    self.job_store.reset_processing_to_queued()
    for job_id in self.job_store.list_queued_ids():
      self._queue.put(job_id)

    self._thread = threading.Thread(target=self._run, name='eve-job-worker', daemon=True)
    self._thread.start()
    self._cleanup_thread = threading.Thread(target=self._cleanup_loop, name='eve-job-cleanup', daemon=True)
    self._cleanup_thread.start()
    log.info('worker bridge started')

  def enqueue(self, job_id: str) -> None:
    self._queue.put(job_id)

  def shutdown(self) -> None:
    self._stop.set()
    if self._thread is not None:
      self._thread.join(timeout=5)
    if self._cleanup_thread is not None:
      self._cleanup_thread.join(timeout=5)
    self._supervisor.shutdown()
    log.info('worker bridge stopped')

  def _run(self) -> None:
    while not self._stop.is_set():
      try:
        job_id = self._queue.get(timeout=1)
      except queue.Empty:
        continue
      self._process_job(job_id)

  def _process_job(self, job_id: str) -> None:
    job = self.job_store.get_job(job_id)
    if job is None or job['status'] != JobStatus.queued:
      return

    self.job_store.update_status(
      job_id,
      JobStatus.loading,
      status_message='Loading audio and models',
    )
    input_path = Path(job['input_path'])
    output_path = Path(job['output_path'])
    errors: list[str] = []
    results: list[dict] = []

    def update_progress(step_name: str, message: str | None = None) -> None:
      self.job_store.update_status(
        job_id,
        JobStatus(step_name),
        status_message=message,
      )

    log.info('processing job %s (%s)', job_id, job['cut_mode'].value)
    status = self._supervisor.process(
      str(input_path),
      cut_mode=job['cut_mode'].value,
      output_path=str(output_path),
      update_xml=False,
      error_out=errors,
      result_out=results,
      progress_callback=update_progress,
    )

    if status == 'ok' and output_path.exists():
      info = results[0] if results else {}
      self.job_store.update_status(
        job_id,
        JobStatus.completed,
        status_message=info.get('message'),
        result_message=info.get('message'),
        unchanged=bool(info.get('bypassed')),
      )
      log.info('job %s completed (unchanged=%s)', job_id, info.get('bypassed', False))
      return

    if status == 'timeout':
      self.job_store.update_status(
        job_id,
        JobStatus.failed,
        status_message='Processing timed out',
        error='processing timeout',
      )
      log.warning('job %s timed out', job_id)
      return

    error = errors[0] if errors else 'processing failed'
    self.job_store.update_status(
      job_id,
      JobStatus.failed,
      status_message=error,
      error=error,
    )
    log.warning('job %s failed: %s', job_id, error)

  def _cleanup_loop(self) -> None:
    while not self._stop.wait(3600):
      cutoff = now_kst() - timedelta(hours=settings.JOB_RETENTION_HOURS)
      for job_id in self.job_store.list_expired(cutoff):
        log.info('deleting expired job %s', job_id)
        self.job_store.delete_job(job_id)
