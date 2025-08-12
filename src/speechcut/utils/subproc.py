import os, subprocess

def no_window_kwargs():
  '''
    no console popup in windows
  '''
  if os.name == 'nt':
    return {'creationflags': subprocess.CREATE_NO_WINDOW}
  return {}