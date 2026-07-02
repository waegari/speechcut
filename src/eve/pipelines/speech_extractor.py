import subprocess, logging
from pathlib import Path
from typing import Union
import numpy as np

from eve.audio.processor import AudioProcessor
from eve.config.settings import settings
from eve.utils.editing_metadata import get_new_filename
from eve.utils.subproc import no_window_kwargs

log = logging.getLogger(__name__)

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

  def speech_music_separate(self):
    timestamps, wav = self.get_vad_timestamps()
    inverse = self.invert_timestamps(timestamps, wav)
    if len(inverse) == 0:
      log.debug('no music in the audio file')
      return False
    music_seg = self.sound_classification(inverse, wav, 'Music')
    merged = self.merge_segments(music_seg)
    inversed_merged = self.invert_timestamps(merged, wav)
    if len(inversed_merged) == 0:
      log.debug('no speech only part in the audio file')
      return False
    if self.get_duration(inversed_merged) < 10:
      log.debug('speech only audio is too short to export')
      return False
    margin_added = self.add_margins(inversed_merged, wav)
    self.ffmpeg_concat_fade(margin_added)
    return True

  def get_vad_timestamps(self):
    '''
    Use VAD (Voice Activity Detection) model to detect speech segments in the audio
    Returns segments and the full waveform
    '''
    audio_path = str(self.source_audio_path)
    v_model = self.vad_model
    wav = v_model.read_audio(audio_path, sampling_rate=self.processing_sr)
    speech_timestamps = v_model.get_speech_timestamps(
      wav,
      sampling_rate=self.processing_sr,
    )
    return speech_timestamps, wav

  def invert_timestamps(self, timestamps:list, wav):
    log.debug(f'timestamps: {timestamps}')
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

    speech_seg = []

    for seg in timestamps:
      audio_seg = wav[seg['start']:seg['end']].squeeze().numpy()
      scores = c_model.predict(audio_seg)      
      avg_probs = scores.mean(axis=0)

      # top4 indices
      top5_idx = np.argsort(avg_probs)[-4:][::-1]  # 내림차순 상위 4개
      top_labels = [class_names[i] for i in top5_idx]
      top_probs = [float(avg_probs[i]) for i in top5_idx]
      music_prob = float(avg_probs[class_names.index('Music')])
      speech_prob = float(avg_probs[class_names.index('Speech')])

      log.debug(
        f'{seg["start"]/16000:8.2f}s-{seg["end"]/16000:8.2f}s  →  '
        f'{top_labels[0]:<20} {top_probs[0]:.3f} | '
        f'{top_labels[1]:<20} {top_probs[1]:.3f} | '
        f'{top_labels[2]:<20} {top_probs[2]:.3f} | '
        f'{top_labels[3]:<20} {top_probs[3]:.3f} | '
        f'Music_prob {music_prob:.3f}'
      )

      # top_idx = int(avg_probs.argmax())
      # top_label = class_names[top_idx]
      # top_prob = float(avg_probs[top_idx])

      top_label, top_prob = top_labels[0], top_probs[0]

      log.debug(f'{seg["start"]/16000:8.2f}s-{seg["end"]/16000:8.2f}s  →  {top_label:<20} {top_prob:.3f}')

      end_of_last_speech_seg = 0 # end of last speech segment where prob > thershold

      if top_label == target_label:
        if top_prob > self.class_prob_threshold:
          speech_seg.append(seg)
          end_of_last_speech_seg = seg['end']
        elif (end_of_last_speech_seg and (seg['start'] - end_of_last_speech_seg) < self.merge_gap_s * self.processing_sr):
          speech_seg.append(seg)

    if not speech_seg:
      log.warning(f'no {target_label}. adjust class_prob_threshold.')

    return speech_seg

  def merge_segments(self, speech_seg):
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

    cmd.append(out_path)
    subprocess.run(cmd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   **no_window_kwargs())
    log.info(f'{out_path} created')
