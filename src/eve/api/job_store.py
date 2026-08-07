from __future__ import annotations

import json
import logging
import shutil
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from eve.api.schemas import CutMode, JobStatus
from eve.config.settings import settings
from eve.utils.timezone import now_kst, now_kst_iso, parse_kst

log = logging.getLogger(__name__)

SEGMENTS_FILENAME = 'segments.json'


class JobStore:
  def __init__(self, db_path: Path, data_dir: Path):
    self.db_path = db_path
    self.data_dir = data_dir
    self.db_path.parent.mkdir(parents=True, exist_ok=True)
    self.data_dir.mkdir(parents=True, exist_ok=True)
    self._init_db()

  def _connect(self) -> sqlite3.Connection:
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    return conn

  def _init_db(self) -> None:
    with self._connect() as conn:
      conn.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY,
          status TEXT NOT NULL,
          step TEXT NOT NULL,
          step_message TEXT,
          cut_mode TEXT NOT NULL,
          input_filename TEXT NOT NULL,
          input_path TEXT NOT NULL,
          output_path TEXT NOT NULL,
          error TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          completed_at TEXT
        )
      ''')
      self._migrate(conn)
      conn.commit()

  def _migrate(self, conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute('PRAGMA table_info(jobs)').fetchall()}
    if 'step' not in cols:
      conn.execute("ALTER TABLE jobs ADD COLUMN step TEXT NOT NULL DEFAULT 'queued'")
    if 'step_message' not in cols:
      conn.execute('ALTER TABLE jobs ADD COLUMN step_message TEXT')
    if 'result_message' not in cols:
      conn.execute('ALTER TABLE jobs ADD COLUMN result_message TEXT')
    if 'unchanged' not in cols:
      conn.execute('ALTER TABLE jobs ADD COLUMN unchanged INTEGER NOT NULL DEFAULT 0')
    if 'progress_current' not in cols:
      conn.execute('ALTER TABLE jobs ADD COLUMN progress_current INTEGER')
    if 'progress_total' not in cols:
      conn.execute('ALTER TABLE jobs ADD COLUMN progress_total INTEGER')

  def _now(self) -> str:
    return now_kst_iso()

  def segments_path(self, job_id: str) -> Path:
    return self.data_dir / job_id / SEGMENTS_FILENAME

  def load_segments_payload(self, job_id: str) -> dict[str, Any] | None:
    path = self.segments_path(job_id)
    if not path.exists():
      return None
    try:
      with path.open('r', encoding='utf-8') as fh:
        data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
      log.warning('failed to load segments for job %s: %s', job_id, exc)
      return None
    if not isinstance(data, dict):
      return None
    return data

  def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
    completed_at = parse_kst(row['completed_at']) if row['completed_at'] else None
    expires_at = None
    if completed_at and row['status'] in (JobStatus.completed.value, JobStatus.failed.value):
      expires_at = completed_at + timedelta(hours=settings.JOB_RETENTION_HOURS)
    unchanged = bool(row['unchanged']) if 'unchanged' in row.keys() else False
    result_message = row['result_message'] if 'result_message' in row.keys() else None
    status = self._normalize_status(row['status'], row['step'] if 'step' in row.keys() else None)
    segments_payload = self.load_segments_payload(row['id'])
    segments = None
    source_duration = None
    if segments_payload is not None:
      raw_segments = segments_payload.get('segments')
      segments = raw_segments if isinstance(raw_segments, list) else []
      duration = segments_payload.get('source_duration')
      source_duration = float(duration) if isinstance(duration, (int, float)) else None
    return {
      'job_id': row['id'],
      'status': status,
      'status_message': row['step_message'] if 'step_message' in row.keys() else None,
      'progress_current': row['progress_current'] if 'progress_current' in row.keys() else None,
      'progress_total': row['progress_total'] if 'progress_total' in row.keys() else None,
      'progress_percent': self._progress_percent(row),
      'cut_mode': CutMode(row['cut_mode']),
      'input_filename': row['input_filename'],
      'input_path': row['input_path'],
      'output_path': row['output_path'],
      'segments': segments,
      'source_duration': source_duration,
      'unchanged': unchanged,
      'result_message': result_message,
      'error': row['error'],
      'created_at': parse_kst(row['created_at']),
      'updated_at': parse_kst(row['updated_at']),
      'completed_at': completed_at,
      'expires_at': expires_at,
    }

  def _progress_percent(self, row: sqlite3.Row) -> int | None:
    if 'progress_current' not in row.keys() or 'progress_total' not in row.keys():
      return None
    current = row['progress_current']
    total = row['progress_total']
    if current is None or total is None or total <= 0:
      return None
    return min(100, max(0, int(current * 100 / total)))

  def _normalize_status(self, status_value: str, step_value: str | None = None) -> JobStatus:
    if status_value == 'processing':
      if step_value in {status.value for status in JobStatus}:
        return JobStatus(step_value)
      return JobStatus.loading
    return JobStatus(status_value)

  def create_job(self, cut_mode: CutMode, input_filename: str) -> tuple[str, Path, Path]:
    job_id = str(uuid.uuid4())
    job_dir = self.data_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(input_filename).suffix.lower()
    input_path = job_dir / f'input{suffix}'
    output_path = job_dir / f'output{suffix}'
    now = self._now()
    with self._connect() as conn:
      conn.execute(
        '''
        INSERT INTO jobs (
          id, status, step, step_message, cut_mode, input_filename, input_path, output_path,
          error, created_at, updated_at, completed_at
        ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, NULL, ?, ?, NULL)
        ''',
        (
          job_id,
          JobStatus.queued.value,
          JobStatus.queued.value,
          cut_mode.value,
          input_filename,
          str(input_path),
          str(output_path),
          now,
          now,
        ),
      )
      conn.commit()
    return job_id, input_path, output_path

  def get_job(self, job_id: str) -> dict[str, Any] | None:
    with self._connect() as conn:
      row = conn.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
    if row is None:
      return None
    return self._row_to_dict(row)

  def update_status(
    self,
    job_id: str,
    status: JobStatus,
    *,
    status_message: str | None = None,
    progress_current: int | None = None,
    progress_total: int | None = None,
    error: str | None = None,
    result_message: str | None = None,
    unchanged: bool = False,
  ) -> None:
    now = self._now()
    completed_at = now if status in (JobStatus.completed, JobStatus.failed) else None
    with self._connect() as conn:
      conn.execute(
        '''
        UPDATE jobs
        SET status = ?, step = ?, step_message = ?, progress_current = ?, progress_total = ?,
            error = ?, result_message = ?, unchanged = ?,
            updated_at = ?, completed_at = COALESCE(?, completed_at)
        WHERE id = ?
        ''',
        (
          status.value,
          status.value,
          status_message,
          progress_current,
          progress_total,
          error,
          result_message,
          int(unchanged),
          now,
          completed_at,
          job_id,
        ),
      )
      conn.commit()

  def reset_processing_to_queued(self) -> list[str]:
    active_statuses = (
      'processing',
      JobStatus.loading.value,
      JobStatus.detecting_speech.value,
      JobStatus.detecting_music.value,
      JobStatus.segments_ready.value,
      JobStatus.merging_segments.value,
      JobStatus.exporting.value,
    )
    with self._connect() as conn:
      placeholders = ', '.join('?' for _ in active_statuses)
      rows = conn.execute(
        f"SELECT id FROM jobs WHERE status IN ({placeholders})",
        active_statuses,
      ).fetchall()
      job_ids = [row['id'] for row in rows]
      if job_ids:
        now = self._now()
        where_placeholders = ', '.join('?' for _ in active_statuses)
        conn.execute(
          f'''
          UPDATE jobs
          SET status = ?, step = ?, step_message = NULL, progress_current = NULL, progress_total = NULL,
              error = NULL, result_message = NULL, unchanged = 0,
              updated_at = ?, completed_at = NULL
          WHERE status IN ({where_placeholders})
          ''',
          (JobStatus.queued.value, JobStatus.queued.value, now, *active_statuses),
        )
        conn.commit()
    return job_ids

  def list_queued_ids(self) -> list[str]:
    with self._connect() as conn:
      rows = conn.execute(
        "SELECT id FROM jobs WHERE status = ? ORDER BY created_at ASC",
        (JobStatus.queued.value,),
      ).fetchall()
    return [row['id'] for row in rows]

  def list_expired(self, cutoff: datetime) -> list[str]:
    with self._connect() as conn:
      rows = conn.execute(
        '''
        SELECT id, completed_at FROM jobs
        WHERE status IN (?, ?)
          AND completed_at IS NOT NULL
        ''',
        (JobStatus.completed.value, JobStatus.failed.value),
      ).fetchall()
    expired: list[str] = []
    for row in rows:
      completed_at = parse_kst(row['completed_at'])
      if completed_at < cutoff:
        expired.append(row['id'])
    return expired

  def delete_job(self, job_id: str) -> None:
    with self._connect() as conn:
      conn.execute('DELETE FROM jobs WHERE id = ?', (job_id,))
      conn.commit()
    job_dir = self.data_dir / job_id
    if job_dir.exists():
      shutil.rmtree(job_dir, ignore_errors=True)
