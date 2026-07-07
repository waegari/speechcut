from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo('Asia/Seoul')


def now_kst() -> datetime:
  return datetime.now(KST)


def now_kst_iso() -> str:
  return now_kst().isoformat()


def parse_kst(value: str) -> datetime:
  dt = datetime.fromisoformat(value)
  if dt.tzinfo is None:
    # Legacy records were stored as UTC without a timezone suffix.
    dt = dt.replace(tzinfo=ZoneInfo('UTC')).astimezone(KST)
  else:
    dt = dt.astimezone(KST)
  return dt
