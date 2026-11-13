#!/usr/bin/env python3
"""Actual admission and binary/split/host-checksum corruptions, no hardware."""
import copy,hashlib,json,struct,tempfile
from pathlib import Path
from prepare_overlap_completion_v1 import admit,merge
from overlap_capture_common_v1 import inspect,host_cases,check_corpus,ELF,PARENT_READY,Elf,validator
from analyze_overlap_completion_v1 import training_rows,analyze
from batch_runner import digest,parse_regions
ROOT=Path(__file__).resolve().parents[1]
def main():
 out=ROOT/'build/overlap-managed-tools-controls-v1';out.mkdir();packet=ROOT/'build/overlap-completion-console-qualification-v2';ready,c,cases,elf,ids=admit(packet,PARENT_READY);layout=json.loads((Path(ready['build'])/'readback-layout.json').read_text());raw=elf.read_bytes();controls=[]
 def reject(name,fn):
  try:fn()
  except(ValueError,TypeError,KeyError,IndexError,struct.error):controls.append(dict(name=name,rejected=True));return
  raise ValueError('Accepted mutation '+name)
 reject('wrong-ready',lambda:admit(packet,'0'*64));e=Elf(raw);table=e.syms['cases'][0]
 for name,offset in [('case-hart',0),('case-dtype',8),('case-shape',16),('case-count',24),('case-trial',40),('kernel-pointer',48)]:
  changed=bytearray(raw);changed[e.file_offset(table+offset,1)]^=1;reject(name,lambda:inspect(bytes(changed),c,layout))
 changed=bytearray(raw);changed[e.file_offset(e.syms['kernel_0_16_0'][0],1)]^=1;reject('actual-MMopcode',lambda:inspect(bytes(changed),c,layout))
 changed=bytearray(raw);changed[e.file_offset(e.syms['overlap_done'][0],1)]=0;reject('completion-sentinel',lambda:inspect(bytes(changed),c,layout))
 bad=copy.deepcopy(c);bad['cases'][0]['hart']=False;reject('boolean-hart',lambda:check_corpus(bad));bad=copy.deepcopy(c);bad['cases'].pop();reject('missing-case',lambda:check_corpus(bad))
 bad=copy.deepcopy(layout);bad['record_stride']=64;reject('record-ABI',lambda:inspect(raw,c,bad))
 text=(ROOT/'build/overlap-completion-console-functional-seed0-v1/stdout').read_text();assert validator().validate(text,c)['independent_numeric_elements']==19872
 bad=copy.deepcopy(cases);bad[0]['expected_checksums_by_hart'][0]+=1;reject('host-independent-checksum',lambda:parse_regions(text,bad,ELF,'0'*64,True,True))
 simulated=[]
 for case,spec in zip(c['cases'],cases):simulated.append(dict(hart=case['hart'],edge=case['edge'],internal_split=spec['internal_split'],start_cycle=1,issue_end_cycle=2,fence_end_cycle=3,end_cycle=4))
 train=training_rows(simulated);assert len(train)==114 and all(not any(k in r for k in['start_cycle','issue_end_cycle','fence_end_cycle','end_cycle'])for r in train)
 next(r for r in simulated if r['internal_split']!='train')['internal_split']='train';reject('reserved-label-inTRAIN',lambda:training_rows(simulated))
 values={};merge(values,{'firesim/overlap_capture_common_v1.py':digest(ROOT/'firesim/overlap_capture_common_v1.py')});assert all(Path(n).is_absolute()for n in values);reject('source-conflicting-digest',lambda:merge(values,{'firesim/overlap_capture_common_v1.py':'0'*64}))
 fake=out/'missing-capture-job';fake.mkdir();(fake/'run.json').write_text('{}\n');assert analyze(fake,out/'missing-capture-analysis')==1;controls.append(dict(name='missing-capture',rejected=True))
 paths=[Path(__file__).resolve(),ROOT/'firesim/prepare_overlap_completion_v1.py',ROOT/'firesim/analyze_overlap_completion_v1.py',ROOT/'firesim/overlap_capture_common_v1.py',packet/'ready.json',ROOT/'calibration/overlap-mechanism-v1/split.json'];r=dict(schema='iris.source_overlap_managed_controls.v1',status='passed',actual_positive_admission=True,regions=168,numeric_elements=19872,negative_controls=controls,TRAIN_absolute_timestamps_redacted=True,hardware_contacted=False,input_sha256={str(p):digest(p)for p in paths});(out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(status='passed',controls=len(controls),report_sha256=digest(out/'report.json'))))
if __name__=='__main__':main()
