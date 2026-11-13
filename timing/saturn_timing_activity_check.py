#!/usr/bin/env python3
"""Finite actual RTL activity proof, source shape checks and negative witnesses."""
import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path
from saturn_timing_check import mailbox

R=Path(__file__).resolve().parents[1]
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as stream:
  for b in iter(lambda:stream.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--sdk',type=Path,required=True);p.add_argument('--replay',type=Path,required=True);p.add_argument('--captures',type=Path,required=True);p.add_argument('--schema',type=Path,required=True);p.add_argument('--contract',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copy2(Path(__file__),out/'checker.py')
 sdk=a.sdk.resolve();replay=a.replay.resolve();captures=a.captures.resolve();schema_path=a.schema.resolve();contract_path=a.contract.resolve();schema=json.loads(schema_path.read_text());projection_schema=json.loads((replay/'projection-schema.json').read_text());names=projection_schema['record_layout'][4:]
 inputs=[Path(__file__),R/'timing/saturn_timing_check.py',sdk/'build.json',sdk/'sdk/libiris_saturn_timing.a',replay/'build.json',replay/'replay',replay/'projection-schema.json',schema_path,contract_path]
 positives=[];mailboxes={}
 for case in ['vme','rvv','fpcomp','shared-fpu']:
  run=captures/case;receipt=json.loads((run/'report.json').read_text());assert receipt['exit_status']==0 and not receipt['timed_out']and receipt['same_architectural_signature_as_frozen_guest']
  mailboxes[case]=mailbox(run/'guest.signature',case)
  inputs += [run/n for n in ['report.json','activity.bin.gz','guest.signature','stdout','stderr']]
  for seed in [0,17,91]:
   command=[str(replay/'replay'),str(run/'activity.bin.gz'),str(seed)]
   if seed==17:command+=['--projection',str(out/(case+'-projection.ndjson.gz'))]
   start=time.monotonic()
   with(out/(case+'-seed'+str(seed)+'.stdout')).open('w')as stdout,(out/(case+'-seed'+str(seed)+'.stderr')).open('w')as stderr:q=subprocess.run(command,stdout=stdout,stderr=stderr,timeout=240)
   if q.returncode:raise ValueError('Activity replay failed '+case+' seed'+str(seed))
   result=json.loads((out/(case+'-seed'+str(seed)+'.stdout')).read_text());positives.append({'case':case,'seed':seed,'argv':command,'host_seconds':time.monotonic()-start,**result})
   print(json.dumps({'case':case,'seed':seed,'harts':result['harts']}),flush=True)
  rows=[r for r in positives if r['case']==case]
  if any(r['harts']!=rows[0]['harts']for r in rows[1:]):raise ValueError('Qualified active state changed with initialization seed')
 # Pure source-shape oracle does not import Spike/array numeric semantics.
 totals=[dict.fromkeys(names,0)for _ in range(3)];frames=[0]*3;points={};last=[None]*3
 for line in gzip.open(out/'vme-projection.ndjson.gz','rt'):
  row=json.loads(line);h,e,t,known,*values=row
  if len(row)!=len(projection_schema['record_layout'])or e!=frames[h]or(last[h]is not None and t<=last[h]):raise ValueError('Invalid compact projection identity')
  frames[h]+=1;last[h]=t
  if known>>len(names):raise ValueError('Projection known mask beyond schema')
  for n,(name,value)in enumerate(zip(names,values)):
   if not known>>n&1:
    if value:raise ValueError('Unknown value was emitted without mask')
    continue
   totals[h][name]+=value
   if h==0 and value and name not in points:points[name]=e
 for h in [0,1]:
  for name in ['VME_INT8_MAC_accept','VME_INT8_MAC_complete']:
   if totals[h][name]!=4*17*31*2:raise ValueError('INT8 source shape MAC count mismatch')
  for name in ['VME_FP8_MAC_accept','VME_FP8_MAC_complete']:
   if totals[h][name]!=4*4*17*31*2:raise ValueError('FP8 source format/shape MAC count mismatch')
  if totals[h]['VME_macro_accept']!=93 or totals[h]['VME_micro_issue']!=641:raise ValueError('VME sequencer event count mismatch')
  if totals[h]['VRF_scrub']!=64:raise ValueError('Compute VRF scrub not source64edges')
 if totals[2]['VRF_scrub']!=32 or any(value for name,value in totals[2].items()if name.startswith('VME_')):raise ValueError('Rocket profile was given compute VME activity')
 # Mutation changes one expected observer bit in memory, never source/model inputs.
 fields={f['name']:f for f in schema['profiles']['compute']['fields']}
 first_nonreset=next(json.loads(line)[1]for line in gzip.open(out/'vme-projection.ndjson.gz','rt')if json.loads(line)[0]==0 and json.loads(line)[3]&2)
 mutations=[('dispatch_counter','dis.debug_id_ctr',first_nonreset),
            ('accepted_macro_bits','vu.vos.io_dis_bits_bits',points['VME_macro_accept']),
            ('array_MAC_enable','vu.vopu_ctrl_reg_macc_0',points['VME_INT8_MAC_accept']),
            ('FP8_physical_completion','vu.vopu.clusters_0_0.cells_0_0.fma.io_validout_pipe_v',points['VME_FP8_MAC_complete']),
            ('VRF_write_mask','vu.vos.io_write_mask',points['VME_VRF_write_bits']),
            ('memory_response_tag','vmu.io_dmem_store_ack_bits_tag',points['VMU_store_ack'])]
 negatives=[]
 for label,field,edge in mutations:
  index=fields[field]['words'][0]['index'];command=[str(replay/'replay'),str(captures/'vme/activity.bin.gz'),'17','--projection','/dev/null','--mutate','0',str(edge),str(index)]
  with(out/(label+'.stdout')).open('w')as stdout,(out/(label+'.stderr')).open('w')as stderr:q=subprocess.run(command,stdout=stdout,stderr=stderr,timeout=90)
  error=(out/(label+'.stderr')).read_text()
  if q.returncode!=2 or'Activity mismatch h0 edge'+str(edge)not in error or field not in error:raise ValueError('Mutation was not caught at intended source field '+label)
  negatives.append({'label':label,'field':field,'edge':edge,'word':index,'argv':command,'exit_status':q.returncode,'error':error.splitlines()[-1]})
 guard=out/'guards.cpp';shutil.copy2(R/'timing/saturn_timing_activity_guards.cpp',guard)
 command=['/usr/bin/g++','-O3','-std=c++20','-pthread','-I'+str(sdk/'sdk'),'-I/scratch/eygao/iris-cy/.conda-env/share/verilator/include',str(guard),str(sdk/'sdk/libiris_saturn_timing.a'),'-latomic','-o',str(out/'guards')]
 with(out/'guards-build.log').open('w')as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 guard_result=json.loads(subprocess.check_output([str(out/'guards')],text=True,stderr=(out/'guards.stderr').open('w')));inputs += [R/'timing/saturn_timing_activity_guards.cpp',guard]
 result={'schema':'iris.saturn_internal_activity_actual_rtl_proof.v1','positive_replays':positives,'guest_mailboxes':mailboxes,'VME_projection_source_shape_checks':{'per_compute_hart_INT8_MACs':4*17*31*2,'per_compute_hart_FP8_MACs':4*4*17*31*2,'all_three_hart_totals':totals,'frames':frames},'expected_observation_bit_corruptions':negatives,'phase_guards':{'argv':command,'result':guard_result},'input_sha256':{str(p):sha(p)for p in inputs},'all_internal_state_computed_continuously_from_actual_reset':True,'only_physical_inputs_drive_model':True,'control_qualification_not_architectural_numeric_definedness':True,'FPGA_or_full_timing_certified':False,'hardware_contacted':False};result['artifact_sha256']={str(p.relative_to(out)):sha(p)for p in out.iterdir()if p.is_file()};(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'report_sha256':sha(out/'report.json'),'positive_runs':len(positives),'negative_mutations':len(negatives),'guards':guard_result}),flush=True)
if __name__=='__main__':main()
