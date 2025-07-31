from pathlib import Path
from threading import Lock
from typing import Set

class ProcessTracker:
  '''
  Tracks files currently being processed to prevent duplicate handling.
  '''

  def __init__(self):
    # A set of file path strings to prevent duplicate processing
    self._locked_files: Set[str] = set()
    self._lock = Lock()

  def is_locked(self, path: Path) -> bool:
    '''Check if the given file path is currently locked (being processed).'''
    with self._lock:
      return str(path.resolve()) in self._locked_files

  def lock(self, path: Path) -> None:
    '''Lock the file path to mark it as being processed.'''
    with self._lock:
      self._locked_files.add(str(path.resolve()))

  def unlock(self, path: Path) -> None:
    '''Unlock the file path after processing is done.'''
    with self._lock:
      self._locked_files.discard(str(path.resolve()))
