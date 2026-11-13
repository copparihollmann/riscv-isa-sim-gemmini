#!/usr/bin/env python3
"""Bind the derived Zephyr context ABI to source facts and actual guest evidence."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PIN='cd45a528d3bf81f9c7aa2a63f9fe512eee0881b0'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(path,*args):return subprocess.check_output(['git','-C',str(ROOT/path),*args])
def record():
    patch=ROOT/'zephyr/patches/0002-iris-vme-context.patch'
    if git('third_party/zephyr','rev-parse','HEAD').decode().strip()!=PIN or git('third_party/zephyr','status','--porcelain'):raise ValueError('Base Zephyr is not clean/pinned')
    if git('third_party/zephyr-iris','rev-parse','HEAD').decode().strip()!=PIN or git('third_party/zephyr-iris','diff','--binary','HEAD')!=patch.read_bytes():raise ValueError('Derived source differs from the explicit patch')
    snapshot_path=ROOT/'build/zephyr-primary-0c0fd778/manifest.json';snapshot=json.loads(snapshot_path.read_text())
    if snapshot.get('state')!='final_native_provenance_frozen' or snapshot.get('closure_unavailable'):raise ValueError('Native snapshot closure is incomplete')
    aliases={item['original_path']:item for item in snapshot['artifacts']}
    for item in aliases.values():
        if sha(item['snapshot_path'])!=item['sha256']:raise ValueError('Frozen model bytes changed')
    sources={
      'vector-save-restore':('third_party/zephyr-iris/arch/riscv/core/fpu.c','z_riscv_vstate_csr_save/restore, z_riscv_vstate_save/restore, arch_flush_local_fpu; read-write early-clobber cursor; mtype before vector copy; full tiles and forced VME save'),
      'ownership-api':('third_party/zephyr-iris/arch/riscv/core/iris_vme.c','iris_vme_enable: hart/mask/context validation, normal lazy-owner claim, explicit four-tile initialization'),
      'api-contract':('third_party/zephyr-iris/include/zephyr/arch/riscv/iris_vme.h','explicit first-use initialization, allowed harts and caller obligations'),
      'tile-serialization':('third_party/zephyr-iris/arch/riscv/core/iris_vme_tiles.S','full_tile_config and 4 tiles x32 rows x128-byte bit-copy'),
      'matrix-readable-configuration':('third_party/rocket-chip/src/main/scala/rocket/CSR.scala','read_vtype/read_mtype: widenDecode(vtwiden) | (tk<<5) | (tm<<10)'),
      'matrix-configuration-restore':('third_party/rocket-chip/src/main/scala/rocket/Matrix.scala','msetmtypeNewType clears geometry; update sets TN/TM/TK with source clamps'),
      'tile-storage':('third_party/saturn/src/main/scala/exu/OuterProductUnit.scala','OPUParameters nMrfRegs=4, cWidth=32; TE=VLEN/8; regs=Reg(Vec(...)) without reset initialization'),
      'matrix-supported-configurations':('third_party/saturn/src/main/scala/common/Parameters.scala','opuMatrixTypes=(8,4),(32,1); opuTE=vLen/8'),
      'instruction-encodings':('third_party/saturn/benchmarks/common/vme.h','OP-V0x57 configuration/zero/row-move; OP-VE0x77 INT8/FP8; TSS row indexing'),
      'undefined-read-policy':('build/zephyr-primary-0c0fd778/final-source-snapshot/spike/iris.patch','Exact tested native overlay, riscv/vector_unit.h iris_cell: reads refused until explicitly written; no OS context magic'),
      'thread-affinity':('third_party/zephyr-iris/kernel/cpu_mask.c','initialized VME threads reject masks outside compute harts0/1'),
      'lazy-recognition':('third_party/zephyr-iris/arch/riscv/core/isr.S','CONFIG_RISCV_IRIS_VME_CONTEXT adds OP-VE0x77 and mtype0xc23'),
      'ordinary-smp-flush':('third_party/zephyr-iris/arch/riscv/core/fpu.c','flush_owned_fpu uses existing remote flush IPI before migration restore'),
    }
    facts={name:{'path':path,'sha256':sha(ROOT/path),'locator':locator} for name,(path,locator) in sources.items()}
    reports={
      'ordinary-base':'build/zephyr-context-base-certified-run/results.json',
      'ordinary-derived':'build/zephyr-context-vme-aware-certified-run/results.json',
      'competing-vme':'build/zephyr-vme-context-certified-run/results.json',
      'mixed-app':'build/zephyr-mixed-vme-mask7-final-run/results.json',
      'scalar-placements':'build/zephyr-placements-ownership/results.json',
      'host-protocol-negatives':'build/zephyr-negative-validation-ownership-checked/results.json',
      'omitted-ownership':'build/zephyr-vme-ownership-negative-run/negative-results.json',
      'omitted-kernel-tile-restore':'build/zephyr-no-tile-restore/run/negative-results.json',
      'latest-native-context-corpus':'build/zephyr-context-suite-current/results.json',
      'real-mlir-zephyr-gates':'zephyr/compiler-acceptance.json',
    }
    rows={}
    for name,path in reports.items():
        data=json.loads((ROOT/path).read_text())
        if not data['status'].startswith('passed'):raise ValueError('Failed context evidence: '+name)
        if 'input_sha256' in data:
            for p,digest in data['input_sha256'].items():
                actual=(ROOT/path).parent/'runner-source.py' if p in ('zephyr/context_run.py','zephyr/vme_context_run.py') else ROOT/p
                if sha(actual)!=digest:raise ValueError('Context evidence input changed: '+p)
        if 'stdout_sha256' in data:
            for stream in ('stdout','stderr'):
                if sha((ROOT/path).parent/stream)!=data[stream+'_sha256']:raise ValueError('Guest output changed')
        if 'run_receipt_sha256' in data and sha((ROOT/path).parent/'results.json')!=data['run_receipt_sha256']:raise ValueError('Negative evidence changed')
        for child in data.get('reports',[]):
            child_path=ROOT/child['path']
            if sha(child_path)!=child['sha256']:raise ValueError('Context corpus child changed')
            child_data=json.loads(child_path.read_text())
            if not child_data['status'].startswith('passed'):raise ValueError('Context corpus child failed')
            if 'run_receipt_sha256' in child_data:
                child_path=child_path.parent/'results.json'
                if sha(child_path)!=child_data['run_receipt_sha256']:raise ValueError('Negative corpus run changed')
                child_data=json.loads(child_path.read_text())
            for name,digest in child_data.get('input_sha256',{}).items():
                artifact=child_path.parent/'runner-source.py' if name in ('zephyr/context_run.py','zephyr/vme_context_run.py') else ROOT/name
                if not artifact.is_file() or sha(artifact)!=digest:
                    item=aliases.get(str(ROOT/name))
                    if not item or item['sha256']!=digest or sha(item['snapshot_path'])!=digest:raise ValueError('Context corpus input unavailable: '+name)
        rows[name]={'path':path,'sha256':sha(ROOT/path),'status':data['status']}
    repos={}
    for name in ('chipyard','saturn','rocket-chip','shuttle','zephyr'):
        path='third_party/'+name
        repos[name]={'commit':git(path,'rev-parse','HEAD').decode().strip(),'tracked_diff_sha256':hashlib.sha256(git(path,'diff','--binary','HEAD')).hexdigest()}
    model=json.loads(Path(snapshot['provenance_snapshot']['path']).read_text())
    repos['riscv-isa-sim']={'commit':model['upstream_spike_sha'],'applied_patch_sha256':model['target_patch_sha256'],'binary_sha256':model['binary_sha256'],'provenance_sha256':snapshot['provenance_snapshot']['sha256']}
    return {'schema_version':1,'status':'passed_functional_context_abi','generator_sha256':sha(Path(__file__)),
      'repositories':repos,'hardware_repository_state_is_current_workspace_observation':True,'model_under_test_snapshot':str(snapshot_path.relative_to(ROOT)),'model_under_test_snapshot_sha256':sha(snapshot_path),'base_zephyr_sha':PIN,'cumulative_patch_sha256':sha(patch),'fact_sources':facts,'evidence':rows,
      'architectural_state':{'fp_registers':32,'fp_max_register_bits':64,'fcsr':True,'vector_registers':32,'vector_register_bits':256,'vector_csrs':['vstart','vl','vtype(including-altfmt)','vcsr'],'vlenb_checked':32,'matrix_csr':'mtype0xc23: widen/TK/TM; VL holds TN','tile_shape':[4,32,32],'tile_cell_bits':32,'tile_bytes_per_initialized_thread':16384},
      'ownership_policy':{'explicit_api':'iris_vme_enable','initialization':'software zeros all four complete tiles before first use','allowed_harts':[0,1],'migration':'between harts0/1 with existing SMP remote-owner flush','hart2':'ordinary FP/RVV, VME API refused and initialized VME task placement rejected','interrupt_vme':False,'unregistered_vme_supported':False,'simulator_automatic_tile_context':False},
      'ordinary_rvv_constraint':{'base_defect':'assembly mutates input-only cursor','fix':'separate +&r cursor; preserve original context pointer','base_gcc16_miscompile_observed':False,'baseline_and_derived_full_register_checks_each':72},
      'functional_context_validated':True,'rtl_certified':False,'fpga_certified':False,'timing_certified':False,
      'remaining':['RTL/FPGA context test and deployed image association','Hardware asynchronous OPU drain/ordering validation','Calibrated context-switch/memory cost and held-out cycle accuracy','FP8 numerical edge certification is separate from exact context examples']}
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--verify',action='store_true');a=p.parse_args();data=record();path=ROOT/'zephyr/context-audit.json'
    if a.verify:
        if json.loads(path.read_text())!=data:raise ValueError('Context audit is stale')
    else:path.write_text(json.dumps(data,indent=2)+'\n')
    print(json.dumps({'status':data['status'],'reports':len(data['evidence']),'rtl_certified':False}))
if __name__=='__main__':main()
