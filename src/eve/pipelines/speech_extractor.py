import json
import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Union

import numpy as np
import torch

from eve.audio.processor import AudioProcessor
from eve.config.settings import settings
from eve.pipelines.outcome import NO_MUSIC_DETECTED_MESSAGE, ProcessingOutcome
from eve.utils.editing_metadata import get_new_filename
from eve.utils.subproc import no_window_kwargs

log = logging.getLogger(__name__)

# Hold segments_ready long enough for typical status pollers to observe it.
SEGMENTS_READY_HOLD_SECONDS = 1.0

class SpeechExtractor(AudioProcessor):
  def __init__(
    self,
    path: Union[str, Path],
    vad_model,
    classification_model,
    sr: int = settings.PROCESSING_SR,
    channels: int = settings.PROCESSING_CH,
    
    output_sr: int = settings.OUTPUT_SR,
    output_br: str = settings.OUTPUT_BR,
    output_ch: int = settings.OUTPUT_CH,
    max_bytes: int = settings.MAX_AUDIO_BYTES,
    
    merge_gap_s: int = settings.MERGE_GAP_SECONDS,
    margin_s_head: int = settings.MARGIN_SECONDS_HEAD,
    margin_s_tail: int = settings.MARGIN_SECONDS_TAIL,
    fade_len_s: float = settings.FADE_SECONDS,
    min_speech_s: int = settings.MIN_SPEECH_S,
    class_prob_threshold: float = settings.CLASS_PROB_THRESHOLD,
    music_sensitivity: int = settings.MUSIC_SENSITIVITY,
    progress_callback: Callable[[str, str | None, int | None, int | None], None] | None = None,
    timing_callback: Callable[[str, float], None] | None = None,
  ):
    super().__init__(path, sr, channels, output_sr, output_br, output_ch, max_bytes)

    self.merge_gap_s = merge_gap_s
    self.margin_s_head = margin_s_head
    self.margin_s_tail = margin_s_tail
    self.fade_len_s = fade_len_s
    self.min_speech_s = min_speech_s
    self.class_prob_threshold = class_prob_threshold
    self.music_sensitivity = music_sensitivity

    self.vad_model = vad_model
    self.classification_model = classification_model
    self.progress_callback = progress_callback
    self.timing_callback = timing_callback

  def _report_progress(
    self,
    step: str,
    message: str | None = None,
    current: int | None = None,
    total: int | None = None,
  ) -> None:
    if self.progress_callback is not None:
      self.progress_callback(step, message, current, total)

  def _report_timing(self, name: str, elapsed_s: float) -> None:
    if self.timing_callback is not None:
      self.timing_callback(name, elapsed_s)
    if settings.ENABLE_TIMING_LOGS:
      log.info('timing %s=%.3fs', name, elapsed_s)

  def _measure(self, name: str, fn: Callable, *args, **kwargs):
    started = time.perf_counter()
    result = fn(*args, **kwargs)
    self._report_timing(name, time.perf_counter() - started)
    return result

  def _to_numpy_audio(self, audio_seg) -> np.ndarray:
    if isinstance(audio_seg, torch.Tensor):
      return audio_seg.detach().cpu().squeeze().numpy()
    return np.asarray(audio_seg, dtype=np.float32).squeeze()

  def _source_duration_s(self, wav) -> float:
    return round(len(wav) / self.processing_sr, 3)

  def _segments_json_path(self) -> Path:
    return self.source_audio_path.parent / 'segments.json'

  def _build_covering_segments(
    self,
    labeled_segs: list[dict],
    gap_type: str,
    wav,
  ) -> list[dict]:
    '''Build adjacent, non-overlapping segments covering [0, len(wav)] in seconds.

    If ``labeled_segs`` is empty (e.g. silence-only), returns an empty list.
    '''
    eof = len(wav)
    if eof <= 0:
      return []

    sorted_segs = sorted(
      (
        {
          'start': max(0, int(seg['start'])),
          'end': min(eof, int(seg['end'])),
          'type': seg['type'],
        }
        for seg in labeled_segs
        if int(seg['end']) > int(seg['start'])
      ),
      key=lambda s: s['start'],
    )
    # Silence-only / no detections: empty array is the documented contract.
    if not sorted_segs:
      return []

    merged_labeled: list[dict] = []
    for seg in sorted_segs:
      if not merged_labeled:
        merged_labeled.append(dict(seg))
        continue
      prev = merged_labeled[-1]
      if seg['start'] <= prev['end'] and seg['type'] == prev['type']:
        prev['end'] = max(prev['end'], seg['end'])
      elif seg['start'] < prev['end'] and seg['type'] != prev['type']:
        # Prefer the earlier label for overlap; truncate the later segment.
        seg = dict(seg)
        seg['start'] = prev['end']
        if seg['end'] <= seg['start']:
          continue
        merged_labeled.append(seg)
      else:
        merged_labeled.append(dict(seg))

    result: list[dict] = []
    cursor = 0
    for seg in merged_labeled:
      if seg['start'] > cursor:
        result.append({'start': cursor, 'end': seg['start'], 'type': gap_type})
      result.append({'start': seg['start'], 'end': seg['end'], 'type': seg['type']})
      cursor = max(cursor, seg['end'])
    if cursor < eof:
      result.append({'start': cursor, 'end': eof, 'type': gap_type})

    return [
      {
        'start': round(seg['start'] / self.processing_sr, 3),
        'end': round(seg['end'] / self.processing_sr, 3),
        'type': seg['type'],
      }
      for seg in result
      if seg['end'] > seg['start']
    ]

  def _publish_segments(
    self,
    wav,
    *,
    labeled_segs: list[dict],
    gap_type: str,
    message: str = 'Speech segments detected',
    hold: bool = True,
  ) -> list[dict]:
    '''Persist original-timeline segments and set status to segments_ready.'''
    segments = self._build_covering_segments(labeled_segs, gap_type, wav)
    payload = {
      'source_duration': self._source_duration_s(wav),
      'segments': segments,
    }
    path = self._segments_json_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as fh:
      json.dump(payload, fh, ensure_ascii=False)
    log.info('published %d segments to %s', len(segments), path)

    self._report_progress('segments_ready', message, 55, 100)
    if hold and SEGMENTS_READY_HOLD_SECONDS > 0:
      time.sleep(SEGMENTS_READY_HOLD_SECONDS)
    return segments

  def speech_music_separate(self, out_path=None) -> ProcessingOutcome:
    '''Aggressive mode: detect music segments, invert to keep speech-only parts.'''
    timestamps, wav = self.get_vad_timestamps()
    inverse = self.invert_timestamps(timestamps, wav)

    if len(inverse) == 0:
      log.info('no non-speech gaps; bypassing with unchanged output')
      merged_speech = self.merge_segments(timestamps) if timestamps else []
      labeled = [{'start': s['start'], 'end': s['end'], 'type': 'speech'} for s in merged_speech]
      if not labeled and len(wav) > 0:
        labeled = [{'start': 0, 'end': len(wav), 'type': 'speech'}]
      self._publish_segments(wav, labeled_segs=labeled, gap_type='speech')
      return self._bypass_unchanged(out_path, NO_MUSIC_DETECTED_MESSAGE)

    self._report_progress('detecting_music', 'Classifying segments', 0, len(inverse))
    music_seg = self._measure('music_classification', self.sound_classification, inverse, wav, 'Music')

    if not music_seg:
      log.info('no music segments detected; bypassing with unchanged output')
      merged_speech = self.merge_segments(timestamps) if timestamps else []
      labeled = [{'start': s['start'], 'end': s['end'], 'type': 'speech'} for s in merged_speech]
      self._publish_segments(wav, labeled_segs=labeled, gap_type='non_speech')
      return self._bypass_unchanged(out_path, NO_MUSIC_DETECTED_MESSAGE)

    self._report_progress('merging_segments', 'Preparing output segments')
    merged = self._measure('merge_segments', self.merge_segments, music_seg)

    if not merged:
      log.info('no music segments long enough after merge; bypassing with unchanged output')
      merged_speech = self.merge_segments(timestamps) if timestamps else []
      labeled = [{'start': s['start'], 'end': s['end'], 'type': 'speech'} for s in merged_speech]
      self._publish_segments(wav, labeled_segs=labeled, gap_type='non_speech')
      return self._bypass_unchanged(out_path, NO_MUSIC_DETECTED_MESSAGE)

    inversed_merged = self.invert_timestamps(merged, wav)

    if len(inversed_merged) == 0:
      log.debug('no speech only part in the audio file')
      return ProcessingOutcome(ok=False, message='no speech-only parts remain after music removal')

    # Publish AFTER merge: merged music + speech gaps on the original timeline.
    labeled = [{'start': s['start'], 'end': s['end'], 'type': 'music'} for s in merged]
    self._publish_segments(wav, labeled_segs=labeled, gap_type='speech')

    if self.get_duration(inversed_merged) < 10:
      log.debug('speech only audio is too short to export')
      return ProcessingOutcome(ok=False, message='speech-only audio is too short to export')

    margin_added = self._measure('add_margins', self.add_margins, inversed_merged, wav)

    self._report_progress('exporting', 'Exporting processed audio')
    self._measure('ffmpeg_export', self.ffmpeg_concat_fade, margin_added, out_path=out_path)
    return ProcessingOutcome(ok=True)

  def speech_voice_preserve(self, out_path=None) -> ProcessingOutcome:
    '''Conservative mode: VAD candidates → keep YAMNet Speech → fade connect.'''
    timestamps, wav = self.get_vad_timestamps()

    if len(timestamps) == 0:
      log.debug('no speech in the audio file')
      # Silence-only: empty segments array (documented contract).
      self._publish_segments(wav, labeled_segs=[], gap_type='non_speech', message='No speech segments')
      return ProcessingOutcome(ok=False, message='no speech segments found in the audio file')

    self._report_progress('detecting_speech', 'Verifying speech segments', 0, len(timestamps))

    speech_seg = self._measure(
      'speech_classification',
      self.sound_classification,
      timestamps,
      wav,
      'Speech',
    )

    if not speech_seg:
      log.debug('no speech confirmed by classifier')
      self._publish_segments(
        wav,
        labeled_segs=[],
        gap_type='non_speech',
        message='No speech segments confirmed',
      )
      return ProcessingOutcome(ok=False, message='no speech segments confirmed by classifier')

    self._report_progress('merging_segments', 'Preparing output segments')
    merged = self._measure('merge_segments', self.merge_segments, speech_seg)

    if len(merged) == 0:
      log.debug('no speech segments long enough to export')
      self._publish_segments(wav, labeled_segs=[], gap_type='non_speech', message='No speech segments')
      return ProcessingOutcome(ok=False, message='no speech segments long enough to export')

    # Publish AFTER merge so portal/ASR get coalesced speech intervals.
    labeled = [{'start': s['start'], 'end': s['end'], 'type': 'speech'} for s in merged]
    self._publish_segments(wav, labeled_segs=labeled, gap_type='non_speech')

    if self.get_duration(merged) < 10:
      log.debug('speech only audio is too short to export')
      return ProcessingOutcome(ok=False, message='speech-only audio is too short to export')

    margin_added = self._measure('add_margins', self.add_margins, merged, wav)
    self._report_progress('exporting', 'Exporting processed audio')
    self._measure('ffmpeg_export', self.ffmpeg_concat_fade, margin_added, out_path=out_path)

    return ProcessingOutcome(ok=True)

  def _bypass_unchanged(self, out_path, message: str) -> ProcessingOutcome:
    if out_path is None:
      out_path = get_new_filename(self.source_audio_path)
    shutil.copy2(self.source_audio_path, out_path)
    log.info('bypass: copied input to %s', out_path)
    return ProcessingOutcome(ok=True, bypassed=True, message=message)

  def get_vad_timestamps(self):
    '''
    Use VAD (Voice Activity Detection) model to detect speech segments in the audio
    Returns segments and the full waveform
    '''
    audio_path = str(self.source_audio_path)
    v_model = self.vad_model
    # Split long early stage for polling UX: load vs VAD (no new status values).
    self._report_progress('loading', 'Loading audio')
    wav = self._measure('audio_read', v_model.read_audio, audio_path, sampling_rate=self.processing_sr)
    self._report_progress('detecting_speech', 'Voice activity detecting')
    speech_timestamps = self._measure(
      'vad_inference',
      v_model.get_speech_timestamps,
      wav,
      sampling_rate=self.processing_sr,
    )
    return speech_timestamps, wav

  def invert_timestamps(self, timestamps:list, wav):
    log.debug(f'timestamps: {timestamps}')
    if not timestamps:
      log.debug('empty timestamps; no inverse segments')
      return []
    eof = len(wav)
    log.debug(f'eof: {eof}')
    temp = []

    for ts in timestamps:
      temp.append(ts['start'])
      temp.append(ts['end'])
    log.debug(f'temp: {temp}')
    if temp[0] == 0:
      temp.pop(0)
    else:
      temp.insert(0, 0)
    if temp[-1] == eof:
      temp.pop()
    else:
      temp.append(eof)

    inverse = [{'start': temp[i-1], 'end': t} for i, t in enumerate(temp) if i%2]
    log.debug(f'inverse: {inverse}')
    return inverse

  def sound_classification(self, timestamps, wav, target_label):
    c_model = self.classification_model
    class_names = c_model.class_names

    kept_seg = []
    end_of_last_kept_seg = 0
    total_segments = len(timestamps)
    progress_step = 'detecting_speech' if target_label == 'Speech' else 'detecting_music'
    progress_label = 'Classifying segments'

    for idx, seg in enumerate(timestamps, start=1):
      audio_seg = self._to_numpy_audio(wav[seg['start']:seg['end']])
      scores = c_model.predict(audio_seg)
      avg_probs = scores.mean(axis=0)

      # top4 indices
      top5_idx = np.argsort(avg_probs)[-4:][::-1]  # 내림차순 상위 4개
      top_labels = [class_names[i] for i in top5_idx]
      top_probs = [float(avg_probs[i]) for i in top5_idx]
      music_prob = float(avg_probs[class_names.index('Music')])

      log.debug(
        f'{seg["start"]/16000:8.2f}s-{seg["end"]/16000:8.2f}s  →  '
        f'{top_labels[0]:<20} {top_probs[0]:.3f} | '
        f'{top_labels[1]:<20} {top_probs[1]:.3f} | '
        f'{top_labels[2]:<20} {top_probs[2]:.3f} | '
        f'{top_labels[3]:<20} {top_probs[3]:.3f} | '
        f'Music_prob {music_prob:.3f}'
      )

      # Pre-refactor Speech path: down-weight Speech when Music also ranks high.
      if target_label == 'Speech' and top_labels[0] == 'Speech' and 'Music' in top_labels:
        top_probs[0] = max(top_probs[0] - music_prob * self.music_sensitivity, 0)

      top_label, top_prob = top_labels[0], top_probs[0]

      log.debug(f'{seg["start"]/16000:8.2f}s-{seg["end"]/16000:8.2f}s  →  {top_label:<20} {top_prob:.3f}')

      if top_label == target_label:
        if top_prob > self.class_prob_threshold:
          kept_seg.append(seg)
          end_of_last_kept_seg = seg['end']
        elif (
          end_of_last_kept_seg
          and (seg['start'] - end_of_last_kept_seg) < self.merge_gap_s * self.processing_sr
        ):
          kept_seg.append(seg)

      self._report_progress(
        progress_step,
        f'{progress_label} ({idx}/{total_segments})',
        idx,
        total_segments,
      )

    if not kept_seg:
      log.warning(f'no {target_label}. adjust class_prob_threshold.')

    return kept_seg

  def merge_segments(self, speech_seg):
    if not speech_seg:
      log.info('merged: 0 (empty input)')
      return []
    merged = []
    cur_start, cur_end = speech_seg[0]['start'], speech_seg[0]['end']
    for seg in speech_seg[1:]:
      if seg['start'] - cur_end < self.processing_sr * self.merge_gap_s:
        cur_end = max(cur_end, seg['end'])
      elif (cur_end - cur_start) > (self.min_speech_s * self.processing_sr):
        merged.append({'start': cur_start, 'end': cur_end})
        log.debug(f'APPENDED, start: {cur_start/self.processing_sr}, end: {cur_end/self.processing_sr}')
        cur_start, cur_end = seg['start'], seg['end']
      else:
        log.debug(f'TOO SHORT TO APPEND, start: {cur_start/self.processing_sr} end: {cur_end/self.processing_sr}')
        cur_start, cur_end = seg['start'], seg['end']
    if (cur_end - cur_start) > (self.min_speech_s * self.processing_sr):
      merged.append({'start': cur_start, 'end': cur_end})
      log.debug(f'APPENDED, start: {cur_start/self.processing_sr}, end: {cur_end/self.processing_sr}')
    else:
      log.debug(f'TOO SHORT TO APPEND, start: {cur_start/self.processing_sr} end: {cur_end/self.processing_sr}')
    log.info(f'merged: {len(merged)}')
    return merged
  
  def get_duration(self, segments):
    log.debug('get duration')
    dur = 0
    for seg in segments:
      start = int(seg['start'])
      end = int(seg['end'])
      dur =+ (end - start)
    log.info(f'dur: {dur}')
    return dur / self.processing_sr

  def add_margins(self, speech_seg, wav):
    log.info('add margins')
    final_seg = speech_seg.copy()
    margin_head = self.processing_sr * self.margin_s_head
    margin_tail = self.processing_sr * self.margin_s_tail
    min_margin = self.processing_sr * self.fade_len_s

    if final_seg[0]['start'] >= margin_head:
      final_seg[0]['start'] -= (margin_head)

    tail_gap = len(wav) - final_seg[-1]['end']
    if tail_gap >= margin_tail:
      final_seg[-1]['end'] = min(final_seg[-1]['end'] + margin_tail, len(wav))

    for i in range(len(speech_seg) - 1):
      log.debug(f'processing: gap #{i}')
      gap_start = final_seg[i]['end']
      gap_end = final_seg[i+1]['start']
      gap = gap_end - gap_start
      if gap >= self.processing_sr * self.merge_gap_s:
        log.debug(f'gap #{i} extend...')
        extended_gap_start = self.find_extended_silence_boundary(gap_start, direction='forward', min_silence_sec=self.margin_s_tail)
        extended_gap_end = self.find_extended_silence_boundary(gap_end, direction='backward', min_silence_sec=self.margin_s_head)
        if extended_gap_start:
          final_seg[i]['end'] = min(gap_start + min_margin, gap_end)
        else:
          final_seg[i]['end'] = min(gap_start + margin_tail, gap_end)
        if extended_gap_end:
          final_seg[i+1]['start'] = max(gap_end - min_margin, gap_start)
        else:
          final_seg[i+1]['start'] = max(gap_end - margin_head, gap_start)

    return final_seg

  def ffmpeg_concat_fade(self, segments, out_path=None, save_as_mp3=False):
    if not segments:
      raise ValueError('segments are empty')
    audio_path = self.source_audio_path

    if save_as_mp3:
      br = self.output_br
      ext = '.mp3'
    else:
      meta = self.get_audio_info()
      br = meta.get('bit_rate') or '1411000'
      ext = audio_path.suffix.lower()

    if out_path is None:
      out_path = get_new_filename(audio_path)
    log.info(f'out_path: {out_path}')

    filter_parts = []
    concat_inputs = []

    for i, seg in enumerate(segments):
      s = seg['start'] / self.processing_sr
      e = seg['end'] / self.processing_sr
      d = e - s

      fade = min(self.fade_len_s, d / 2)

      trim = (
        f'[0:a]atrim=start={s}:end={e},'
        f'asetpts=PTS-STARTPTS,'
        f'afade=t=in:st=0:d={fade},'
        f'afade=t=out:st={d-fade}:d={fade}'
        f'[a{i}];'
      )
      filter_parts.append(trim)
      concat_inputs.append(f'[a{i}]')

    filter_concat = ''.join(filter_parts) + ''.join(concat_inputs) \
            + f'concat=n={len(segments)}:v=0:a=1[outa]'

    cmd = [
      'ffmpeg', '-y', '-i', str(audio_path),
      '-filter_complex', filter_concat,
      '-map', '[outa]'
    ]

    if ext == '.mp3':
      cmd += ['-c:a', 'libmp3lame', '-b:a', br]
    elif ext == '.wav':
      cmd += ['-c:a', 'pcm_s16le']
    else:
      cmd += ['-c:a', 'flac']

    cmd.append(str(out_path))
    subprocess.run(cmd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   **no_window_kwargs())
    log.info(f'{out_path} created')
