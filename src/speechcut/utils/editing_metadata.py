from __future__ import annotations
from pathlib import Path
import xml.etree.ElementTree as ET
import logging

from speechcut.config.settings import settings 

log = logging.getLogger(__name__)

def get_new_filename(old: Path) -> Path:
  parts  = old.stem.split('_')
  end_ts, pname, brd, pid = parts[:4]    # ['20250728…', '김현정의뉴스쇼(1)', '071002', '12345']
  pid = int(pid) % 10_000_000 # mod
  new_pid  = str(pid + 10_000_000)
  new_pname = f'{pname}(다시듣기)'
  new_stem = '_'.join([end_ts, new_pname, brd, new_pid])
  return old.with_stem(new_stem)

def add_processed_program_to_xml(audio_path: str | Path) -> None:
  '''
  original_path 예) yyyyMMddhhmmss_programname_hhmmss_pid.wav
  같은 날짜(<Metadata><date>) 블록 맨 끝에
  다시듣기 항목을 'program'으로 추가

  <program>
    <programname>김현정의뉴스쇼(1)</programname>
    <programid>12345</programid>
    <brdtime>071002</brdtime>
    <filename>
    <filepath>20250801075648_김현정의뉴스쇼(1)_071002_12345.wav</filepath>
    </filename>
  </program>
  <program>
    <programname>김현정의뉴스쇼(1)(다시듣기)</programname>
    <programid>10012345</programid>
    <brdtime>071002</brdtime>
    <filename>
    <filepath>20250801075648_김현정의뉴스쇼(1)(다시듣기)_071002_10012345.wav</filepath>
    </filename>
  </program>

  '''
  if isinstance(audio_path, str):
    audio_path = Path(audio_path)
  xml_path: Path = audio_path.with_name(settings.XML_FILENAME.name)
  
  name = audio_path.stem
  date   = name[:8]
  parts  = name.split('_')
  end_ts, pname, brd, pid = parts[:4]    # ['20250728…', '김현정의뉴스쇼(1)', '071002', '12345']
  pid = int(pid) % 10_000_000 # mod
  new_pid  = str(pid + 10_000_000)
  new_pname = f'{pname}(다시듣기)'
  new_file  = f'{end_ts}_{new_pname}_{brd}_{new_pid}.wav'

  tree = ET.parse(xml_path)
  root = tree.getroot()

  meta = next((m for m in root.findall('Metadata') if m.findtext('date') == date), None)
  if meta is None:
    log.warning('원본 프로그램 메타데이터(date: %s)가 없습니다.', date)
    return

  for p in meta.findall('program'):
    if p.findtext('programid') == new_pid and p.findtext('brdtime') == brd and p.findtext('speech_only_done') == '1':
      log.warning('이미 처리된 파일입니다: %s', new_file)
      return

  # 원본 program
  src_prog = next((p for p in meta.findall('program')
           if p.findtext('programid') == str(pid) and p.findtext('brdtime') == brd), None)
  if src_prog is None:
    log.warning('원본 프로그램 메타데이터(pid: %s, brdtime: %s)가 없습니다.', pid, brd)
    return

  prog = ET.SubElement(meta, 'program')

  if src_prog is not None:
    # 원본 태그 복제
    for child in src_prog:
      print(str(child.text))
      prog.append(ET.fromstring(ET.tostring(child)))

  # 수정
  prog.find('programname').text = new_pname
  prog.find('programid').text   = new_pid
  prog.find('filename/filepath').text = new_file

  # 처리 완료 태그 추가
  ET.SubElement(prog, 'speech_only_done').text = '1'

  # 저장
  ET.indent(tree, space='  ', level=0)   # 들여쓰기
  tree.write(xml_path, encoding='utf-8', xml_declaration=True)
  log.info('XML 업데이트 완료: %s → %s', pid, new_pid)