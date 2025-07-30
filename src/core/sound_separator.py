import csv
import subprocess
import numpy as np
from silero_vad import load_silero_vad, read_audio, get_speech_timestamps
import tensorflow_hub as tfhub
import tensorflow as tf
from pathlib import Path
from typing import Union

from core.audio_processor import AudioProcessor
from settings.settings import settings

class SoundSeparator(AudioProcessor):
  def __init__(
    self,
    path: Union[str, Path],
    sr: int = settings.PROCESSING_SR,
    channels: int = settings.PROCESSING_CH,
    
    output_sr: int = settings.OUTPUT_SR,
    output_br: str = settings.OUTPUT_BR,
    output_ch: int = settings.OUTPUT_CH,
    max_bytes: int = settings.MAX_AUDIO_BYTES,
    
    merge_gap_s: int = settings.MERGE_GAP_SECONDS,
    margin_s: int = settings.MARGIN_SECONDS,
    fade_len_s: float = settings.FADE_SECONDS,
    min_speech_ms: int = settings.MIN_SPEECH_MS,
    speech_threshold: float = settings.SPEECH_THRESHOLD,
  ):
    super().__init__(path, sr, channels, output_sr, output_br, output_ch, max_bytes)

    self.merge_gap_s = merge_gap_s
    self.margin_s = margin_s
    self.fade_len_s = fade_len_s
    self.min_speech_ms = min_speech_ms
    self.speech_threshold = speech_threshold

    self.silero_vad = load_silero_vad()
    self.yamnet = tfhub.load('https://tfhub.dev/google/yamnet/1')

  def speech_music_separate(self):
    timestamps, wav = self.get_vad_timestamps()
    speech_seg = self.sound_classification(timestamps, wav)
    merged = self.merge_segments(speech_seg)
    merged = self.add_margins(merged, wav)
    self.ffmpeg_concat_fade(merged)

  def get_vad_timestamps(self):
    """
    Use VAD (Voice Activity Detection) model to detect speech segments in the audio
    Returns segments and the full waveform
    """
    audio_path = str(self.source_audio_path)
    model = self.silero_vad
    wav = read_audio(audio_path, sampling_rate=self.processing_sr)
    speech_timestamps = get_speech_timestamps(
      wav,
      model,
      sampling_rate=self.processing_sr,
    )
    return speech_timestamps, wav

  def sound_classification(self, timestamps, wav):
    yamnet = self.yamnet
    csv_path = yamnet.class_map_path().numpy().decode()

    with tf.io.gfile.GFile(csv_path, 'r') as f:
      reader = csv.reader(f)
      next(reader)
      class_names = [row[2] for row in reader]

    speech_seg = []

    for seg in timestamps:
      audio_seg = wav[seg['start']:seg['end']].squeeze().numpy()
      scores, _, _ = yamnet(audio_seg)
      scores_np = scores.numpy()
      avg_probs = scores_np.mean(axis=0)
      top_idx = int(avg_probs.argmax())
      top_label = class_names[top_idx]
      top_prob = float(avg_probs[top_idx])

      end_of_kept_seg = 0
      print(f"{seg['start']/16000:8.2f}s-{seg['end']/16000:8.2f}s  →  {top_label:<20} {top_prob:.3f}")
      if speech_seg:
        end_of_kept_seg = speech_seg[-1]['end']

      if top_label == 'Speech' and (
        top_prob > self.speech_threshold or
        (end_of_kept_seg and (seg['start'] - end_of_kept_seg) < self.merge_gap_s * self.processing_sr)
      ):
        speech_seg.append(seg)

    if not speech_seg:
      print('no speech. adjust speech_threshold.')

    return speech_seg

  def merge_segments(self, speech_seg):
    merged = []
    cur_start, cur_end = speech_seg[0]['start'], speech_seg[0]['end']
    for seg in speech_seg[1:]:
      if seg['start'] - cur_end < self.processing_sr * self.merge_gap_s:
        cur_end = max(cur_end, seg['end'])
      else:
        merged.append({'start': cur_start, 'end': cur_end})
        print(f'start: {cur_start/self.processing_sr}, end: {cur_end/self.processing_sr}')
        cur_start, cur_end = seg['start'], seg['end']
    merged.append({'start': cur_start, 'end': cur_end})
    print(f'start: {cur_start/self.processing_sr}, end: {cur_end/self.processing_sr}')
    print(f'merged: {len(merged)}')
    return merged

  def add_margins(self, speech_seg, wav):
    print('add margins')
    final_seg = speech_seg.copy()
    margin = self.processing_sr * self.margin_s
    min_margin = self.processing_sr * self.fade_len_s

    if final_seg[0]['start'] >= margin:
      final_seg[0]['start'] -= (margin // 2)

    tail_gap = len(wav) - final_seg[-1]['end']
    if tail_gap >= margin:
      final_seg[-1]['end'] = min(final_seg[-1]['end'] + margin, len(wav))

    for i in range(len(speech_seg) - 1):
      print(f'processing: gap #{i}')
      gap_start = final_seg[i]['end']
      gap_end = final_seg[i+1]['start']
      gap = gap_end - gap_start
      if gap >= self.processing_sr * self.merge_gap_s:
        print(f'gap #{i} extend...')
        extended_gap_start = self.find_extended_silence_boundary(gap_start, direction='backward', min_silence_sec=self.margin_s)
        extended_gap_end = self.find_extended_silence_boundary(gap_end, direction='forward', min_silence_sec=self.margin_s)

        if extended_gap_start:
          print('gapstart extended')
          final_seg[i]['end'] = min(gap_start + min_margin, gap_end)
        else:
          final_seg[i]['end'] = min(gap_start + margin, gap_end)
        if extended_gap_end:
          print('gapend extended')
          final_seg[i+1]['start'] = max(gap_end - min_margin, gap_start)
        else:
          final_seg[i+1]['start'] = max(gap_end - margin, gap_start)

    return final_seg

  def ffmpeg_concat_fade(self, segments, out_path=None, save_as_mp3=True):
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
      out_path = f'{audio_path.stem}_speech_only{ext}'

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
    subprocess.run(cmd, check=True)
    print(f'{out_path} created')
