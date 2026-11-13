#!/usr/bin/env python3
"""Finite actual-admission, source mutation and reserved-label export controls."""
import copy,json,shutil,tempfile
from pathlib import Path
from batch_runner import digest
from prepare_pow2_matrix import admit,merge
from analyze_pow2_matrix import training_rows,analyze
from check_pow2_matrix_clint import inspect_clint_window
from pow2_matrix_review import Elf
ROOT=Path(__file__).resolve().parents[1]
def main():
 out=ROOT/'build/pow2-matrix-managed-tools-v1';out.mkdir(exist_ok=False);b=ROOT/'build/pow2-matrix-single-v2';ready,c,cases,elf,ids=admit(b,digest(b/'ready.json'));assert len(cases)==132;controls=[]
 def reject(name,edit):
  with tempfile.TemporaryDirectory(dir=out)as d:
   t=Path(d)
   for n in ['ready.json','build.json','qualification.json','corpus.json','golden-words.bin','host-cases.json','matrix.elf']:shutil.copyfile(b/n,t/n)
   r=json.loads((t/'ready.json').read_text());edit(t,r);(t/'ready.json').write_text(json.dumps(r)+'\n')
   try:admit(t,digest(t/'ready.json'))
   except(ValueError,TypeError,KeyError):controls.append(dict(name=name,rejected=True));return
   raise ValueError('Accepted '+name)
 reject('source-not-frozen',lambda t,r:r.update(source_frozen=False));reject('reserved-label-policy',lambda t,r:r.update(reserved_timing_labels_root_only=False));reject('wrong-geometry',lambda t,r:r.update(regions=131))
 def bad(t,r):
  p=t/'golden-words.bin';s=bytearray(p.read_bytes());s[0]^=1;p.write_bytes(s);r['artifact_sha256']['golden-words.bin']=digest(p)
 reject('rebound-golden-corruption',bad)
 def wrong(t,r):
  p=t/'host-cases.json';p.write_text('[]\n');r['artifact_sha256']['host-cases.json']=digest(p)
 reject('missing-host-case',wrong)
 raw=bytearray(elf.read_bytes());e=Elf(bytes(raw));raw[e.file_offset(0x80000b56,4)]^=1
 try:inspect_clint_window(bytes(raw))
 except ValueError:controls.append(dict(name='actualCLINTloadmutation',rejected=True))
 else:raise ValueError('ChangedCLINTloadaccepted')
 simulated=[]
 for x in c['cases']:simulated.append(dict(x,start_cycle=1,end_cycle=2,mtime_before=3,mtime_after=4))
 train=training_rows(simulated);assert len(train)==96 and all(not any(k in row for k in['start_cycle','end_cycle','mtime_before','mtime_after'])for row in train)
 next(x for x in simulated if x['internal_split']=='reserved_holdout')['internal_split']='train'
 try:training_rows(simulated)
 except ValueError:controls.append(dict(name='reservedTRAINleak',rejected=True))
 else:raise ValueError('ReservedshapeadmittedTRAIN')
 val={};merge(val,{'firesim/check_pow2_matrix_clint.py':digest(ROOT/'firesim/check_pow2_matrix_clint.py')});assert all(Path(x).is_absolute()for x in val)
 try:merge(val,{'firesim/check_pow2_matrix_clint.py':'0'*64})
 except ValueError:controls.append(dict(name='sourcecollision',rejected=True))
 else:raise ValueError('Sourcecollisionaccepted')
 fake=out/'missing-capture';fake.mkdir();(fake/'run.json').write_text('{}\n');assert analyze(fake,out/'missing-capture-analysis')==1;controls.append(dict(name='missing-managed-capture',rejected=True))
 paths=[Path(__file__).resolve(),ROOT/'firesim/prepare_pow2_matrix.py',ROOT/'firesim/analyze_pow2_matrix.py',ROOT/'firesim/check_pow2_matrix_clint.py',ROOT/'firesim/pow2_matrix_review.py',b/'ready.json'];r=dict(schema='iris.pow2_matrix_managed_tools_controls.v1',status='passed',actual_positive_admission=True,regions=132,negative_controls=controls,TRAIN_timestamps_removed=True,hardware_contacted=False,input_sha256={str(p):digest(p)for p in paths});(out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(status='passed',controls=len(controls),report_sha256=digest(out/'report.json'))))
if __name__=='__main__':main()
