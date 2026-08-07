from __future__ import annotations

from pathlib import Path

import aiofiles
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from eve.api.schemas import CutMode, JobCreateResponse, JobStatus, JobStatusResponse
from eve.config.settings import settings

router = APIRouter(prefix='/api/v1/jobs', tags=['jobs'])

AUDIO_EXTS = {'.wav', '.mp3', '.flac'}
MEDIA_TYPES = {
  '.wav': 'audio/wav',
  '.mp3': 'audio/mpeg',
  '.flac': 'audio/flac',
}


def _get_job_store(request: Request):
  return request.app.state.job_store


def _get_worker_bridge(request: Request):
  return request.app.state.worker_bridge


@router.post('', response_model=JobCreateResponse, status_code=202)
async def create_job(
  request: Request,
  file: UploadFile = File(...),
  cut_mode: CutMode = Form(CutMode.aggressive),
):
  if not file.filename:
    raise HTTPException(status_code=400, detail='filename is required')

  suffix = Path(file.filename).suffix.lower()
  if suffix not in AUDIO_EXTS:
    raise HTTPException(status_code=400, detail=f'unsupported audio format: {suffix}')

  content = await file.read()
  if not content:
    raise HTTPException(status_code=400, detail='empty file')
  if len(content) > settings.MAX_UPLOAD_BYTES:
    raise HTTPException(status_code=413, detail='file too large')

  job_store = _get_job_store(request)
  worker_bridge = _get_worker_bridge(request)

  job_id, input_path, _output_path = job_store.create_job(cut_mode, file.filename)

  async with aiofiles.open(input_path, 'wb') as out:
    await out.write(content)

  worker_bridge.enqueue(job_id)
  return JobCreateResponse(job_id=job_id, status=JobStatus.queued, cut_mode=cut_mode)


@router.get(
  '/{job_id}',
  response_model=JobStatusResponse,
  summary='Get job status',
  description=(
    'Poll job progress. After speech/music detection finishes, status becomes '
    '`segments_ready` and `segments` / `source_duration` are populated. '
    'Those fields remain on subsequent polls through merging, exporting, and completed. '
    'Silence-only audio may yield an empty `segments` array.'
  ),
)
async def get_job(job_id: str, request: Request):
  job_store = _get_job_store(request)
  job = job_store.get_job(job_id)
  if job is None:
    raise HTTPException(status_code=404, detail='job not found')
  return JobStatusResponse(**job)


@router.get(
  '/{job_id}/download',
  summary='Download processed audio',
  description='Returns the processed WAV (or original format) only when status is completed.',
  responses={
    200: {
      'description': 'Processed audio file',
      'content': {
        'audio/wav': {},
        'audio/mpeg': {},
        'audio/flac': {},
        'application/octet-stream': {},
      },
    },
    409: {
      'description': (
        'Job is not completed yet (queued / loading / detecting_* / '
        'segments_ready / merging_segments / exporting) or has failed'
      ),
    },
    404: {'description': 'Job or output file not found'},
  },
)
async def download_job(job_id: str, request: Request):
  job_store = _get_job_store(request)
  job = job_store.get_job(job_id)
  if job is None:
    raise HTTPException(status_code=404, detail='job not found')
  if job['status'] != JobStatus.completed:
    raise HTTPException(
      status_code=409,
      detail=f'job is not completed (status={job["status"].value})',
    )

  output_path = Path(job['output_path'])
  if not output_path.exists():
    raise HTTPException(status_code=404, detail='output file not found')

  suffix = output_path.suffix.lower()
  media_type = MEDIA_TYPES.get(suffix, 'application/octet-stream')
  return FileResponse(
    path=output_path,
    filename=job['input_filename'],
    media_type=media_type,
  )
