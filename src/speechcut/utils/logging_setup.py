from __future__ import annotations
import logging
import logging.handlers
from multiprocessing import Queue
from pathlib import Path
import os

from speechcut.config.settings import settings

FMT = '%(asctime)s %(levelname)s [pid=%(process)d] [%(name)s] %(message)s'
DATEFMT = '%Y-%m-%d %H:%M:%S'

def setup_log_listener(log_queue: Queue, *, log_dir: str | Path | None = None,
           level: str | None = None, filename: str = 'speechcut.log',
           when: str = 'midnight', backup_count: int = 14):
  '''
  Called in the main process: start a QueueListener and attach handlers (file rotation + console).
  Return value: the listener (you must call `.stop()` on shutdown).
  '''
  log_dir = log_dir or settings.LOG_DIR
  log_dir.mkdir(parents=True, exist_ok=True)

  level = (level or settings.LOG_LEVEL or 'INFO').upper()
  file_handler = logging.handlers.TimedRotatingFileHandler(
    log_dir / filename, when=when, backupCount=backup_count, encoding='utf-8'
  )
  file_handler.setFormatter(logging.Formatter(FMT, DATEFMT))
  file_handler.setLevel(getattr(logging, level, logging.INFO))

  # console = logging.StreamHandler()
  # console.setFormatter(logging.Formatter(FMT, DATEFMT))
  # console.setLevel(getattr(logging, level, logging.INFO))

  listener = logging.handlers.QueueListener(log_queue, file_handler, respect_handler_level=True)
  listener.start()
  return listener

def install_log_queue_handler(log_queue: Queue, *, level: str = 'INFO'):
  '''
  Can be called from any process (main/child): attach a QueueHandler to the root logger.
  Child processes (workers) should call this right after `run()` begins.
  '''
  root = logging.getLogger()
  root.handlers.clear()
  root.setLevel(getattr(logging, level.upper(), logging.INFO))
  qh = logging.handlers.QueueHandler(log_queue)
  root.addHandler(qh)
