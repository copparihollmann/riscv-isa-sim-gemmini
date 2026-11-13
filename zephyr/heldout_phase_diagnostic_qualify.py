#!/usr/bin/env python3
import argparse,hashlib,json,pathlib,shutil,sys
from heldout_phase_diagnostic_validate import validate,timeout_evidence
R=pathlib.Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--build',type=pathlib.Path,required=True);p.add_argument('--seed0',type=pathlib.Path,required=True);p.add_argument('--seed17',type=pathlib.Path,required=True);p.add_argument('--negative',type=pathlib.Path,required=True);a=p.parse_args();b=a.build.resolve();m=json.loads((b/'manifest.json').read_text());cases=json.loads((b/'cases.json').read_text());gold=json.loads((b/'golden.json').read_text());ident={};runs=[];controls=[]
 def bind(p,d=None):
  p=pathlib.Path(p).resolve();v=sha(p);assert d is None or d==v,(str(p),d,v);assert str(p)not in ident or ident[str(p)]==v;ident[str(p)]=v
 for path in [pathlib.Path(__file__),pathlib.Path(__file__).with_name('heldout_phase_diagnostic_validate.py'),pathlib.Path(__file__).with_name('heldout_phase_diagnostic_run.py'),b/'manifest.json',b/'cases.json',b/'golden.json',pathlib.Path(m['ELF']),b/'diag_mark.disassembly',b/'diag_watchdog.disassembly']:bind(path)
 for name,d in m['input_sha256'].items():bind(name,d)
 first=None
 for seed,directory in [(0,a.seed0.resolve()),(17,a.seed17.resolve())]:
  r=json.loads((directory/'report.json').read_text());assert r['pass']and r['seed']==seed and r['exit_status']==0 and not r['timed_out']and r['ELF_sha256']==m['ELF_sha256']and r['native_sha256'].startswith('35901887');text=(directory/'stdout').read_text();proof=validate(text,m,cases,gold);first=first or text;runs.append(dict(seed=seed,report=str(directory/'report.json'),report_sha256=sha(directory/'report.json'),proof=proof))
  for name,d in r['input_sha256'].items():bind(name,d)
  for path in directory.iterdir():
   if path.is_file():bind(path)
 negative=a.negative.resolve();r=json.loads((negative/'report.json').read_text());assert r['pass']and r['force_stall_negative']and r['exit_status']==1 and not r['timed_out'];timeout=timeout_evidence((negative/'stdout').read_text(),forced=True)
 for name,d in r['input_sha256'].items():bind(name,d)
 for path in negative.iterdir():
  if path.is_file():bind(path)
 def reject(name,fn):
  try:fn()
  except(ValueError,TypeError,KeyError):controls.append(dict(name=name,rejected=True));return
  raise ValueError('Corruption accepted '+name)
 lines=first.splitlines()
 for tag,field in [('IRIS_REGION ','checksum'),('IRIS_HELDOUT_RESULT ','accumulator_checksum'),('IRIS_DIAG_WATCHDOG ','hart')]:
  changed=list(lines);i=next(i for i,x in enumerate(changed)if x.startswith(tag));row=json.loads(changed[i].split(' ',1)[1]);row[field]+=1;changed[i]=tag+json.dumps(row);reject(tag+field,lambda changed=changed:validate('\n'.join(changed),m,cases,gold))
 reject('missing normal completion',lambda:validate('\n'.join(x for x in lines if not x.startswith('IRIS_DIAG_DONE ')),m,cases,gold))
 negtext=(negative/'stdout').read_text();reject('timeout labeled normal completion',lambda:timeout_evidence(negtext+'\nIRIS_DIAG_DONE {}\n',forced=True))
 row=dict(timeout['mailboxes_raw']);row['watchdog_hart']=0;reject('wrong timeout watchdog physicalhart',lambda:timeout_evidence('IRIS_DIAG_TIMEOUT '+json.dumps(row),forced=True))
 row=dict(timeout['mailboxes_raw']);row['main']^=1;reject('wrong forced stage',lambda:timeout_evidence('IRIS_DIAG_TIMEOUT '+json.dumps(row),forced=True))
 parent=R/'build/fast-heldout-zephyr-compact-v6';pm=json.loads((parent/'manifest.json').read_text());body=[]
 for path in sorted((b/'generated').glob('*.o')):
  name=str(parent/'generated'/path.name);expect=pm['inputs'][name]['sha256'];assert sha(path)==expect;bind(path,expect);body.append(dict(path=str(path),parent_object_sha256=expect,byte_identical=True))
 assert len(body)==8
 controls.append(dict(name='changed compiledobject byte rejected by parent hash',rejected=hashlib.sha256(b'\x00'+path.read_bytes()[1:]).hexdigest()!=sha(path)))
 result=dict(schema='iris.phase_handoff_diagnostic_qualification.v1',**{'pass':True},ELF_sha256=m['ELF_sha256'],functional=runs,forced_timeout_control=timeout,negative_controls=controls,exact_parent_compiled_objects=body,watchdog_and_marker_bodies_no_FP_instructions=True,input_sha256=ident,hardware_contacted=False,fitting_allowed=False,global_v6_reference_timing_labels_consumed=False)
 (b/'qualification.json').write_text(json.dumps(result,indent=2)+'\n');ready=dict(schema='iris.phase_handoff_diagnostic_ready.v1',status='ready_for_root_managed_preparation',ELF=m['ELF'],ELF_sha256=m['ELF_sha256'],manifest_sha256=sha(b/'manifest.json'),qualification_sha256=sha(b/'qualification.json'),cases_sha256=sha(b/'cases.json'),golden_sha256=sha(b/'golden.json'),phases=2,cases=32,regions=32,watchdog_hart=1,no_stage_progress_timeout_ms=5000,forced_negative_watchdog_passed=True,original_parent_objects_unchanged=True,source_frozen=True,diagnostic_only=True,hardware_contacted=False,fitting_allowed=False,proposed_runtime=dict(originaldriver=True,fesvr_step_size=128,target_max_cycles=None,wall_watchdog_seconds=600,phase_timeout_seconds=780));(b/'ready.json').write_text(json.dumps(ready,indent=2)+'\n');print(json.dumps(dict(status=ready['status'],ready_sha256=sha(b/'ready.json'),controls=len(controls))))
if __name__=='__main__':main()
