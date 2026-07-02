from __future__ import annotations

import logging
import multiprocessing as mp
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from eve.api.job_store import JobStore
from eve.api.routers import jobs
from eve.api.schemas import HealthResponse
from eve.api.worker_bridge import WorkerBridge
from eve.config.settings import settings
from eve.utils.logging_setup import setup_logging

log = logging.getLogger('eve.api')


@asynccontextmanager
async def lifespan(app: FastAPI):
  os.environ['PATH'] = str(settings.FFMPEG_BIN.parent) + os.pathsep + os.environ.get('PATH', '')
  try:
    mp.set_start_method('spawn', force=True)
  except RuntimeError:
    pass

  settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
  setup_logging(settings.LOG_DIR, settings.LOG_LEVEL)

  job_store = JobStore(settings.JOB_DB_PATH, settings.JOB_DATA_DIR)
  bridge = WorkerBridge(job_store)
  bridge.start()

  app.state.job_store = job_store
  app.state.worker_bridge = bridge
  log.info('EVE API started on %s:%s', settings.API_HOST, settings.API_PORT)
  try:
    yield
  finally:
    bridge.shutdown()
    log.info('EVE API stopped')


app = FastAPI(title='EVE API', version='0.1.0', lifespan=lifespan)
app.include_router(jobs.router)


@app.get('/health', response_model=HealthResponse)
async def health():
  return HealthResponse()


def run() -> None:
  uvicorn.run(
    'eve.api.main:app',
    host=settings.API_HOST,
    port=settings.API_PORT,
    reload=False,
  )


if __name__ == '__main__':
  mp.freeze_support()
  run()
