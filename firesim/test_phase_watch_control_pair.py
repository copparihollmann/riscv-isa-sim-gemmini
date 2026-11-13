#!/usr/bin/env python3
"""Adversarial controls for offline paired numerical/byte evidence."""
import copy,json
from pathlib import Path
from analyze_phase_watch_control_pair import numeric,independent_goldens,pair_elf,hf
R=Path(__file__).resolve().parents[1]
def main():
 out=R/'build/phase-watch-control-pair-controls-v1';out.mkdir(exist_ok=False);texts={};corpora={};elf={};g=independent_goldens();checks=[]
 for v in ['enabled','disabled']:
  p=R/('runs/fpga-phase-watch-byte-'+v+'-v1-001');texts[v]=(p/'optional-observability/uartlog').read_text();corpora[v]=json.loads((p/'corpus.json').read_text());elf[v]=(p/'manager/workloads/iris-batch/batch.elf').read_bytes();rows,proof=numeric(texts[v],corpora[v],v,g);assert len(rows)==(32 if v=='enabled'else 16)and proof['normal_completion']is(v=='enabled')
 pair_elf(elf['enabled'],elf['disabled'])
 def reject(name,call):
  try:call()
  except(ValueError,KeyError,TypeError,AssertionError):checks.append(dict(name=name,rejected=True));return
  raise ValueError('Accepted '+name)
 def changed(v,tag,key,value):
  ls=texts[v].splitlines();i=next(i for i,s in enumerate(ls)if s.startswith(tag+' '));row=json.loads(ls[i][len(tag)+1:]);row[key]=value;ls[i]=tag+' '+json.dumps(row);return '\n'.join(ls)
 for key,value in [('hart',True),('start_cycle',True),('instret_delta',0),('checksum',0),('role','scalar.compute')]:reject('ROI-'+key,lambda k=key,v=value:numeric(changed('enabled','IRIS_REGION',k,v),corpora['enabled'],'enabled',g))
 for key,value in [('word_count',True),('accumulator_checksum',0),('mismatching_w8a8_words',1),('job',1)]:reject('full-output-'+key,lambda k=key,v=value:numeric(changed('enabled','IRIS_HELDOUT_RESULT',k,v),corpora['enabled'],'enabled',g))
 reject('terminal-bool',lambda:numeric(changed('enabled','IRIS_BATCH_DONE','failed',False),corpora['enabled'],'enabled',g))
 reject('watcher-hart-bool',lambda:numeric(changed('enabled','IRIS_DIAG_WATCHDOG','hart',True),corpora['enabled'],'enabled',g))
 reject('missing-trial-last-job',lambda:numeric('\n'.join(s for s in texts['enabled'].splitlines()if not(s.startswith('IRIS_HELDOUT_RESULT ')and '"job":14' in s)),corpora['enabled'],'enabled',g))
 bad=copy.deepcopy(corpora['enabled']);bad['goldens'][0][2]['accumulator_u32'][123]^=1;reject('independent-math-golden',lambda:numeric(texts['enabled'],bad,'enabled',g))
 bad=copy.deepcopy(corpora['enabled']);bad['watchdog_enabled']=1;reject('watch-enabled-bool-type',lambda:numeric(texts['enabled'],bad,'enabled',g))
 reject('disabled-false-normal-DONE',lambda:numeric(texts['disabled']+'\nIRIS_DIAG_DONE {"phases":2,"failed":0}\n',corpora['disabled'],'disabled',g))
 reject('disabled-false-watch-start',lambda:numeric(texts['disabled']+'\nIRIS_DIAG_WATCHDOG {"hart":1,"no_progress_ms":5000}\n',corpora['disabled'],'disabled',g))
 reject('disabled-host-timeout-mislabeled-success',lambda:numeric(texts['disabled'].replace('COMMAND_EXIT_CODE="124"','COMMAND_EXIT_CODE="0"'),corpora['disabled'],'disabled',g))
 b=bytearray(elf['disabled']);b[55625]^=1;reject('second-ELF-byte-changed',lambda:pair_elf(elf['enabled'],bytes(b)))
 b=bytearray(elf['disabled']);b[55624]=2;reject('flag-value-two',lambda:pair_elf(elf['enabled'],bytes(b)))
 reject('reversed-flag-ELFs',lambda:pair_elf(elf['disabled'],elf['enabled']))
 paths=[Path(__file__),R/'firesim/analyze_phase_watch_control_pair.py'];r=dict(schema='iris.actual_watch_pair_corruption_controls.v1',**{'pass':True},real_enabled_full_numeric_passed=True,real_disabled_phase0_numeric_passed=True,disabled_normal_completion=False,controls=checks,hardware_contacted=False,global_v6_reference_timing_labels_consumed=False,input_sha256={str(p):hf(p)for p in paths});(out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(**{'pass':True},controls=len(checks),sha256=hf(out/'report.json'))))
if __name__=='__main__':main()
