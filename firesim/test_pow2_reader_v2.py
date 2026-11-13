#!/usr/bin/env python3
"""Synthetic inventory/preparation corruption controls; no hardware archives."""
import hashlib,io,json,tarfile,tempfile
from pathlib import Path
from analyze_pow2_packets_v2 import read_archive
ROOT=Path(__file__).resolve().parents[1]
def hb(raw):return hashlib.sha256(raw).hexdigest()
def packet(where,role,wrong=False):
 b=ROOT/('runs/fpga-pow2-memory-single-v1-001'if role=='memory'else'runs/fpga-pow2-matrix-single-v1-001');m=json.loads((b/'run.json').read_text());names=['ready.json','corpus.json','qualification.json','build.json']+(['layout.json','review.json']if role=='memory'else['golden-words.bin']);files={'job/'+n:(b/n).read_bytes()for n in names};m['prepared_file_sha256']={n:hb(files['job/'+n])for n in names}
 if wrong:m['prepared_file_sha256']['qualification.json']='0'*64
 files['job/run.json']=json.dumps(m).encode();inventory=json.dumps(dict(files=[dict(path=n,sha256=hb(raw),bytes=len(raw))for n,raw in files.items()])).encode();files['capture-manifest.json']=inventory
 with tarfile.open(where,'w:gz')as t:
  for name,raw in files.items():info=tarfile.TarInfo(name);info.size=len(raw);t.addfile(info,io.BytesIO(raw))
 return hb(files['job/run.json'])
def main():
 out=ROOT/'build/pow2-postcapture-reader-controls-v2';out.mkdir();controls=[]
 for role in('memory','matrix'):
  path=out/(role+'.tar.gz');expected=packet(path,role);data,ids=read_archive(path,expected);assert'job/ready.json'in data
  bad=out/(role+'-bad.tar.gz');expected=packet(bad,role,True)
  try:read_archive(bad,expected)
  except ValueError:controls.append(dict(name=role+'-forged-prepared-qualification',rejected=True))
  else:raise ValueError('Forgedpreparedqualificationaccepted')
  try:read_archive(path,'0'*64)
  except ValueError:controls.append(dict(name=role+'-wrong-captured-manifest',rejected=True))
  else:raise ValueError('Wrongmanifestaccepted')
 r=dict(schema='iris.pow2_postcapture_reader_controls.v2',status='passed',both_actual_prelaunch_admission_packets_inventory_roundtrip_passed=True,negative_controls=controls,synthetic_archive_only=True,hardware_contacted=False,input_sha256={str(p):hb(p.read_bytes())for p in[Path(__file__).resolve(),ROOT/'firesim/analyze_pow2_packets_v2.py']});(out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(status='passed',controls=len(controls),report_sha256=hb((out/'report.json').read_bytes()))))
if __name__=='__main__':main()
