from __future__ import annotations
import multiprocessing as mp
import argparse

from src.manager.scheduler import run_scheduler

def parse_args():
  p = argparse.ArgumentParser(description='Speech-only generator scheduler')
  p.add_argument('--poll', type=int, default=60, help='polling interval seconds (default: 60)')
  p.add_argument('--timeout', type=int, default=600, help='per-task timeout seconds (default: 600)')
  return p.parse_args()

def main():
  args = parse_args()
  run_scheduler(polling_seconds=args.poll, timeout_sec=args.timeout)

if __name__ == '__main__':
  mp.freeze_support()
  mp.set_start_method('spawn', force=True)
  main()
