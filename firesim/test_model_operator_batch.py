#!/usr/bin/env python3
"""Actual local admission, source-body and wrong-archive-role controls."""
import copy,json,shutil,struct,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from batch_runner import digest
from prepare_model_operator_batch import admit,merge
from analyze_model_operator_batch import analyze
def main():
 out=ROOT/'build/model-operator-tools-local-v1';out.mkdir(exist_ok=False);base=ROOT/'build/model-operator-batch-v1';controls=[]
 ready,corpus,cases,elf,identities=admit(base,digest(base/'ready.json'))
 if len(cases)!=48 or len(identities)<20:raise ValueError('Actual admission incomplete')
 def negative(name,edit):
  with tempfile.TemporaryDirectory(dir=out)as directory:
   target=Path(directory)/'copy';shutil.copytree(base,target);r=json.loads((target/'ready.json').read_text());r['elf']=str(target/'batch.elf');r['corpus_path']=str(target/'corpus.json');edit(target,r);(target/'ready.json').write_text(json.dumps(r)+'\n')
   try:admit(target,digest(target/'ready.json'))
   except(ValueError,KeyError):controls.append(dict(name=name,rejected=True));return
   raise ValueError('Admitted corruption '+name)
 negative('calibration eligibility',lambda t,r:r.update(calibration_usable=True))
 negative('TinyLlama protection removed',lambda t,r:r.update(TinyLlama_protected=False))
 negative('false exact checkpoint admission',lambda t,r:r.update(exact_Llama2_checkpoint_admitted=True))
 negative('region count',lambda t,r:r.update(required_regions=119))
 def qualify_edit(t,r,fn):
  p=t/'qualification.json';q=json.loads(p.read_text());fn(q);p.write_text(json.dumps(q)+'\n');r['qualification_sha256']=digest(p)
 negative('missing seed17',lambda t,r:qualify_edit(t,r,lambda q:q.update(functional=q['functional'][:1])))
 negative('actual no-op proof removed',lambda t,r:qualify_edit(t,r,lambda q:q['negative_controls'][-1].pop('failed_compute_words')))
 def body(t,r):
  p=t/'binary-proof.json';proof=json.loads(p.read_text());g=next(x for x in proof['actual_MLIR_object_export_renames']if x['kind']=='model');data=bytearray(Path(g['renamed']).read_bytes());shoff=struct.unpack_from('<Q',data,40)[0];size,count=struct.unpack_from('<HH',data,58)
  for i in range(count):
   f=struct.unpack_from('<IIQQQQIIQQ',data,shoff+i*size)
   if f[2]&4 and f[5]:data[f[4]]^=1;break
  changed=t/'changed-body.o';changed.write_bytes(data);g['renamed']=str(changed);g['renamed_sha256']=digest(changed);p.write_text(json.dumps(proof)+'\n');r['binary_proof_sha256']=digest(p);qualify_edit(t,r,lambda q:q.update(binary_proof_sha256=digest(p)))
 negative('changed compiled MLIR opcode',body)
 try:admit(base,'0'*64)
 except ValueError:controls.append(dict(name='wrong frozen ready hash',rejected=True))
 else:raise ValueError('Wrong ready digest accepted')
 d={};merge(d,{'workloads/model_operator_batch_validate.py':digest(ROOT/'workloads/model_operator_batch_validate.py')})
 if not all(Path(p).is_absolute()for p in d):raise ValueError('Relative source map escaped normalization')
 try:merge(d,{'workloads/model_operator_batch_validate.py':'0'*64})
 except ValueError:controls.append(dict(name='conflicting normalized source identity',rejected=True))
 else:raise ValueError('Conflicting source digest accepted')
 wrong=ROOT/'runs/fpga-buffered-fit-v1-002'
 if analyze(wrong,out/'wrong-role-archive')==0:raise ValueError('Wrong hardware archive role accepted')
 controls.append(dict(name='actual archived fitting run rejected for protected operator role',rejected=True))
 sources=[Path(__file__),ROOT/'firesim/prepare_model_operator_batch.py',ROOT/'firesim/analyze_model_operator_batch.py',ROOT/'workloads/model_operator_batch_validate.py']
 result=dict(schema='iris.model_operator_managed_tools_local_controls.v1',**{'pass':True},actual_positive_admission=True,admitted_cases=48,admitted_regions=120,negative_controls=controls,all_input_paths_absolute=True,hardware_contacted=False,input_sha256={str(p.resolve()):digest(p)for p in sources});(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(**{'pass':True},controls=len(controls),report_sha256=digest(out/'report.json'))))
if __name__=='__main__':main()
