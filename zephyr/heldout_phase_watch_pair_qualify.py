#!/usr/bin/env python3
import argparse,hashlib,json,struct
from pathlib import Path
import sys
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'firesim'))
from heldout_phase_watch_pair_validate import validate
from heldout_phase_diagnostic_validate import timeout_evidence

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def verify_pair(m):
 a=Path(m['variants']['enabled']['path']).read_bytes();b=Path(m['variants']['disabled']['path']).read_bytes();assert a[:7]==b'\x7fELF\x02\x01\x01'and len(a)==len(b);assert sha(m['variants']['enabled']['path'])==m['variants']['enabled']['sha256']and sha(m['variants']['disabled']['path'])==m['variants']['disabled']['sha256']
 off=struct.unpack_from('<Q',a,40)[0];size,count=struct.unpack_from('<HH',a,58);secs=[struct.unpack_from('<IIQQQQIIQQ',a,off+i*size)for i in range(count)];found=[]
 for s in secs:
  if s[1]!=2:continue
  strings=secs[s[6]];names=a[strings[4]:strings[4]+strings[5]]
  for p in range(s[4],s[4]+s[5],s[9]):
   name,info,other,index,address,n=struct.unpack_from('<IBBHQQ',a,p)
   if name and names[name:].split(b'\0',1)[0]==b'iris_diag_watchdog_enabled':found.append((address,n,index))
 assert len(found)==1;address,n,index=found[0];section=secs[index];assert n==1 and section[1]!=8 and section[2]&2 and not section[2]&4 and section[3]<=address<section[3]+section[5];offset=section[4]+address-section[3];assert [i for i,(x,y)in enumerate(zip(a,b))if x!=y]==[offset]and a[offset]==1 and b[offset]==0
 assert all(a[s[4]:s[4]+s[5]]==b[s[4]:s[4]+s[5]]for s in secs if s[2]&4)
 return dict(single_nonexec_data_byte=True,address=address,file_offset=offset,enabled=1,disabled=0,all_other_filebytes_identical=True,all_instruction_and_symbol_addresses_identical=True)
