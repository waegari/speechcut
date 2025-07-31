from __future__ import annotations
import argparse
import multiprocessing as mp
from speechcut.app.scheduler import run_scheduler

def parse_args():
    p = argparse.ArgumentParser(prog="speechcut", description="Speech-only generator scheduler")
    p.add_argument("--poll", type=int, default=60, help="Polling interval seconds (default: 60)")
    p.add_argument("--timeout", type=int, default=600, help="Per-task timeout seconds (default: 600)")
    return p.parse_args()

def main():
    args = parse_args()
    run_scheduler(polling_seconds=args.poll, timeout_sec=args.timeout)

if __name__ == "__main__":
    mp.freeze_support()
    mp.set_start_method("spawn", force=True)
    main()
