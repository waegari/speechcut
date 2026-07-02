'''Headless entry point for Windows PM2 / service deployment.'''
from __future__ import annotations

import ctypes
import multiprocessing as mp
import os


def _hide_console_window() -> None:
  if os.name != 'nt':
    return
  try:
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
      ctypes.windll.user32.ShowWindow(hwnd, 0)
  except Exception:
    pass


def main() -> None:
  from eve.utils.win_process import apply_windows_process_hacks

  apply_windows_process_hacks()
  _hide_console_window()

  from eve.api.main import run

  run()


if __name__ == '__main__':
  mp.freeze_support()
  main()
