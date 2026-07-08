from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class CutMode(str, Enum):
  aggressive = 'aggressive'
  conservative = 'conservative'


class JobStatus(str, Enum):
  queued = 'queued'
  loading = 'loading'
  detecting_speech = 'detecting_speech'
  detecting_music = 'detecting_music'
  merging_segments = 'merging_segments'
  exporting = 'exporting'
  completed = 'completed'
  failed = 'failed'


class JobCreateResponse(BaseModel):
  job_id: str
  status: JobStatus = JobStatus.queued
  cut_mode: CutMode


class JobStatusResponse(BaseModel):
  job_id: str
  status: JobStatus
  status_message: str | None = None
  cut_mode: CutMode
  input_filename: str
  unchanged: bool = False
  result_message: str | None = None
  error: str | None = None
  created_at: datetime
  updated_at: datetime
  completed_at: datetime | None = None
  expires_at: datetime | None = None


class HealthResponse(BaseModel):
  status: str = Field(default='ok')
