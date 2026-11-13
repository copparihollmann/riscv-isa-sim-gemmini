#!/usr/bin/env python3
import json,shutil,tempfile
from pathlib import Path
from batch_runner import digest
from prepare_pow2_memory import admit,merge
from analyze_pow2_memory import analyze
from check_pow2_memory_clint import inspect_clint_window
ROOT=Path(__file__).resolve().parents[1]
def main():
 out=ROOT/'build/pow2-memory-managed-tools-v3';out.mkdir(exist_ok=False);b=ROOT/'build/pow2-memory-single-reviewed-v1';ready,corpus,cases,elf,ids=admit(b,digest(b/'ready.json'));assert len(cases)==234 and sum(len(c['active_harts'])for c in cases)==234;controls=[]
 def reject(name,edit):
  with tempfile.TemporaryDirectory(dir=out)as d:
   t=Path(d)
   for f in['ready.json','parent-ready.json','build.json','qualification.json','corpus.json','layout.json','review.json','host-cases.json','footprints.elf']:shutil.copyfile(b/f,t/f)
   r=json.loads((t/'ready.json').read_text());edit(t,r);(t/'ready.json').write_text(json.dumps(r)+'\n')
   try:admit(t,digest(t/'ready.json'))
   except(ValueError,KeyError,TypeError):controls.append(dict(name=name,rejected=True));return
   raise ValueError('Accepted '+name)
 reject('234flattenedcasesnot117cohorts',lambda t,r:r.update(declared_cases=117))
 reject('80Brecordrequired',lambda t,r:r.update(record_bytes=64))
 reject('globalheldoutrole',lambda t,r:r.update(global_heldout=True))
 reject('samplesoutsideROI',lambda t,r:r.update(CLINT_samples_outside_CSR_ROI=False))
 def qbad(t,r):
  p=t/'qualification.json';q=json.loads(p.read_text());q['CLINT_windows_verified']=0;p.write_text(json.dumps(q)+'\n');r['qualification_sha256']=digest(p)
 reject('actualCLINTqualificationrequired',qbad)
 def hostbad(t,r):
  p=t/'host-cases.json';x=json.loads(p.read_text());p.write_text(json.dumps(x[::2])+'\n');r['host_cases_sha256']=digest(p)
 reject('missingsecondpass',hostbad)
 try:admit(b,'0'*64)
 except ValueError:controls.append(dict(name='wrongreadyhash',rejected=True))
 else:raise ValueError('Wronghashaccepted')
 raw=bytearray(elf.read_bytes());from pow2_memory_review import Elf
 e=Elf(bytes(raw));off=e.file_offset(0x800006b4,4);raw[off]^=1
 try:inspect_clint_window(bytes(raw))
 except ValueError:controls.append(dict(name='actualCLINTloadopcodechanged',rejected=True))
 else:raise ValueError('ChangedCLINTopcodeaccepted')
 values={};merge(values,{'firesim/check_pow2_memory_clint.py':digest(ROOT/'firesim/check_pow2_memory_clint.py')});assert all(Path(p).is_absolute()for p in values)
 try:merge(values,{'firesim/check_pow2_memory_clint.py':'0'*64})
 except ValueError:controls.append(dict(name='sourceidentityconflict',rejected=True))
 else:raise ValueError('Sourceconflictaccepted')
 fake=out/'missing-capture-job';fake.mkdir();(fake/'run.json').write_text('{}\n');assert analyze(fake,out/'missing-capture-analysis')==1;controls.append(dict(name='absentmanagedcapture',rejected=True))
 from analyze_pow2_memory import training_rows
 from pow2_memory_review import validator
 simulated=validator().canonical()
 for row in simulated:row.update(internal_split='reserved_holdout'if row['footprint_bytes']in(4096,65536,524288)else'train',start_cycle=100,end_cycle=200,mtime_before=1,mtime_after=2,cycles=100)
 train=training_rows(simulated);assert len(train)==180 and all(not any(k in row for k in ['start_cycle','end_cycle','mtime_before','mtime_after'])for row in train)
 simulated[12]['internal_split']='train'
 try:training_rows(simulated)
 except ValueError:controls.append(dict(name='reservedlabelTRAINleak',rejected=True))
 else:raise ValueError('Reserved timing admitted')
 paths=[Path(__file__),ROOT/'firesim/prepare_pow2_memory.py',ROOT/'firesim/analyze_pow2_memory.py',ROOT/'firesim/pow2_memory_review.py',ROOT/'firesim/check_pow2_memory_clint.py'];r=dict(schema='iris.memory_footprint_mtime_managed_tools_controls.v1',**{'pass':True},actual_positive_admission=True,cohorts=117,declared_cases=234,regions=234,negative_controls=controls,hardware_contacted=False,input_sha256={str(p):digest(p)for p in paths});(out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(**{'pass':True},controls=len(controls),report_sha256=digest(out/'report.json'))))
if __name__=='__main__':main()
