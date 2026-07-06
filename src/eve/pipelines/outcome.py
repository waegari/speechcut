from __future__ import annotations

from dataclasses import dataclass

NO_MUSIC_DETECTED_MESSAGE = '오디오 파일에서 음악 구간이 검출되지 않습니다'


@dataclass
class ProcessingOutcome:
  ok: bool
  bypassed: bool = False
  message: str | None = None
