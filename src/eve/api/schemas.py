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
  segments_ready = 'segments_ready'
  merging_segments = 'merging_segments'
  exporting = 'exporting'
  completed = 'completed'
  failed = 'failed'


class SegmentType(str, Enum):
  speech = 'speech'
  music = 'music'
  non_speech = 'non_speech'


class JobSegment(BaseModel):
  start: float = Field(description='Segment start on the original (pre-edit) timeline, in seconds')
  end: float = Field(description='Segment end on the original (pre-edit) timeline, in seconds')
  type: SegmentType = Field(description='speech / music / non_speech')


class JobCreateResponse(BaseModel):
  job_id: str
  status: JobStatus = JobStatus.queued
  cut_mode: CutMode


class JobStatusResponse(BaseModel):
  job_id: str
  status: JobStatus
  status_message: str | None = None
  progress_percent: int | None = None
  progress_current: int | None = None
  progress_total: int | None = None
  cut_mode: CutMode
  input_filename: str
  segments: list[JobSegment] | None = Field(
    default=None,
    description=(
      'Original-timeline speech/music/non_speech intervals in seconds. '
      'Present from segments_ready onward (including merging/exporting/completed). '
      'Null until detection finishes. May be an empty list for silence-only audio.'
    ),
  )
  source_duration: float | None = Field(
    default=None,
    description='Source audio duration in seconds (for waveform display). Null if unknown.',
  )
  unchanged: bool = False
  result_message: str | None = None
  error: str | None = None
  created_at: datetime
  updated_at: datetime
  completed_at: datetime | None = None
  expires_at: datetime | None = None


class HealthResponse(BaseModel):
  status: str = Field(default='ok')
