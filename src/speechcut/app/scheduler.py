from __future__ import annotations
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from speechcut.config.settings import settings
from speechcut.app.manager import Supervisor
from speechcut.utils.editing_metadata import get_new_filename
from speechcut.utils.locking import ProcessingLock

log = logging.getLogger('speechcut.scheduler')
AUDIO_EXTS = {'.wav', '.mp3', '.flac'}

def _marker_paths(src: Path) -> dict[str, Path]:
  new_filename  = get_new_filename(src)
  
  return {
    'success': src.with_stem(f'{new_filename.stem}'),
    'timeout': src.with_name(f'{new_filename.stem}.timeout'),
    'failed':  src.with_name(f'{new_filename.stem}.failed'),
  }

def _mark(src: Path, kind: str, note: str = ''):
  mp = _marker_paths(src)[kind]
  ts = datetime.now().isoformat()
  content = f'{kind} at {ts}'
  if note:
    content += f'\n{note}'
  mp.write_text(content, encoding='utf-8')

def get_unprocessed_audio_files(beginning: datetime) -> list[Path]:
  input_dirs = settings.INPUT_DIR
  now = datetime.now()
  cutoff = max(beginning, now - timedelta(days=1))
  cutoff_month = now - timedelta(days=settings.FILE_RETENTION_DAYS)
  targets: list[Path] = []
  
  for i, input_dir in enumerate(input_dirs):
    log.info(f'scan dir({i+1}/{len(input_dirs)}): {str(input_dir)}')
    for file in input_dir.rglob('*.*'):
      last_modified = datetime.fromtimestamp(file.stat().st_mtime)
      if last_modified < cutoff:
        if (last_modified < cutoff_month) and ('(다시듣기)' in file.stem):
          log.info(f'REMOVE OLD file: {file.name}')
          file.unlink()
        continue
      if '(다시듣기)' in file.stem:
        continue

      marks = _marker_paths(file)

      if marks['success'].exists():
        continue
      # no retry on failure
      if marks['timeout'].exists() or marks['failed'].exists():
        continue
      
      targets.append(file)
>>>>>>> b338c0116bda71cc7958b1f11e8e8345977b9eb0

  return sorted(targets, key=lambda p: p.stat().st_mtime)

def process_file(audio_path: Path, locker: ProcessingLock, manager: Supervisor, timeout_sec: int = 600):
  if locker.is_locked(audio_path):
    log.info(f'[skip] Already processing: {audio_path.name}')
    return

  log.info(f'[process] {audio_path.name}')
  locker.lock(audio_path)
  try:
    status = manager.process(str(audio_path), timeout=timeout_sec)
    if status == 'ok':
      log.info(f'[ok] {audio_path.name}')
    elif status == 'timeout':
      log.warning(f'[timeout] {audio_path.name}')
      _mark(audio_path, 'timeout', note=f'timeout={timeout_sec}s')
    else:
      log.error(f'[error] {audio_path.name}')
      _mark(audio_path, 'failed')
  finally:
    locker.unlock(audio_path)

def run_scheduler(polling_seconds: int = 60, timeout_sec: int = 600, log_queue=None):
  started_at = datetime.now()
  
  locker = ProcessingLock()
  manager = Supervisor(default_timeout=timeout_sec, log_queue=log_queue)

  log.info(f'Scheduler started at {started_at}. Polling every {polling_seconds} sec.')
  try:
    while True:
      cycle_start = time.time()

      files = get_unprocessed_audio_files(started_at)
      log.info(f'[{datetime.now().isoformat()}] {len(files)} target(s).')

      # only ONE file get processed
      if files:
        process_file(files[0], locker, manager, timeout_sec=timeout_sec)
      else:
        log.info('[idle] no new files')

      # if it takes over 1 minute to process, the next cycle will be delayed.
      elapsed = time.time() - cycle_start
      sleep_time = max(0.0, polling_seconds - elapsed)
      time.sleep(sleep_time)
  except KeyboardInterrupt:
    log.info('\nScheduler stopped by user.')
  finally:
    manager.shutdown()

if __name__ == '__main__':
  # safe guard for windows
  import multiprocessing as mp
  mp.set_start_method('spawn', force=True)

  # (for PyInstaller)
  try:
    mp.freeze_support()
  except Exception:
    pass

  run_scheduler(polling_seconds=60, timeout_sec=600)
