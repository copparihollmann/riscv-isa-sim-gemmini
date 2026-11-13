#!/usr/bin/env python3
"""Finite positive generic-service sweep, selected only by TRAIN live counters."""
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    original=ROOT/'calibration/compute-fit-fadd-shape-7de-initial-v1'
    model=ROOT/'build/fadd-shape-frozen-7de1c02d'
    out=ROOT/'calibration/compute-fit-fadd-shape-7de-sweep-v1';out.mkdir(exist_ok=False)
    candidates=[]
    for read in (0,8,16,32):
        for miss in (0,6,16):
            name='read'+str(read)+'-miss'+str(miss)
            where=out/name;where.mkdir();params=json.loads((original/'parameters.json').read_text())
            identity='iris-compute-fadd-shape-7de-'+name+'-v1'
            params.update(calibration_identity=identity,scalar_read_service=read,scalar_L1_miss_service=miss,
                          vector_load_service=20,selection_scope='Finite positive runtime service grid; actual TRAIN replay required; no CV selection.',
                          generic_scalar_DRAM_extra_costs_fitted=True)
            (where/'parameters.json').write_text(json.dumps(params,indent=2,sort_keys=True)+'\n');digest=sha(where/'parameters.json')
            lines=[]
            for line in (original/'runtime.fixture').read_text().splitlines():
                f=line.split()
                if f and f[0]=='empirical_profile':f[2]=identity
                if f and f[0]=='empirical_cache_service':f[2]=str(read);f[4]=str(miss)
                if f and f[0]in ('empirical_family','empirical_cache_service','empirical_branch_service','empirical_instruction_service'):
                    if 'UNIDENTIFIED'not in f[-3]:f[-2]=digest
                    if f[0]=='empirical_cache_service':f[-3]='OWN_7DE_TRAIN_GENERIC_SERVICE_CANDIDATE';f[-2]=digest
                lines.append(' '.join(f)if f else '')
            for h in range(3):
                resource='fit.compute.vector-load'+str(h)
                lines.extend(['resource '+resource+' 1',f'empirical_family {h} memory.vector.load {resource} 20 0 1 OWN_7DE_TRAIN_GENERIC_SERVICE_CANDIDATE {digest} core_cycles'])
            (where/'runtime.fixture').write_text('\n'.join(lines)+'\n');candidates.append((name,where))
    def worker(item):
        name,where=item;replay=ROOT/('build/compute-fit-fadd-shape-7de-sweep-'+name+'-v1')
        features=ROOT/('build/compute-fit-features-fadd-shape-7de-sweep-'+name+'-v1')
        evaluate=where/'evaluation'
        commands=[
            [sys.executable,str(ROOT/'benchmarks/compute_fit/replay.py'),'--build',str(ROOT/'build/compute-fit-v3'),'--native',str(model/'spike'),'--uart',str(model/'libsifive_uart.so'),'--fixture',str(where/'runtime.fixture'),'--output',str(replay),'--timeout','180'],
            [sys.executable,str(ROOT/'timing/empirical_compute_features_v2.py'),'--build',str(ROOT/'build/compute-fit-v3'),'--analysis',str(ROOT/'build/fpga-compute-fit-v1-001-analysis/report.json'),'--reference-run',str(ROOT/'runs/fpga-compute-fit-v1-001/run.json'),'--receipt',str(replay/'run.json'),'--regions',str(replay/'regions.jsonl'),'--features',str(replay/'features.jsonl'),'--output',str(features)],
            [sys.executable,str(ROOT/'timing/empirical_compute_evaluate_v1.py'),'--regions',str(features/'regions.jsonl'),'--output',str(evaluate)]]
        for i,argv in enumerate(commands):
            with(where/(str(i)+'.stdout')).open('w')as stdout,(where/(str(i)+'.stderr')).open('w')as stderr:
                code=subprocess.call(argv,stdout=stdout,stderr=stderr,cwd=ROOT)
            if code:return {'name':name,'pass':False,'failed_stage':i,'exit_status':code}
        report=json.loads((evaluate/'report.json').read_text())
        # No internal-validation metric is accessed by this selection code.
        return {'name':name,'pass':True,'train_objective':report['train_objective']['value'],
                'report':str(evaluate/'report.json'),'report_sha256':sha(evaluate/'report.json'),
                'fixture_sha256':sha(where/'runtime.fixture')}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:results=list(pool.map(worker,candidates))
    good=[r for r in results if r['pass']]
    result={'schema':'iris.fadd_shape_actual_training_sweep.v1','pass':len(good)==len(results),
        'selection_uses_internal_validation':False,'global_heldout_timings_consumed':False,
        'objective':'TRAIN parent/hart trial-median relative MSE, all fit-eligible families',
        'candidates':results,'selected':min(good,key=lambda x:(x['train_objective'],x['name']))if good else None,
        'no_runtime_ID_PC_or_reference_cycle_lookup':True,'native_sha256':sha(model/'spike'),
        'input_sha256':{str(p):sha(p)for p in (Path(__file__).resolve(),original/'parameters.json',original/'runtime.fixture',ROOT/'build/compute-fit-v3/split.json')}}
    (out/'selection.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if not result['pass']:raise SystemExit(1)


if __name__=='__main__':main()
