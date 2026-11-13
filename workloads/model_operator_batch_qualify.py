#!/usr/bin/env python3
"""Qualify seeded runs, real omitted-call ELF and compiled-body refusal guards."""
import argparse,copy,hashlib,json
from pathlib import Path
from model_operator_batch_validate import validate
from model_operator_batch_build import text_sections
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--seed0',type=Path,required=True);p.add_argument('--seed17',type=Path,required=True);p.add_argument('--negative',type=Path,required=True);a=p.parse_args();b=a.build.resolve();corpus=json.loads((b/'corpus.json').read_text());built=json.loads((b/'build.json').read_text());proof=json.loads((b/'binary-proof.json').read_text());identities={};controls=[];functional=[]
 def bind(p,expected=None):
  p=Path(p).resolve();observed=sha(p)
  if expected is not None and observed!=expected:raise ValueError('Input mismatch '+str(p))
  if str(p)in identities and identities[str(p)]!=observed:raise ValueError('Conflicting input digest')
  identities[str(p)]=observed
 for p in [Path(__file__),Path(__file__).with_name('model_operator_batch_validate.py'),Path(__file__).with_name('model_operator_batch_build.py'),b/'build.json',b/'corpus.json',b/'binary-proof.json',b/'batch.elf']:bind(p)
 if built['deliberate_noop_negative']or built['elf_sha256']!=sha(b/'batch.elf')or not proof['pass']:raise ValueError('Positive compiled-body proof required')
 for case in corpus['cases']:
  if case['source_case']['shape_mnk'][:2]!=[2,32]or case['workers']not in(1,2)or case['active_harts']!=list(range(case['workers']))+[2]or case['calibration_usable']is not False or case['validation_only']is not True:raise ValueError('Finite protected operator cases')
 for guard in proof['actual_MLIR_object_export_renames']:
  if guard['kind']not in('model','bridge'):continue
  original,renamed=Path(guard['source']),Path(guard['renamed']);bind(original,guard['source_sha256']);bind(renamed,guard['renamed_sha256'])
  if text_sections(original)!=text_sections(renamed):raise ValueError('Compiled body changed')
 first=next(g for g in proof['actual_MLIR_object_export_renames']if g['kind']=='model');sections=text_sections(first['source']);mutated=list(sections);mutated[0]=bytes([sections[0][0]^1])+sections[0][1:]
 if mutated==text_sections(first['renamed']):raise ValueError('Body corruption not rejected')
 controls.append(dict(name='one executable-byte change in renamed actual MLIR object',rejected=True))
 first_text=None
 for seed,directory in [(0,a.seed0.resolve()),(17,a.seed17.resolve())]:
  path=directory/'report.json';r=json.loads(path.read_text());bind(path);bind(directory/'stdout',r['stdout_sha256']);bind(directory/'stderr',r['stderr_sha256'])
  if not r['pass']or r['seed']!=seed or r['elf_sha256']!=sha(b/'batch.elf')or r['returncode']!=0 or r['timed_out']or r['deliberate_noop_negative']or not r['native_sha256'].startswith('35901887'):raise ValueError('Exact fresh359 seeded positive required')
  for name,d in r['input_sha256'].items():bind(name,d)
  text=(directory/'stdout').read_text();validated=validate(text,corpus);functional.append(dict(seed=seed,report=str(path),report_sha256=sha(path),stdout_sha256=sha(directory/'stdout'),proof=validated))
  if first_text is None:first_text=text
 def reject(name,changed):
  try:validate(changed,corpus)
  except(ValueError,KeyError,TypeError):controls.append(dict(name=name,rejected=True));return
  raise ValueError('Corruption accepted '+name)
 lines=first_text.splitlines();wi=next(i for i,x in enumerate(lines)if x.startswith('IRIS_WORDS '));ri=next(i for i,x in enumerate(lines)if x.startswith('IRIS_REGION '));pi=next(i for i,x in enumerate(lines)if x.startswith('IRIS_REGION ')and json.loads(x.split(' ',1)[1])['hart']==2)
 for name,index,field in [('full accumulator',wi,'accumulator_u32'),('W8A8 word',wi,'W8A8_f32_words'),('checksum',ri,'checksum'),('trial identity',ri,'trial_id')]:
  changed=list(lines);row=json.loads(changed[index].split(' ',1)[1]);
  if isinstance(row[field],list):row[field][0]^=1
  else:row[field]+=1
  changed[index]=changed[index].split(' ',1)[0]+' '+json.dumps(row);reject(name,'\n'.join(changed))
 reject('missing producer ROI','\n'.join(lines[:pi]+lines[pi+1:]));reject('duplicate full output','\n'.join(lines+[lines[wi]]));reject('missing batch completion','\n'.join(x for x in lines if not x.startswith('IRIS_BATCH_DONE ')))
 neg=a.negative.resolve();nr=json.loads((neg/'report.json').read_text());bind(neg/'report.json');bind(neg/'stdout',nr['stdout_sha256']);bind(neg/'stderr',nr['stderr_sha256'])
 for name,d in nr['input_sha256'].items():bind(name,d)
 if not nr['pass']or not nr['deliberate_noop_negative']or nr['returncode']==0 or nr['proof']['failed_compute_words']!=3072:raise ValueError('Actual omitted-call negative required')
 controls.append(dict(name='actual compiled omitted-kernel ELF',rejected=True,failed_compute_words=3072,report_sha256=sha(neg/'report.json')))
 result=dict(schema='iris.model_operator_batch_qualification.v1',**{'pass':True},elf_sha256=sha(b/'batch.elf'),corpus_sha256=sha(b/'corpus.json'),binary_proof_sha256=sha(b/'binary-proof.json'),functional=functional,negative_controls=controls,input_sha256=identities,hardware_contacted=False,calibration_usable=False,TinyLlama_protected_validation_only=True)
 (b/'qualification.json').write_text(json.dumps(result,indent=2)+'\n');ready=dict(schema='iris.model_operator_batch_ready.v1',status='ready_for_root_managed_preparation',elf=str(b/'batch.elf'),elf_sha256=sha(b/'batch.elf'),corpus_path=str(b/'corpus.json'),corpus_sha256=sha(b/'corpus.json'),build_sha256=sha(b/'build.json'),binary_proof_sha256=sha(b/'binary-proof.json'),qualification_sha256=sha(b/'qualification.json'),required_cases=48,required_regions=120,trials=3,full_int32_words=3072,full_W8A8_words=3072,all_harts=[0,1,2],h2_role='real operand producer and fresh-output poison, independently hashed before compute',calibration_usable=False,all_cases_validation_only=True,TinyLlama_protected=True,exact_Llama2_checkpoint_admitted=False,source_frozen_for_preparation=True,proposed_runtime=dict(driver='original archived8f',fesvr_step_size=128,target_max_cycles=None,watchdog_seconds=600,phase_timeout_seconds=780))
 (b/'ready.json').write_text(json.dumps(ready,indent=2)+'\n');print(json.dumps(dict(status=ready['status'],ready_sha256=sha(b/'ready.json'),negative_controls=len(controls),regions=120)))
if __name__=='__main__':main()
