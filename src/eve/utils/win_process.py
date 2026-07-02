from __future__ import annotations

import os


def apply_windows_process_hacks() -> None:
  '''Hide console windows for multiprocessing worker children on Windows.'''
  if os.name != 'nt':
    return

  try:
    import multiprocessing.spawn as spawn

    _orig_get_executable = spawn.get_executable

    def _get_executable() -> str:
      exe = _orig_get_executable()
      if exe.lower().endswith('python.exe'):
        pythonw = f'{exe[:-10]}pythonw.exe'
        if os.path.isfile(pythonw):
          return pythonw
      return exe

    spawn.get_executable = _get_executable
  except Exception:
    pass
