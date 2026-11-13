#!/usr/bin/env python3
"""Stage a relocatable SDK4 source/binary/provider bundle; never publish primary."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('sdk4_builder',HERE/'build.py');builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
sha=builder.sha

def main():
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--rebuild',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--jobs',type=int,default=8)
    a=parser.parse_args();rebuild_path=a.rebuild.resolve();r=json.loads(rebuild_path.read_text());workspace=rebuild_path.parent/'workspace'
    if not(r['binary_byte_identical']and r['uart_byte_identical']and r['binary_sha256']==builder.BINARY_SHA and r['uart_sha256']==builder.UART_SHA):
        raise ValueError('Different native byte epoch requires new gates; no package staged')
    frozen=ROOT/'build/combined-frozen-35901887';companion=ROOT/'build/combined-os-acceptance-v1'
    if sha(frozen/'manifest.json')!=builder.FROZEN_SHA or sha(companion/'report.json')!='0d690772b1708e548add3afba012b8fa39fd8ae17c3497c2dd51eafb97eaf9fe':raise ValueError('Wrong reference proof closure')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    for name in ['build.py','provider.py','launch.py','README.md']:shutil.copyfile(HERE/name,out/name)
    (out/'launch.py').chmod(0o755)
    shutil.copyfile(frozen/'source-overlay.patch',out/'iris.patch')
    evidence=out/'evidence';evidence.mkdir();shutil.copytree(frozen,evidence/'combined');shutil.copytree(companion,evidence/'os')
    shutil.copyfile(rebuild_path,evidence/'rebuild.json')
    shutil.copyfile(rebuild_path.parent/'build-executed.py',evidence/'initial-build-executed.py')
    if sha(evidence/'initial-build-executed.py')!=r['builder_sha256']:raise ValueError('Executed rebuild helper differs')
    correction=ROOT/'build/combined-sdk4-rebuild-v1/inspection-correction.json'
    shutil.copyfile(correction,evidence/'inspection-correction.json')
    snapshot=out/'source';lock={}
    inputs=dict(r['source_input_sha256']);inputs.update(r['restored_frozen_input_sha256'])
    for name,value in sorted(inputs.items()):
        original=workspace/name
        if sha(original)!=value:raise ValueError('Rebuilt source input changed: '+name)
        target=snapshot/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,target);lock[name]=value
    source_lock={'schema':'iris.combined_sdk4.source_lock.v1','base_commit':builder.PIN,'source_overlay_sha256':builder.OVERLAY_SHA,
        'frozen_manifest_sha256':builder.FROZEN_SHA,'native_device_abi':4,'historical_repository_root':str(ROOT),'input_sha256':lock}
    (out/'source-lock.json').write_text(json.dumps(source_lock,indent=2)+'\n')
    second=out.with_name(out.name+'-source-rebuild')
    command=[sys.executable,str(out/'build.py'),'--output',str(second),'--jobs',str(a.jobs)]
    with (evidence/'package-rebuild.log').open('wb')as stream:
        result=subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT)
    if result.returncode:raise ValueError('Packaged source rebuild failed; preserve outputs')
    rebuilt=json.loads((second/'rebuild.json').read_text())
    if not(rebuilt['binary_byte_identical']and rebuilt['uart_byte_identical']):raise ValueError('Packaged source rebuild produced a new byte epoch')
    shutil.copyfile(second/'rebuild.json',evidence/'packaged-rebuild.json')
    binary_root=Path(rebuilt['build']);(out/'bin').mkdir()
    for name in ['spike','libsifive_uart.so']:shutil.copy2(binary_root/name,out/'bin'/name)
    sdk=out/'sdk';sdk.mkdir()
    for name in ['riscv','fesvr','fdt']:(sdk/name).symlink_to('../source/third_party/riscv-isa-sim-combined/'+name,target_is_directory=True)
    shutil.copyfile(binary_root/'config.h',sdk/'config.h')
    (sdk/'ABI').write_text('iris_device_clock_abi_v4\n')
    board=out/'board';board.mkdir()
    shutil.copyfile(snapshot/'board/evidence/bootrom.rv64.img',board/'bootrom.rv64.img')
    shutil.copyfile(snapshot/'board/build/iris.dtb',board/'iris.dtb')
    capsule=json.loads((frozen/'manifest.json').read_text());legacy=json.loads(builder.frozen_bytes(frozen,capsule['files']['build/snapshot-5e6cc309/provenance.json']))
    launch=legacy['launch_isa'];coverage=legacy['datatype_coverage']
    coverage.update(schema_version=2,status='experimental-source-policy-and-knownness-subsets',all_instructions_certified=False,
        source_capability_audit='source/hardware/dtypes.json',knownness_tracking=True,
        validation_scope='32 guest cases + five real handler/oracle groups, typed unknown controls,19combined groups; separate exact-byte positive OS/compiler companion')
    selftest=out/'selftest';selftest.mkdir()
    smoke=builder.frozen_bytes(frozen,capsule['files']['benchmarks/build/smoke.elf']);(selftest/'smoke.elf').write_bytes(smoke)
    args=[str(out/'launch.py'),'--iris-vme','--isa='+launch['2'],'-p3',
        '-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000',
        *['--hart-isa='+str(h)+':'+launch[str(h)]for h in range(3)],'--extlib='+str(out/'bin/libsifive_uart.so'),
        '--device=sifive_uart,0x10020000','--iris-bootrom='+str(board/'bootrom.rv64.img'),'--dtb='+str(board/'iris.dtb'),str(selftest/'smoke.elf')]
    env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']);start=time.monotonic()
    run=subprocess.run(args,capture_output=True,timeout=60,env=env)
    (selftest/'stdout').write_bytes(run.stdout);(selftest/'stderr').write_bytes(run.stderr)
    rows=[json.loads(line.split(b' ',1)[1])for line in run.stdout.splitlines()if line.startswith(b'IRIS_REGION ')]
    original=json.loads(builder.frozen_bytes(frozen,capsule['files']['build/combined-functional/results.json']))
    expected_smoke=json.loads(builder.frozen_bytes(frozen,capsule['files']['build/combined-functional/smoke.stdout']).split(b'IRIS_REGION ',1)[1].splitlines()[0])
    expected_rows=[json.loads(line.split(b' ',1)[1])for line in builder.frozen_bytes(frozen,capsule['files']['build/combined-functional/smoke.stdout']).splitlines()if line.startswith(b'IRIS_REGION ')]
    checksum=lambda rs:{(v['case_id'],v['region'],v['hart']):v['checksum']for v in rs}
    passed=run.returncode==0 and len(rows)==12 and{v['hart']for v in rows}=={0,1,2}and all(v.get('pass')is True for v in rows)and checksum(rows)==checksum(expected_rows)
    test={'pass':passed,'scope':'three-hart-int8-smoke','binary_sha256':sha(out/'launch.py'),
        'native_binary_sha256':sha(out/'bin/spike'),'uart_sha256':sha(out/'bin/libsifive_uart.so'),
        'argv':args,'returncode':run.returncode,'region_count':len(rows),'rows':rows,'host_seconds':time.monotonic()-start,
        'stdout_sha256':sha(selftest/'stdout'),'stderr_sha256':sha(selftest/'stderr'),'expected_checksums_from_frozen_combined_guest_evidence':True}
    (selftest/'results.json').write_text(json.dumps(test,indent=2)+'\n')
    if not passed:raise ValueError('Fresh packaged physical three-hart smoke failed')
    hardware=json.loads((snapshot/'hardware/manifest.json').read_text());facts=hardware['facts']
    per_hart={str(h):{'core':'Shuttle'if h<2 else'Rocket','vlen_bits':256,'dlen_bits':128 if h<2 else 256,
        'matrix_unit':h<2,'tcm_bytes':131072 if h<2 else 0,'launch_isa':launch[str(h)],
        'hardware_isa':facts['harts'][h]['value']['isa'],'hardware_isa_evidence':facts['harts'][h]['evidence']}for h in range(3)}
    provenance={'schema':'iris.combined_sdk4.package.v1','status':'experimental_functional_ready','mode':'explicit_experimental_functional',
        'upstream_spike_sha':builder.PIN,'target_patch_sha256':builder.OVERLAY_SHA,'binary_sha256':builder.BINARY_SHA,
        'device_binary_sha256':builder.UART_SHA,'native_device_abi':4,'launch_isa':launch,'per_hart':per_hart,
        'isa_extensions':['zfh','zvfh','zba','zbb','zbs','zvbb','zvt32t','zvti8i32mm','zvtofp8fmm','zvfofp8min','zvfbfmin','zvfbfa'],
        'datatype_coverage':coverage,'memory_regions':[[0x70000000,0x40000],[0x80000000,0x100000000],[0x580000000,0x20000]],
        'hardware_source_repositories':hardware['repositories'],'hardware_manifest_sha256':sha(snapshot/'hardware/manifest.json'),
        'functional_policies':{'reset':'unreset XPR/FPR/VRF/predicate/FCSR/tile/RAM bits retain unknown shadow masks',
            'transport':'opaque copies, spill/reload, per-bit masks, tile and shared canonical RAM preserve knownness',
            'observation':'unknown required arithmetic/control/address/CSR bits terminate with IRIS_UNDEFINED_STATE naming hart,PC,unit and masks',
            'fatal':'configured IRIS_FATAL_PCS/known guest fatal entries terminate nonzero with hart,PC,cause/EPC/tval; arbitrary guest trap handlers can be valid and are not automatically fatal',
            'all_harts':'heterogeneous ISA overrides; CLINT/PLIC/atomics and tested Zephyr timer/preemption/context paths',
            'configured_csrs':'hardware HPM count0; rdtime illegal; CLINT mtime MMIO is the timer; source per-core writable counter read phase and FS/VCSR/FCSR policy'},
        'limitations':['Full bit-exact coverage is not certified; source-policy conversion/div/sqrt and architecture breadth remain incomplete.',
            'Hart2 Rocket CEASE halting-until-reset is an explicit capability refusal.',
            'Column matrix move-out has no configured OPU readout datapath and is explicitly refused.',
            'Hart2 has integer/vector IEEE H/S/D execution; matrix/Mx BF16/OFP8 arithmetic is not advertised.',
            'No global zero-reset claim; unknown observations fail closed. Complete knownness coverage is not certified.',
            'Default functional mcycle is not calibrated performance time. The optional source scalar pipeline/serialized-other-operation fixture is experimental.',
            'Caches/frontend/memory/vector/VME timing and end-to-end +/-2% remain unqualified; no loaded FPGA image association.'],
        'evidence':{'local_groups':19,'functional_guests':32,'handler_groups':5,'source_closure_sha256':builder.FROZEN_SHA,
            'root_os_companion_sha256':'0d690772b1708e548add3afba012b8fa39fd8ae17c3497c2dd51eafb97eaf9fe','positive_os_groups':7,'captured_profile_regions':9},
        'rtl_certified':False,'timing_calibrated':False,'held_out_2pct':False,'deployed_image_association_verified':False,
        'full_knownness_certified':False,'full_zephyr_or_model_certified':False,'primary_modified':False}
    provenance['input_sha256']={str(path.relative_to(out)):sha(path)for path in out.rglob('*')if path.is_file()and not path.is_symlink()}
    (out/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    spec=importlib.util.spec_from_file_location('packaged_sdk4_provider',out/'provider.py');provider=importlib.util.module_from_spec(spec);spec.loader.exec_module(provider)
    selected=provider.experimental_functional_simulator()
    if selected.get('available')is not True:raise ValueError(selected.get('reason'))
    merlin={'schema':'iris.experimental_simulator.v1','binary':selected['binary'],'binary_sha256':selected['binary_sha256'],
        'native_binary_sha256':builder.BINARY_SHA,
        'model_provider':str(out/'provider.py'),'source_identity':{'spike_base':builder.PIN,'patch_sha256':builder.OVERLAY_SHA,
            'hardware_manifest_sha256':provenance['hardware_manifest_sha256']},'isa_extensions':['zvt32t','zvti8i32mm'],
        'per_hart_isa':launch,'launch_args':selected['launch_args'],'memory_regions':selected['memory_regions'],
        'selftest':{'pass':True,'binary_sha256':selected['binary_sha256'],'scope':'three-hart-int8-smoke','receipt':str(selftest/'results.json')},
        'input_sha256':{str(out/name):sha(out/name)for name in ['provider.py','provenance.json','launch.py','bin/spike','bin/libsifive_uart.so',
            'board/bootrom.rv64.img','board/iris.dtb','selftest/results.json','selftest/stdout','selftest/stderr']},
        'rtl_certified':False,'timing_calibrated':False,'zephyr_smp_certified':False}
    (out/'merlin-manifest.json').write_text(json.dumps(merlin,indent=2)+'\n');print(out/'provenance.json')
if __name__=='__main__':main()
