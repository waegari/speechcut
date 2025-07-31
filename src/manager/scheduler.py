from __future__ import annotations
import time
from pathlib import Path
from datetime import datetime, timedelta
from src.settings.settings import settings
from src.manager.worker_manager import WorkerManager
from src.manager.process_tracker import ProcessTracker

AUDIO_EXTS = {'.wav', '.mp3', '.flac'}

def _marker_paths(src: Path) -> dict[str, Path]:
    return {
        'success': src.with_name(f'{src.stem}_speech_only.mp3'),
        'timeout': src.with_name(f'{src.stem}_speech_only.timeout'),
        'failed':  src.with_name(f'{src.stem}_speech_only.failed'),
    }

def _mark(src: Path, kind: str, note: str = ''):
    mp = _marker_paths(src)[kind]
    ts = datetime.now().isoformat()
    content = f'{kind} at {ts}'
    if note:
        content += f'\n{note}'
    mp.write_text(content, encoding='utf-8')

def get_unprocessed_audio_files() -> list[Path]:
    input_dir = Path(settings.INPUT_DIR)
    cutoff = datetime.now() - timedelta(days=1)
    targets: list[Path] = []

    for file in input_dir.rglob('*.*'):
        if file.suffix.lower() not in AUDIO_EXTS:
            continue
        if '_speech_only' in file.stem:
            continue
        if datetime.fromtimestamp(file.stat().st_mtime) < cutoff:
            continue

        marks = _marker_paths(file)

        if marks['success'].exists():
            continue
        # no retry on failure
        if marks['timeout'].exists() or marks['failed'].exists():
            continue
        
        targets.append(file)

    return sorted(targets, key=lambda p: p.stat().st_mtime)

def process_file(audio_path: Path, tracker: ProcessTracker, manager: WorkerManager, timeout_sec: int = 600):
    if tracker.is_locked(audio_path):
        print(f'[skip] Already processing: {audio_path.name}')
        return

    print(f'[process] {audio_path.name}')
    tracker.lock(audio_path)
    try:
        status = manager.process(str(audio_path), timeout=timeout_sec)
        if status == 'ok':
            print(f'[ok] {audio_path.name}')
        elif status == 'timeout':
            print(f'[timeout] {audio_path.name}')
            _mark(audio_path, 'timeout', note=f'timeout={timeout_sec}s')
        else:
            print(f'[error] {audio_path.name}')
            _mark(audio_path, 'failed')
    finally:
        tracker.unlock(audio_path)

def run_scheduler(polling_seconds: int = 60, timeout_sec: int = 600):
    tracker = ProcessTracker()
    manager = WorkerManager(default_timeout=timeout_sec)

    print(f'Scheduler started. Polling every {polling_seconds} sec.')
    try:
        while True:
            cycle_start = time.time()

            files = get_unprocessed_audio_files()
            print(f'[{datetime.now().isoformat()}] {len(files)} target(s).')

            # only ONE file get processed
            if files:
                process_file(files[0], tracker, manager, timeout_sec=timeout_sec)
            else:
                print('[idle] no new files')

            # if it takes over 1 minute to process, the next cycle will be delayed.
            elapsed = time.time() - cycle_start
            sleep_time = max(0.0, polling_seconds - elapsed)
            time.sleep(sleep_time)
    except KeyboardInterrupt:
        print('\nScheduler stopped by user.')
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
