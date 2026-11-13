#!/usr/bin/env python3
"""Real model-only readback/CSR proof plus synthetic-label math/refusal controls."""
import copy,hashlib,json,math,tempfile
from fractions import Fraction
from pathlib import Path
import sys
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'timing'))
import compare_overlap_completion_v2 as v

def main():
 o=R/'build/overlap-comparison-v2-qualification-v2';o.mkdir(exist_ok=False);corpus=v.load(R/'build/overlap-completion-console-guest-v1/corpus.json');elf=R/'build/overlap-completion-console-guest-v1/overlap.elf';runs=[R/'build/overlap-completion-console-selected7bd5-baseline-v1',R/'build/overlap-completion-entry-queue-final-ON-v1'];checks=[];positive=[]
 def reject(name,fn):
  try:fn()
  except(ValueError,KeyError,IndexError,TypeError):checks.append(dict(name=name,rejected=True));return
  raise ValueError('Accepted corruption: '+name)
 for run in runs:
  rows,scope,rr=v.native(run,corpus,elf);positive.append(dict(run=str(run),native_sha256=scope['native_binary_sha256'],actual_CSR_ELF_joins=scope['actual_CSR_ELF_joins'],qualified_elements=scope['fullword_or_activebyte_numerical_elements'],normal_HTIF_exit=scope['normal_HTIF_exit'],intentional_postmeasurement_quit=scope['intentional_postmeasurement_quit']))
  if run==runs[1]:
   prediction=R/'build/overlap-completion-b6ee-prediction-v2/prediction.json';assert v.verify_prediction(prediction,run,rows,rr,scope)
   with tempfile.TemporaryDirectory()as tmp:
    for name,key,value in [('wrong-prediction-native','native_binary_sha256','0'*64),('wrong-paired-UART','uart_library_sha256','0'*64),('bool-prediction-count','regions_checked',True)]:
     d=v.load(prediction);d[key]=value;bad=Path(tmp)/(name+'.json');bad.write_text(json.dumps(d));reject(name,lambda b=bad:v.verify_prediction(b,run,rows,rr,scope))
  synthetic=[]
  for i,(s,c)in enumerate(zip(rows,corpus['cases'])):
   b=i*10000000+100;issue=s['issue_end']-s['start']+1;fence=s['fence_end']-s['issue_end']+2;tail=s['drain_end']-s['fence_end']+3
   synthetic.append(dict(case_id='overlap.v1.case.'+str(i),hart=c['hart'],fp8=c['fp8'],edge=c['edge'],count=c['count'],rotate=c['rotate'],trial=c['trial'],internal_split='reserved_validation'if c['edge']==(64 if c['hart']==2 else 16)else'train',pass_=True,failed_elements=0,checksum=sum(v.golden(c)),start_cycle=b,issue_end_cycle=b+issue,fence_end_cycle=b+issue+fence,end_cycle=b+issue+fence+tail,instret_delta=s['instret']))
  for h in synthetic:h['pass']=h.pop('pass_')
  compared=v.compare_rows(rows,synthetic,corpus);stats=v.summarize(compared);assert len(compared)==168
  for s,h,c in zip(rows,synthetic,compared):
   for label,a,b in [('issue',0,1),('fence',1,2),('dependent_readout',2,3),('total',0,3)]:
    ns=[s[k]for k in v.FIELDS];hs=[h[k]for k in v.HW_FIELDS];expected=float(100*Fraction((ns[b]-ns[a])-(hs[b]-hs[a]),hs[b]-hs[a]));assert math.isclose(expected,c[label+'_signed_error_percent'],rel_tol=1e-12)
  positive[-1]['all672_synthetic_window_errors_independently_checked']=True
  if run==runs[0]:
   for name,index,key,value in [('boolean-hart',0,'hart',False),('boolean-counter',0,'end_cycle',True),('changed-trial',0,'trial',99),('changed-golden',0,'checksum',1),('wrong-split',0,'internal_split','reserved_validation'),('reversed-middle-boundary',0,'fence_end_cycle',0),('bool-instret',0,'instret_delta',True)]:
    bad=copy.deepcopy(synthetic);bad[index][key]=value;reject(name,lambda b=bad:v.compare_rows(rows,b,corpus))
   reject('missing-last-trial',lambda:v.compare_rows(rows,synthetic[:-1],corpus));reject('reordered-case',lambda:v.compare_rows(rows,[synthetic[1],synthetic[0],*synthetic[2:]],corpus))
   raw=(run/'stderr').read_text();words=raw.splitlines();i=next(i for i,x in enumerate(words)if x.startswith('0x'));bad=words[:];bad[i]='0x0000000000000001';reject('missing-finished-sentinel',lambda:v.raw_decode('\n'.join(bad),corpus))
   dataindex=[i for i,x in enumerate(words)if x.startswith('0x')][1+168*14];bad=words[:];bad[dataindex]='0x0000000000000000';reject('actual-readback-word-omitted',lambda:v.raw_decode('\n'.join(bad),corpus))
   with tempfile.TemporaryDirectory()as tmp:
    f=Path(tmp)/'features.jsonl';features=[json.loads(x)for x in(run/'features.jsonl').read_text().splitlines()];features[0]['raw']^=4;f.write_text(''.join(json.dumps(x)+'\n'for x in features));reject('wrong-actual-ELF-CSR',lambda:v.join_prefix(f,copy.deepcopy(rows),elf))
    features=[json.loads(x)for x in(run/'features.jsonl').read_text().splitlines()];features[-1]=dict(features[-2]);f.write_text(''.join(json.dumps(x)+'\n'for x in features));reject('duplicate-CSR-ownership',lambda:v.join_prefix(f,copy.deepcopy(rows),elf))
 r=dict(schema='iris.overlap_comparison_model_and_synthetic_qualification.v1',pass_=True,actual_model_only_positive_runs=positive,negative_controls=checks,actual_hardware_label_files_opened=False,synthetic_reference_not_hardware=True,no_global_or_reserved_timing_labels=True,total_only_instret=True,subwindow_instret_invented=False,hardware_contacted=False,input_sha256={str(p):v.sha(p)for p in[Path(__file__).resolve(),R/'timing/compare_overlap_completion_v2.py',R/'timing/compare_pow2_native.py',R/'build/overlap-completion-console-guest-v1/corpus.json',elf,*[run/'run.json'for run in runs]]});r['pass']=r.pop('pass_');(o/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(pass_=True,actual_model_runs=len(positive),negative_controls=len(checks),report_sha256=v.sha(o/'report.json'))))
if __name__=='__main__':main()
