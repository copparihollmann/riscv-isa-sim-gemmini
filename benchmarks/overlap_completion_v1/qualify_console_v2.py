#!/usr/bin/env python3
"""Freeze finite full-word console qualification; no hardware/timing labels."""
import argparse,hashlib,json
from pathlib import Path
from validate_console import validate
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text())
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--seed0',type=Path,required=True);p.add_argument('--seed17',type=Path,required=True);p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 corpus=load(a.build/'corpus.json');build=load(a.build/'build.json');inputs={};runs=[]
 for folder in(a.seed0,a.seed17):
  r=load(folder/'run.json')
  if r.get('pass')is not True or r.get('normal_HTIF_exit')is not True or r.get('forced_debug_quit')is not False or r.get('ELF_sha256')!=build['elf_sha256']:raise ValueError('Actual matching normal functional execution required')
  result=validate((folder/'stdout').read_text(),corpus)
  runs.append({'run':str((folder/'run.json').resolve()),'result':result,'seed':r['seed']})
  inputs[str((folder/'run.json').resolve())]=sha(folder/'run.json');inputs[str((folder/'stdout').resolve())]=sha(folder/'stdout')
 if [r['seed']for r in runs]!=[0,17]:raise ValueError('Exact two functional schedules required')
 baseline=load(a.baseline/'run.json')
 if baseline.get('pass')is not True or baseline.get('ELF_sha256')!=build['elf_sha256']or baseline.get('actual_cycle_endpoints')!=672 or baseline.get('normal_HTIF_exit')is not False or baseline.get('forced_debug_quit')is not True:raise ValueError('Own typed timed post-ROI readback required; do not imply normal exit')
 text=(a.seed0/'stdout').read_text();lines=text.splitlines();wi=next(i for i,l in enumerate(lines)if l.startswith('IRIS_WORD '));ri=next(i for i,l in enumerate(lines)if l.startswith('IRIS_REGION '));controls=[]
 def reject(name,changed):
  try:validate('\n'.join(changed),corpus)
  except(ValueError,KeyError,IndexError,TypeError):controls.append({'name':name,'rejected':True})
  else:raise ValueError('Validator missed '+name)
 reject('missing-word',lines[:wi]+lines[wi+1:]);reject('duplicate-word',lines[:wi]+[lines[wi]]+lines[wi:]);reject('missing-region',lines[:ri]+lines[ri+1:]);reject('duplicate-region',lines[:ri]+[lines[ri]]+lines[ri:])
 for name,key,value in [('wrong-value','value',999),('bool-value','value',True),('negative-value','value',-1),('wrong-hart','hart',2),('out-of-range-case','case',len(corpus['cases']))]:
  changed=lines[:];row=json.loads(changed[wi][len('IRIS_WORD '):]);row[key]=value;changed[wi]='IRIS_WORD '+json.dumps(row);reject(name,changed)
 for name,key,value in [('bad-checksum','checksum',0),('reversed-window','end_cycle',0),('bool-counter','start_cycle',True),('failed-region','failed_elements',1)]:
  changed=lines[:];row=json.loads(changed[ri][len('IRIS_REGION '):]);row[key]=value;changed[ri]='IRIS_REGION '+json.dumps(row);reject(name,changed)
 reject('failed-footer',[l.replace('IRIS_OVERLAP_DONE failed=0','IRIS_OVERLAP_DONE failed=1')for l in lines])
 for path in(Path(__file__),Path(__file__).with_name('validate_console.py'),Path(__file__).with_name('build_console.py'),Path(__file__).with_name('guest_console.c'),a.build/'build.json',a.build/'corpus.json',a.build/'readback-layout.json',a.build/'overlap.elf',a.baseline/'run.json',a.baseline/'regions.json',a.baseline/'features.jsonl'):
  inputs[str(path.resolve())]=sha(path)
 report={'schema':'iris.overlap_completion_console_qualification.v2','pass':True,'ELF_sha256':build['elf_sha256'],'cases':168,'functional_normal_exit_runs':runs,'numeric_elements_per_run':19872,'matrix_readback_scope':'row0 of each4tiles;32wordsperrow inclzero-tail; otherMRFrowsnotread','vector_readback_scope':'everyactiveVLbytepluszero-padding','typed_corruption_controls':controls,'own_timed_baseline_672_CSR_ELF_joins':True,'baseline_normal_exit_claimed':False,'all10_kernel_instruction_bytes_equal_prior_P_only_packet':len(build['measured_kernel_bytes_equal_parent'])==10,'reference_role':'source_mechanism_validation_no_parameter_fit','hardware_contacted':False,'global_heldout_timings_consumed':False,'input_sha256':inputs}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 ready={'schema':'iris.overlap_completion_ready.v2','pass':True,'build':str(a.build.resolve()),'elf':str((a.build/'overlap.elf').resolve()),'ELF_sha256':build['elf_sha256'],'cases':168,'regions':168,'numeric_elements_per_run':19872,'matrix_readback_scope':'row0 of each4tiles;32wordsperrow inclzero-tail; otherMRFrowsnotread','vector_readback_scope':'everyactiveVLbytepluszero-padding','qualification':str(out/'report.json'),'qualification_sha256':sha(out/'report.json'),'corpus':str((a.build/'corpus.json').resolve()),'layout':str((a.build/'readback-layout.json').resolve()),'validator':str(Path(__file__).with_name('validate_console.py').resolve()),'reference_role':'new_source_mechanism_validation_not_global_holdout_or_fitting','timing_parameters_fitted':False,'hardware_contacted':False,'all_four_boundary_values_printed':True,'all_words_printed_after_last_measured_case':True,'single_active_hart_per_case':True,'input_sha256':inputs}
 (out/'ready.json').write_text(json.dumps(ready,indent=2)+'\n');print(json.dumps({'pass':True,'controls':len(controls),'ready':str(out/'ready.json'),'ready_sha256':sha(out/'ready.json')}))
if __name__=='__main__':main()
