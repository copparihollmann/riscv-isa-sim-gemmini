#!/usr/bin/env python3
"""Verify optional model admission, real generic-run smoke and typed refusals."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from spike import empirical_provider_rvv7108_v1 as p
from benchmarks.validate_console import validate

def check(model,smoke,output):
    model,smoke,output=[Path(x).resolve()for x in (model,smoke,output)]
    output.mkdir(parents=True,exist_ok=False)
    before=p.sha(model);base=p.document(model);controls=[]
    selected=p.experimental_empirical_simulator(model)
    p.need(selected.get('available')is True,'Actual package unavailable')
    def refuse(name,change,expected):
        value=copy.deepcopy(base);change(value);path=output/(name+'.json')
        path.write_text(json.dumps(value,indent=2)+'\n')
        result=p.experimental_empirical_simulator(path)
        p.need(result.get('available')is False and expected in result.get('reason',''),'Wrong refusal for '+name+': '+str(result))
        controls.append(dict(name=name,pass_=True,reason=result['reason'],manifest=str(path),sha256=p.sha(path)))
        return path
    for key in ('native_binary','uart_library','fixture','binary','bootrom','dtb'):
        refuse('digest-'+key,lambda d,key=key:d['input_sha256'].__setitem__(d[key],'0'*64),'Changed model input')
    for key in ('parameters','fit_plan','runtime_QA','compiler','Zephyr','smoke_time','fatal','replay'):
        refuse('digest-evidence-'+key,lambda d,key=key:d['input_sha256'].__setitem__(d['evidence'][key],'0'*64),'Changed model input')
    capsule=ROOT/'build/warm-OPU-frozen-7108a6ec-v1'
    refuse('removed-source-archive',lambda d:d['input_sha256'].pop(str(capsule/'native-source.tar.gz')),'Changed model input')
    fatal=p.document(ROOT/p.EVIDENCE['fatal'][0]);raw=next(iter(fatal['output_sha256']))
    refuse('removed-raw-fatal-proof',lambda d:d['input_sha256'].pop(raw),'Changed model input')
    compiled=p.document(capsule/'compiled-inputs.json');header=next(k for k in compiled if k.endswith('.hpp'))
    refuse('removed-compiled-header',lambda d:d['input_sha256'].pop(header),'Changed model input')
    refuse('hart2-matrix-role',lambda d:d['per_hart_isa'].__setitem__('2',p.COMPUTE_ISA),'Fixed real three-hart')
    refuse('certification-escalation',lambda d:d['qualification'].__setitem__('accuracy_2percent_certified',True),'Unqualified experimental scope')
    refuse('extra-launch-override',lambda d:d['launch_args'].append('--isa=rv64gc'),'Fixed boot/device/fixture')
    refuse('wrong-epoch',lambda d:d.__setitem__('package_kind','generic-fit'),'Only fixed fitted7108')
    # Corrupt a new copy, never any source/native/runtime evidence already bound.
    source=Path(base['fixture']);changed=output/'changed.fixture'
    changed.write_bytes(source.read_bytes()+b'\n# byte corruption control\n')
    bad=refuse('actual-changed-file',lambda d:d['input_sha256'].__setitem__(str(changed),p.CORE['fixture'][1]),'Changed model input')
    for name,text,want in [
        ('duplicate-field','{"schema":"iris.empirical_simulator.v1","schema":"x"}','Duplicate JSON key'),
        ('nonfinite','{"x":NaN}','Nonfinite JSON')]:
        path=output/(name+'.json');path.write_text(text)
        result=p.experimental_empirical_simulator(path)
        p.need(result.get('available')is False and want in result.get('reason',''),'Typed JSON refusal missing')
        controls.append(dict(name=name,pass_=True,reason=result['reason']))
    old=os.environ.get('LD_PRELOAD')
    try:
        os.environ['LD_PRELOAD']='not-loaded-provider-control.so'
        result=p.experimental_empirical_simulator(model)
        p.need(result.get('available')is False and 'Loader overrides'in result['reason'],'Loader override accepted')
        controls.append(dict(name='loader-override',pass_=True,reason=result['reason']))
    finally:
        if old is None:os.environ.pop('LD_PRELOAD',None)
        else:os.environ['LD_PRELOAD']=old
    # The real generic runner must reject corrupted evidence before native exec.
    argv=[sys.executable,'-m','iris_model.empirical_run','--model',str(bad),
          '--elf',str(ROOT/'benchmarks/build/smoke.elf'),'--output',str(output/'generic-refusal'),'--timeout','30']
    got=subprocess.run(argv,cwd=ROOT,capture_output=True,timeout=30)
    (output/'generic-refusal.stdout').write_bytes(got.stdout)
    (output/'generic-refusal.stderr').write_bytes(got.stderr)
    refused=p.document(output/'generic-refusal/run.json')
    p.need(got.returncode!=0 and refused['status']=='refused_or_failed' and 'pid'not in refused,'Generic runner executed corrupt model')
    controls.append(dict(name='real-generic-run-preexec-refusal',pass_=True,returncode=got.returncode))
    run=p.document(smoke/'run.json')
    p.need(run.get('pass')is True and run.get('exit_status')==0 and run.get('timed_out')is False and run.get('fixture_sha256')==p.CORE['fixture'][1],'Actual normal generic-run smoke required')
    p.need(run.get('input_sha256',{}).get(str(model))==before,'Smoke used another descriptor')
    checked=validate((smoke/'stdout').read_text(),p.document(ROOT/'benchmarks/calibration-corpus.json'),3,True)
    summary=p.document(smoke/'native-summary.json');retired=summary.get('retired_instructions')
    p.need(isinstance(retired,list)and len(retired)==3 and all(type(v)is int and v>0 for v in retired),'All three harts must actually retire instructions')
    p.need(p.sha(model)==before and p.experimental_empirical_simulator(model)['available'],'Original package changed during controls')
    report=dict(schema='iris.optional_rvv7108_admission_controls.v1',**{'pass':True},
        actual_generic_run_normal_exit_verified=True,three_hart_independent_smoke=checked,
        retired_instructions=retired,host_seconds=run['host_seconds'],
        simulated_MIPS=sum(retired)/run['host_seconds']/1e6,
        controls=[{('pass'if k=='pass_'else k):v for k,v in c.items()}for c in controls],
        hardware_contacted=False,provider_or_default_promoted=False,timing_accuracy_certified=False,
        input_sha256={str(q):p.sha(q)for q in (Path(__file__).resolve(),Path(p.__file__),model,smoke/'run.json',smoke/'stdout',smoke/'stderr',smoke/'features.jsonl',smoke/'native-summary.json',ROOT/'benchmarks/validate_console.py',ROOT/'benchmarks/calibration-corpus.json')})
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

if __name__=='__main__':
    a=argparse.ArgumentParser(__doc__);a.add_argument('--model',type=Path,required=True);a.add_argument('--smoke',type=Path,required=True);a.add_argument('--output',type=Path,required=True);v=a.parse_args()
    result=check(v.model,v.smoke,v.output);print(json.dumps({'pass':result['pass'],'controls':len(result['controls'])}))
