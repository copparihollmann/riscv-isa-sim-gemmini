#!/usr/bin/env python3
"""Bind a fixed-model read-sharing behavior witness to actual memory residuals."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from memory_routes_current_audit_v2 import Elf

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--comparison',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    base=ROOT/'build/memory-routes-current-v1';elf=Elf(base/'memory-routes.elf');table,size=elf.symbol('experiments')
    corpus=json.loads((base/'corpus.json').read_text());indices={c['case_id']:i for i,c in enumerate(corpus['cases'])}
    report=json.loads((args.comparison/'report.json').read_text())
    if report.get('pass')is not True or report.get('parameter_fit_performed')is not False:raise ValueError('Fixed actual comparison required')
    for name,digest in report['artifact_sha256'].items():
        if sha(args.comparison/name)!=digest:raise ValueError('Comparison changed')
    rows=[json.loads(x)for x in (args.comparison/'regions.jsonl').read_text().splitlines()]
    # The exact compiled chase loop reloads c->n after every dependent LD.
    if elf.read(0x800004b8,2)!=bytes.fromhex('1062')or elf.read(0x800004ba,2)!=bytes.fromhex('584d'):
        raise ValueError('Actual LD chain / per-iteration LW28(a0) changed')
    cases=[]
    for row in rows:
        if(row['target'],row['pattern'],row['kind'],row['n'],row['mask'])==('dram','bank0','chase',257,7):
            address=table+64*indices[row['case_id']]+28
            d=row['actual_model_data_path_features']
            cases.append({**{k:row[k]for k in ('case_id','hart','trial_id','hardware_cycles','native_cycles','signed_error_percent')},
                'compiled_shared_n_address':address,'compiled_shared_n_cache_line':address&~63,
                'actual_model_data_features':d,'actual_model_Icache_features':row['actual_model_instruction_cache_features']})
    if len(cases)!=9:raise ValueError('Three harts times three matching repetitions required')
    for trial in range(3):
        values=[x for x in cases if x['trial_id']==trial]
        if len({v['compiled_shared_n_address']for v in values})!=1:raise ValueError('Expected same immutable metadata address across harts')
    paths=[Path(__file__).resolve(),ROOT/'timing/memory_routes_current_shared_read_probe_v1.cpp',ROOT/'timing/empirical_cache_v6.cpp',
        ROOT/'timing/empirical_cache_v6.hpp',ROOT/'timing/empirical_cache_v4.hpp',ROOT/'timing/empirical_cache_v2.hpp',ROOT/'timing/empirical_cache.hpp',
        base/'memory-routes.elf',base/'guest.c',base/'corpus.json',args.comparison/'report.json',args.comparison/'regions.jsonl',
        ROOT/'pipeline/riscv-isa-sim-fadd-shape-store-fixed-v1/riscv/iris_timing_adapter.cc',
        ROOT/'pipeline/riscv-isa-sim-fadd-shape-store-fixed-v1/riscv/iris_timing_adapter.h']
    before={str(x):sha(x)for x in paths}
    command=['g++','-std=c++20','-O2','-I'+str(ROOT/'timing'),str(paths[1]),str(paths[2]),'-o',str(out/'probe')]
    built=subprocess.run(command,capture_output=True);(out/'compile.stdout').write_bytes(built.stdout);(out/'compile.stderr').write_bytes(built.stderr)
    if built.returncode:raise ValueError('Behavior probe compile failed')
    result=subprocess.run([str(out/'probe')],capture_output=True);(out/'probe.stdout').write_bytes(result.stdout);(out/'probe.stderr').write_bytes(result.stderr)
    if result.returncode:raise ValueError('Behavior probe failed')
    proof=json.loads(result.stdout)
    if proof.get('pass')is not True or type(proof.get('checks'))is not int or proof['checks']<25:raise ValueError('Actual behavior controls incomplete')
    if any(sha(path)!=digest for path,digest in before.items()):raise ValueError('Source changed')
    result={'schema':'iris.memory_routes_current_structural_diagnosis.v1','pass':True,'parameter_fit_performed':False,
        'native_or_helper_source_changed':False,'global_heldout_timings_consumed':False,'hardware_contacted':False,
        'behavior_probe':proof,'actual_matched_triples':cases,'compiled_chase_loop':[
            {'pc':0x800004b8,'raw':0x6210,'instruction':'ld a2,0(a2)','role':'dependent target pointer'},
            {'pc':0x800004ba,'raw':0x4d58,'instruction':'lw a4,28(a0)','role':'same read-only case.n metadata on all active harts'}],
        'source_scope':'Exact source and generated kernel bytes are frozen; table remains read-only in this test.',
        'diagnosis':'Model CacheHistoryV6 chains overlapping reads and rejects private L1 hit fast paths while a foreign read is pending. This reproduces a possible shared-read serialization mechanism, not a hardware latency or complete native counterfactual proof.',
        'counterevidence':'Single-hart DRAM chase is typically underpredicted. No uniform additional DRAM latency can correct both these tails and the underpredicted cases.',
        'next_test':'A new optional ownership-aware read-hit model must preserve pending stores/misses, incomplete early-installed tags, same-hart order, and real shared-value publication; prove independent native controls and rerun this exact ELF before fitting.',
        'full_2pct_certified':False,'source_image_association_verified':False,'input_sha256':before,'compile_argv':command,
        'artifact_sha256':{f.name:sha(f)for f in out.iterdir()if f.is_file()}}
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'pass':True,'checks':proof['checks'],'output':str(out)}))


if __name__=='__main__':main()
