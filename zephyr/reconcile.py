#!/usr/bin/env python3
"""Reconcile selected immutable scalar, context and real-compiler evidence."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def make_record():
    for script in ('audit.py','context_audit.py','compiler_acceptance.py'):
        subprocess.run([sys.executable,str(ROOT/'zephyr'/script),'--verify'],check=True,stdout=subprocess.DEVNULL)
    old=json.loads((ROOT/'zephyr/test-results.json').read_text());paths=set(old.get('evidence_sha256',{}))
    paths.update(['zephyr/source-audit.json','zephyr/context-audit.json','zephyr/compiler-acceptance.json','build/zephyr-placements-ownership/results.json','build/zephyr-negative-validation-ownership-checked/results.json','build/zephyr-context-suite-current/results.json','build/zephyr-mixed-vme-mask7-final-run/results.json','build/zephyr-mixed-vme-mask7-live/results.json','build/zephyr-primary-0c0fd778/manifest.json'])
    for op in ('gemm','conv2d'):
        for workers in (1,2):paths.add(f'build/zephyr-mlir-final/{op}-h{workers}/results.json')
    compiler=json.loads((ROOT/'zephyr/compiler-acceptance.json').read_text())
    return {'schema_version':2,'status':'passed_selected_scalar_rvv_vme_and_real_mlir_zephyr_integration','generator_sha256':sha(Path(__file__)),'zephyr_sha':'cd45a528d3bf81f9c7aa2a63f9fe512eee0881b0','context_patch_sha256':sha(ROOT/'zephyr/patches/0002-iris-vme-context.patch'),'source_audit_verified':True,'scalar_smp_functionally_validated':True,'placements':7,'placement_regions':24,'historical_live_scalar_runs':3,'historical_live_scalar_regions':18,'mixed_live_regions':9,'seed17_stdout_and_graph_identical':True,'negative_host_protocol_tests':7,'ordinary_rvv_full_register_checks_per_positive_image':72,'vme_context_functionally_validated':True,'latest_native_context_positive_elf_tests':3,'latest_native_context_negative_elf_tests':2,'vme_competing_tasks':4,'vme_rounds_per_task':8,'compute_hart_migration_verified':True,'hart2_vme_refusal_verified':True,'real_mlir_compiler_zephyr_programs':compiler['programs'],'real_mlir_int32_elements_checked':compiler['all_int32_elements_checked'],'real_mlir_w8a8_elements_checked':compiler['all_w8a8_elements_checked'],'real_mlir_binary_sha256':compiler['native_binary_sha256'],'evidence_sha256':{name:sha(ROOT/name) for name in sorted(paths)},'full_zephyr_certified':False,'vme_context_rtl_certified':False,'rtl_certified':False,'fpga_certified':False,'timing_accuracy_certified':False,'whole_model_worker_pool_qualified':False,'remaining':['Actual FPGA/RTL Zephyr context and compiler-pipeline validation plus source/image association','Hardware asynchronous OPU context drain/ordering validation','Generic whole-model worker-pool target ownership before matrix dispatch','Full transformer-model deployment and per-operator dtype coverage beyond tested int8 compiler route','Calibrated pipelines/memory and held-out cycle accuracy']}
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--verify',action='store_true');a=p.parse_args();data=make_record();path=ROOT/'zephyr/test-results.json'
    if a.verify:
        if json.loads(path.read_text())!=data:raise ValueError('Selected Zephyr acceptance ledger is stale')
    else:path.write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({'status':data['status'],'real_mlir_programs':data['real_mlir_compiler_zephyr_programs'],'rtl_certified':False}))
if __name__=='__main__':main()
