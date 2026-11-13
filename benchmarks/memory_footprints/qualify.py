#!/usr/bin/env python3
"""Freeze real schedule and omission controls plus independently checked geometry."""
import argparse,copy,hashlib,json
from pathlib import Path
from build import ROOT,sha
from validate import validate,validate_corpus

def qualify(build,negative):
 c=json.loads((build/'corpus.json').read_text());b=json.loads((build/'build.json').read_text());validate_corpus(c);ids=dict(b['input_sha256']);ids.update({str(p):sha(p)for p in [Path(__file__).resolve(),Path(__file__).with_name('run.py'),build/'build.json',build/'footprints.elf']});normal=[]
 for seed in(0,17):
  d=build/('seed%d'%seed);r=json.loads((d/'run.json').read_text());assert r['pass']is True and r['exit_status']==0 and r['timed_out']is False and r['normal_guest_exit_verified']is True and r['seed']==seed and r['elf_sha256']==b['elf_sha256'];text=(d/'stdout').read_text();validate(text,c);assert sha(d/'stdout')==r['stdout_sha256']and sha(d/'stderr')==r['stderr_sha256'];ids.update(r['input_sha256']);ids.update({str(p):sha(p)for p in[d/'run.json',d/'stdout',d/'stderr']});normal.append(dict(seed=seed,report=str(d/'run.json'),report_sha256=sha(d/'run.json'),host_seconds=r['host_seconds']))
 neg=json.loads((negative/'seed0/run.json').read_text());assert neg['pass']is True and neg['expect_negative']is True and neg['exit_status']!=0 and neg['timed_out']is False and neg['proof']==dict(actual_omitted_kernel_detected=True,failed_regions=360);ids.update(neg['input_sha256']);ids.update({str(p):sha(p)for p in[negative/'seed0/run.json',negative/'seed0/stdout',negative/'seed0/stderr']})
 controls=[]
 def reject(name,action):
  try:action()
  except(ValueError,AssertionError,KeyError,TypeError):controls.append(dict(name=name,rejected=True))
  else:raise ValueError('Corruption accepted '+name)
 rows=[json.loads(l[len('IRIS_REGION '):])for l in text.splitlines()if l.startswith('IRIS_REGION ')]
 def wire(rows,terminal=None):return '\n'.join('IRIS_REGION '+json.dumps(r)for r in rows)+'\nIRIS_BATCH_DONE '+json.dumps(terminal or dict(failed=0,cases=105,regions=360,trials=3))+'\n'
 for key,value in[('hart',True),('checksum',0),('expected_checksum',0),('pass_index',1),('body_loads',1),('requested_bytes',True),('instret_delta',True),('end_cycle',0),('trial_id',17),('parent_case_id','wrong'),('footprint_bytes',1)]:
  changed=copy.deepcopy(rows);changed[0][key]=value;reject(key,lambda:validate(wire(changed),c))
 reject('missing-row',lambda:validate(wire(rows[1:]),c));reject('duplicate-row',lambda:validate(wire(rows+rows[:1]),c));reject('terminal-bool',lambda:validate(wire(rows,dict(failed=False,cases=105,regions=360,trials=3)),c))
 for key,value in[('nodes',16),('mask',True),('internal_split','bad'),('expected_checksums_by_hart',[0,0,0])]:
  changed=copy.deepcopy(c);changed['cases'][0][key]=value;reject('corpus-'+key,lambda:validate_corpus(changed))
 nodes_checked=0
 for size in(2048,16384,131072,1048576,4194304):
  n=size//64
  for trial in range(3):
   for h in range(3):
    values=[]
    for i in range(n):
     x=i^(i>>3);x=(x*13)&(n-1);x=x^(x>>5);values.append((x+17*trial+7*h)&(n-1))
    assert len(set(values))==n and set(values)==set(range(n));assert values[0]==(17*trial+7*h)%n;nodes_checked+=n
 for p,h in ids.items():assert sha(p)==h,p
 q=dict(schema='iris.memory_footprint_qualification.v1',**{'pass':True},elf_sha256=b['elf_sha256'],corpus_sha256=sha(build/'corpus.json'),functional=normal,actual_omitted_kernel=dict(report=str(negative/'seed0/run.json'),report_sha256=sha(negative/'seed0/run.json'),failed_regions=360),negative_controls=controls,permutation_bijections_checked=45,permutation_indices_checked=nodes_checked,exact_four_instruction_body_verified=b['exact_loop']is not None,normal_guest_exit_verified=True,input_sha256=ids,hardware_contacted=False,physical_hit_or_miss_assertion=False,source_image_association_verified=False)
 (build/'qualification.json').write_text(json.dumps(q,indent=2)+'\n');ready=dict(schema='iris.memory_footprint_ready.v1',status='ready_for_root_managed_preparation',source_frozen=True,required_cases=105,required_regions=360,trials=3,passes=2,fitting_only=True,global_heldout=False,elf=str(build/'footprints.elf'),elf_sha256=b['elf_sha256'],corpus_sha256=sha(build/'corpus.json'),build_sha256=sha(build/'build.json'),qualification_sha256=sha(build/'qualification.json'),layout_sha256=sha(build/'layout.json'),source_image_association_verified=False);(build/'ready.json').write_text(json.dumps(ready,indent=2)+'\n');print(json.dumps(dict(pass_=True,ready_sha256=sha(build/'ready.json'),permutation_indices_checked=nodes_checked,negative_controls=len(controls))))
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--negative-build',type=Path,required=True);a=p.parse_args();qualify(a.build.resolve(),a.negative_build.resolve())