def main():
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--negative-build',type=Path,required=True);a=p.parse_args();b=a.build.resolve();m=json.loads((b/'manifest.json').read_text());assert not m['force_stall_negative'];pair=verify_pair(m);ident={};runs=[];controls=[];cases=json.loads((b/'cases.json').read_text());gold=json.loads((b/'golden.json').read_text())
 def bind(path,d=None):
  path=Path(path).resolve();v=sha(path);assert d is None or d==v;assert str(path)not in ident or ident[str(path)]==v;ident[str(path)]=v
 for path in[Path(__file__),Path(__file__).with_name('heldout_phase_watch_pair_validate.py'),Path(__file__).with_name('heldout_phase_watch_pair_run.py'),Path(__file__).with_name('heldout_phase_diagnostic_validate.py'),b/'manifest.json',b/'pair-proof.json',b/'cases.json',b/'golden.json']:bind(path)
 for path,d in m['input_sha256'].items():bind(path,d)
 for variant in['enabled','disabled']:
  bind(m['variants'][variant]['path'],m['variants'][variant]['sha256'])
  for seed in[0,17]:
   d=R/f'build/phase-watch-byte-pair-v1-{variant}-seed{seed}';r=json.loads((d/'report.json').read_text());assert r['pass']and r['variant']==variant and r['seed']==seed and r['exit_status']==0 and not r['timed_out']and r['ELF_sha256']==m['variants'][variant]['sha256'];validate((d/'stdout').read_text(),dict(m,ELF_sha256=r['ELF_sha256']),cases,gold,variant=='enabled');runs.append(dict(variant=variant,seed=seed,report=str(d/'report.json'),report_sha256=sha(d/'report.json')))
   for path,digest in r['input_sha256'].items():bind(path,digest)
   for path in d.iterdir():
    if path.is_file():bind(path)
 negative=[];nm=json.loads((a.negative_build.resolve()/'manifest.json').read_text());assert nm['force_stall_negative'];verify_pair(nm)
 for variant in['enabled','disabled']:
  d=R/f'build/phase-watch-byte-pair-negative-v1-{variant}-run';r=json.loads((d/'report.json').read_text());assert r['pass']and r['variant']==variant and r['force_stall_negative'];text=(d/'stdout').read_text()
  if variant=='enabled':assert r['exit_status']==1 and not r['timed_out'];timeout_evidence(text,forced=True)
  else:assert r['timed_out']and r['exit_status']is None and 'IRIS_DIAG_TIMEOUT 'not in text and 'IRIS_DIAG_DONE 'not in text
  negative.append(dict(variant=variant,report=str(d/'report.json'),report_sha256=sha(d/'report.json'),proof=r['proof']))
  for path,digest in r['input_sha256'].items():bind(path,digest)
  for path in d.iterdir():
   if path.is_file():bind(path)
 # Proof readers reject in-memory table/console corruption without changing inputs.
 ontext=(R/'build/phase-watch-byte-pair-v1-enabled-seed0/stdout').read_text();offtext=(R/'build/phase-watch-byte-pair-v1-disabled-seed0/stdout').read_text()
 def reject(name,fn):
  try:fn()
  except(ValueError,AssertionError,TypeError,KeyError):controls.append(dict(name=name,rejected=True));return
  raise ValueError('Corruption accepted '+name)
 reject('disabled console falsely reports watcher',lambda:validate(offtext+'\nIRIS_DIAG_WATCHDOG {"hart":1,"no_progress_ms":5000}\n',dict(m,ELF_sha256=m['variants']['disabled']['sha256']),cases,gold,False))
 reject('enabled console lacks watcher',lambda:validate('\n'.join(x for x in ontext.splitlines()if not x.startswith('IRIS_DIAG_WATCHDOG ')),dict(m,ELF_sha256=m['variants']['enabled']['sha256']),cases,gold,True))
 reject('missing normal completion',lambda:validate('\n'.join(x for x in offtext.splitlines()if not x.startswith('IRIS_DIAG_DONE ')),dict(m,ELF_sha256=m['variants']['disabled']['sha256']),cases,gold,False))
 changed=dict(m,variants=dict(m['variants']));changed['variants']['disabled']=m['variants']['enabled'];reject('identical bytes falsely called toggle pair',lambda:verify_pair(changed))
 body=json.loads((b/'pair-proof.json').read_text())['parent_compiled_objects'];assert len(body)==8 and all(sha(x['path'])==x['sha256']==x['parent_sha256']for x in body)
 q=dict(schema='iris.phase_watch_one_byte_pair_qualification.v1',**{'pass':True},pair=pair,pair_proof_sha256=sha(b/'pair-proof.json'),functional=runs,forced_counterfactuals=negative,negative_controls=controls,parent_compiled_objects=body,input_sha256=ident,hardware_contacted=False,fitting_allowed=False,root_cause_proven=False);(b/'qualification.json').write_text(json.dumps(q,indent=2)+'\n');ready=dict(schema='iris.phase_watch_one_byte_pair_ready.v1',status='ready_for_root_managed_preparation',manifest_sha256=sha(b/'manifest.json'),qualification_sha256=sha(b/'qualification.json'),pair_proof_sha256=sha(b/'pair-proof.json'),cases_sha256=sha(b/'cases.json'),golden_sha256=sha(b/'golden.json'),variants=m['variants'],phases=2,cases=32,regions=32,all_instruction_addresses_identical=True,only_one_retained_nonexec_byte_differs=True,all4seeded_positives_pass=True,both_forced_counterfactuals_pass=True,diagnostic_only=True,fitting_allowed=False,source_frozen=True);(b/'ready.json').write_text(json.dumps(ready,indent=2)+'\n');print(json.dumps(dict(status=ready['status'],ready_sha256=sha(b/'ready.json'),pair=pair)))
if __name__=='__main__':main()
