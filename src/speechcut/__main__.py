from __future__ import annotations
import argparse, multiprocessing as mp, logging
from multiprocessing import Queue
from speechcut.utils.logging_setup import setup_log_listener, install_log_queue_handler
from speechcut.app.scheduler import run_scheduler

def parse_args():
  p = argparse.ArgumentParser(prog='speechcut', description='Speech-only generator scheduler')
  p.add_argument('--poll', type=int, default=60, help='Polling interval seconds (default: 60)')
  p.add_argument('--timeout', type=int, default=600, help='Per-task timeout seconds (default: 600)')
  return p.parse_args()

def main():
  args = parse_args()

  log_queue: Queue = mp.Queue()
  listener = setup_log_listener(log_queue)   # 파일 회전 + 콘솔
  try:
    install_log_queue_handler(log_queue)   # 메인 프로세스 루트에 QueueHandler
    logging.getLogger('speechcut.bootstrap').info('speechcut starting...')
    run_scheduler(polling_seconds=args.poll, timeout_sec=args.timeout, log_queue=log_queue)
  finally:
    listener.stop()

if __name__ == '__main__':
  mp.freeze_support()
  mp.set_start_method('spawn', force=True)
  main()
