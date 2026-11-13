#!/usr/bin/env python3
"""Independently validate a normal selected-model exit; preserve raw run receipt."""
import argparse
import json
from pathlib import Path
from build import ROOT,sha
from validate import validate

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--run',type=Path,required=True);a=p.parse_args();b=a.build.resolve();out=a.run.resolve()
    r=json.loads((out/'run.json').read_text());c=json.loads((b/'corpus.json').read_text());report={'schema':'iris.memory_footprint_WFI_selected_model_qualification.v1','pass':False,'normal_guest_exit_verified':False,'timing_accuracy_certified':False,'new_exact_reference_required':True,'hardware_contacted':False,'error':None}
    try:
        if r['pass']is not True or r['status']!='passed_guest_exit'or r['exit_status']!=0 or r['timed_out']is not False:raise ValueError('Normal selected-model guest exit required')
        if r['ELF_sha256']!=sha(b/'footprints.elf'):raise ValueError('Selected run ELF mismatch')
        proof=validate((out/'stdout').read_text(),c)
        if (out/'stderr').read_bytes():raise ValueError('Selected model stderr not empty')
        summary=json.loads((out/'native-summary.json').read_text());retired=summary['retired_instructions'];cycles=summary['cycles']
        if len(retired)!=3 or any(type(n)is not int or n<=0 for n in retired)or type(cycles)is not int or cycles<=0:raise ValueError('Actual three-hart target counters required')
        rows=[json.loads(l[len('IRIS_REGION '):])for l in(out/'stdout').read_text().splitlines()if l.startswith('IRIS_REGION ')]
        for name,h in r['input_sha256'].items():
            if sha(name)!=h:raise ValueError('Model execution input changed: '+name)
        if any(sha(name)!=h for name,h in r['output_sha256'].items()):raise ValueError('Raw run output changed')
        report.update({'pass':True,'normal_guest_exit_verified':True,'numeric_proof':proof,'global_modeled_target_cycles':cycles,'retired_instructions_by_hart':retired,'retired_instructions_total':sum(retired),'host_seconds':r['host_seconds'],'actual_MIPS':sum(retired)/r['host_seconds']/1e6,'ROI_mcycle_delta_sum_by_hart':[sum(x['end_cycle']-x['start_cycle']for x in rows if x['hart']==h)for h in range(3)],'ROI_instret_delta_sum_by_hart':[sum(x['instret_delta']for x in rows if x['hart']==h)for h in range(3)],'per_hart_mcycle_not_global_elapsed':True,'IRQ_and_cache_history_changed':True})
    except(ValueError,KeyError,TypeError)as e:report['error']=str(e)
    paths=[Path(__file__).resolve(),b/'ready.json',b/'footprints.elf',b/'corpus.json',out/'run.json',*[out/n for n in('stdout','stderr','features.jsonl','native-summary.json')if(out/n).is_file()]];report['input_sha256']={str(p):sha(p)for p in paths}
    (out/'qualification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k)for k in('pass','normal_guest_exit_verified','global_modeled_target_cycles','retired_instructions_by_hart','host_seconds','actual_MIPS','error')}));raise SystemExit(0 if report['pass']else 1)

if __name__=='__main__':main()
