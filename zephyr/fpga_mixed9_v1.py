#!/usr/bin/env python3
"""Preserved mixed9 ELF source/context/golden qualification; no target rebuild."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
PIN='cd45a528d3bf81f9c7aa2a63f9fe512eee0881b0'
PATCH='558cefc2f57225774cc891e1df0d2f7149f6e834a7012b4c0735f0fba0d1aa1b'
ELF='93a52d8935e6e0a3d63a88ded86f44f2802cfceb4e0f919d4e272bb56567a306'
PROFILE={'requested_baud':3676470,'clock_hz':500000000,'divisor':135}


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
    if not ok:raise ValueError(msg)
def host_cases():
    # Independently count row-strided M16N16K16 and valid 6x6 3x3 convolution.
    return [dict(id='zephyr.gemm16',active_harts=[0,1,2],region='kernel',expected_checksums_by_hart=[len(range(h,16,3))*16*16 for h in range(3)]),
            dict(id='zephyr.conv2d8',active_harts=[0,1,2],region='kernel',expected_checksums_by_hart=[len(range(h,6,3))*6*9 for h in range(3)]),
            dict(id='zephyr.vme.yield',active_harts=[0,1,2],region='kernel',expected_checksums_by_hart=[32*32,32*32,32*32])]

def binary_proof(path):
    sys.path.insert(0,str(ROOT/'timing'));from fp8_format_functional_audit_v1 import Elf
    e=Elf(path);need(sha(path)==ELF,'Exact preserved mixed9 ELF')
    expected={0x8000062e:(4,0x02000b13),0x80000640:(4,0x43e06057),0x80000644:(4,0x02090407),0x80000648:(4,0x02090807),0x8000064c:(4,0xf2880077),0x80000650:(2,0x3b7d),0x80000652:(4,0x6e7060ef),0x80000656:(4,0xfe0b1be3),0x8000066e:(4,0x43fb6c57),0x80000672:(4,0x020aec27),0x80000676:(4,0x0330000f),0x80000770:(4,0x02000c93),0x80000778:(4,0x0c0b7057),0x8000077c:(4,0x02090407),0x80000780:(4,0x5b9060ef),0x80000784:(4,0x020a8427),0x80000788:(4,0x0330000f),0x8000079a:(2,0x3cfd),0x8000079c:(4,0xfc0c9ee3)}
    for pc,(n,w)in expected.items():need(int.from_bytes(e.read(pc,n),'little')==w,'Actual worker encoding '+hex(pc))
    # Parse actual instruction boundaries rather than searching unaligned bytes.
    def words(symbol):
        need(len(e.symbols[symbol])==1,'Unique compiled function '+symbol);a,n=e.symbols[symbol][0];out=[];offset=0
        while offset<n:
            lo=int.from_bytes(e.read(a+offset,2),'little');size=4 if lo&3==3 else 2
            need(offset+size<=n,'Complete function instruction');out.append(int.from_bytes(e.read(a+offset,size),'little'));offset+=size
        return out
    save=words('z_riscv_vstate_save');restore=words('z_riscv_vstate_restore')
    need([w for w in save if w in [0x02078027,0x02078427,0x02078827,0x02078c27]]==[0x02078027,0x02078427,0x02078827,0x02078c27],'Compiled four m8 VRF save groups')
    need([w for w in restore if w in [0x02078007,0x02078407,0x02078807,0x02078c07]]==[0x02078007,0x02078407,0x02078807,0x02078c07],'Compiled four m8 VRF restore groups')
    need(0x0c307757 in save and 0x0c3076d7 in restore,'Compiled e8m8 VLmax context copying')
    for name in ['iris_vme_enable','z_iris_vme_tiles_zero','z_iris_vme_tiles_save','z_iris_vme_tiles_restore','z_riscv_vstate_csr_restore']:words(name)
    return dict(worker_instruction_checks=len(expected),compute_harts=[0,1],MM_format='unsigned8xunsigned8 into wrapping32, TK1',MM_commands_per_worker=32,MM_measured_output='tile0,row0,32word checksum32*32=1024; no fullMRF word comparison',hart2='ordinary e8m1 VL32 load/yield/store repeated32times, checksum32*32=1024; no VME execution/refusal',kernel_context_copy='four e8m8 groups v0/v8/v16/v24,1024bytes per fullVRF save/restore at VLEN256',context_runtime_limit='Compiled and source-bound availability; this app emits no actual save/restore/migration/IRQ counts and has one vector owner per hart')


def validate(text,require_driver_exit=False,wrapper=None):
    lines=text.splitlines();need(not any(x in text for x in ('IRIS_FATAL','ASSERTION FAIL','*** FAILED ***')),'Guest/driver fatal')
    profiles=[json.loads(x.split(' ',1)[1])for x in lines if x.startswith('IRIS_UART_PROFILE ')]
    need(profiles==[PROFILE]and all(type(v)is int for v in profiles[0].values()),'Actual Ethan UART DIV135 profile required')
    rows=[json.loads(x.split(' ',1)[1])for x in lines if x.startswith('IRIS_REGION ')]
    want=[(c,h,c['expected_checksums_by_hart'][h])for c in host_cases()for h in c['active_harts']]
    need(len(rows)==9,'Exact mixed9 region count');previous={}
    for r,(c,h,expected)in zip(rows,want):
        need(all(type(r.get(k))is int for k in ('hart','hart_mask','checksum','start_cycle','end_cycle','instret_delta')),'Typed actual region fields')
        need(r['case_id']==c['id']and r['region']=='kernel'and r['hart']==h and r['hart_mask']==7 and r['role']==('scalar.compute'if c['id']!='zephyr.vme.yield'else'vme.compute'if h<2 else'vector.copy'),'Actual SMP role/order')
        need(r['checksum']==expected,'Independent scalar numerical checksum')
        need(0<=r['start_cycle']<r['end_cycle']<2**64 and 0<r['instret_delta']<2**64 and r['start_cycle']>=previous.get(h,0),'Actual program counter boundaries')
        previous[h]=r['end_cycle']
    footer=[json.loads(x.split(' ',1)[1])for x in lines if x.startswith('IRIS_BATCH_DONE ')]
    need(footer==[{'failed':0}]and type(footer[0]['failed'])is int,'Exact existing guest completion protocol')
    if require_driver_exit:
        from script_envelope_v3 import validate_envelope
        need(wrapper is not None,'Actual captured sim-run wrapper required for driver proof')
        validate_envelope(text,wrapper)
    return dict(regions=9,case_count=3,harts=[0,1,2],all_independent_checksums_passed=True,
                normal_guest_protocol_completed=True,driver_exit_verified=require_driver_exit,
                UART_divisor_readback=PROFILE,
                interrupt_scope='Pinned workers each complete two1ms k_sleep calls and shared mutex/yield/semaphore work; no per-hart ISR/IPI counters are emitted.',
                HTIF_scope='Actual sys_arch_reboot writes success1; actual source-bound host script header/footer must also verify exit0',
                driver_exit_grammar='Actual dated util-linux script envelope and exact captured COMMAND; standalone/malformed markers refuse',
                vector_scope='One pinned VME owner on each compute hart;32yields/32unsignedINT8 TK1 operations and32-word row0 checksum. Hart2 ordinary32-byte vector copy/yield32iterations. No samehart competing owners, migration, explicit refusal or context-count claim',
                timing_certified=False)


def qualify(build,gates,output):
    sys.path.insert(0,str(ROOT/'timing'));from fp8_format_functional_audit_v1 import Elf
    build,output=Path(build).resolve(),Path(output).resolve();need(not output.exists(),'Fresh qualification output')
    record=json.loads((build/'build.json').read_text());elf=build/'zephyr/zephyr.elf'
    need(record['status']=='built'and record['zephyr_sha']==PIN and record['source_patch_sha256']==PATCH,'Pinned mixed Zephyr source with exact recorded context overlay')
    need(record['uart_profile']['name']=='ethan-firesim'and record['uart_profile']['expected_divisor']==135,'Ethan overlay build, not physical115200')
    need(sha(elf)==record['artifact_sha256']['zephyr/zephyr.elf']==ELF,'Successful exact build ELF')
    source=Path(record['source']);need(subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()==PIN,'Current source pin')
    diff=subprocess.check_output(['git','-C',str(source),'diff','--binary','HEAD']);need(hashlib.sha256(diff).hexdigest()==PATCH,'Exact current Iris VME context patch')
    need(not subprocess.check_output(['git','-C',str(source),'ls-files','--others','--exclude-standard']),'No unrecorded kernel source inputs')
    config={}
    for line in(build/'zephyr/.config').read_text().splitlines():
        if line.startswith('CONFIG_')and'='in line:k,_,v=line.partition('=');config[k]=v
    for k,v in {'CONFIG_SMP':'y','CONFIG_MP_MAX_NUM_CPUS':'3','CONFIG_IRIS_BENCH_WORKERS':'3','CONFIG_IRIS_BENCH_HART_MASK':'7','CONFIG_IRIS_BENCH_EXIT_ON_COMPLETION':'y','CONFIG_UART_HTIF':'y','CONFIG_UART_SIFIVE':'y','CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC':'500000'}.items():need(config.get(k)==v,'Required compiled configuration '+k)
    need(all(config.get(k)=='y'for k in ['CONFIG_RISCV_ISA_EXT_V','CONFIG_IRIS_BENCH_VME','CONFIG_RISCV_IRIS_VME_CONTEXT','CONFIG_FPU_SHARING'])and config.get('CONFIG_RISCV_VECTOR_MAX_LEN')=='256'and config.get('CONFIG_RISCV_PMP')!='y','Exact RVV/VME-context256b compiled configuration')
    inputs={str(Path(__file__).resolve()):sha(Path(__file__)),str(build/'build.json'):sha(build/'build.json')}
    for name,d in record['input_sha256'].items():p=ROOT/name;need(sha(p)==d,'OOT build source changed '+name);inputs[str(p)]=d
    for name,d in record['artifact_sha256'].items():p=build/name;need(sha(p)==d,'Compiled build artifact changed '+name);inputs[str(p)]=d
    # Retain actual compiled source/header dependency closure from Ninja, not a
    # claim that recording only app/CMake files captures the whole kernel.
    ninja=Path('/scratch/eygao/iris-cy/.conda-env/bin/ninja');deps=subprocess.check_output([str(ninja),'-C',str(build),'-t','deps'],text=True)
    depfiles=set()
    for line in deps.splitlines():
        if line.startswith('    '):
            p=Path(line.strip());p=p if p.is_absolute()else build/p
            need(p.is_file(),'Missing actual compiled dependency '+str(p));depfiles.add(p.resolve())
    need(len(depfiles)>100,'Actual kernel dependency closure')
    for p in depfiles:inputs[str(p)]=sha(p)
    inputs[str(ninja)]=sha(ninja)
    e=Elf(elf);symbols={n:e.symbols[n][0]for n in ('tohost','fromhost','sys_arch_reboot','main','worker')}
    need(all(len(e.symbols[n])==1 for n in symbols),'Unique runtime/HTIF symbols')
    tohost,sz=symbols['tohost'];need(sz==8 and tohost%8==0 and e.read(tohost,8)==bytes(8),'HTIF tohost file-backed64b zero')
    fromhost,sz=symbols['fromhost'];need(sz==8 and e.read(fromhost,8)==bytes(8),'HTIF fromhost file-backed zero')
    reboot,size=symbols['sys_arch_reboot'];raw=e.read(reboot,size)
    need(bytes.fromhex('85471ce3')in raw,'Compiled li1/store64 HTIF success path')
    compiler=Path(record['commands'][0]['argv'][0]).parent/'riscv-tools/bin/riscv64-unknown-elf-objdump'
    compiler=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-objdump')
    asm=subprocess.check_output([str(compiler),'-d','--disassemble=sys_arch_reboot',str(elf)],text=True);inputs[str(compiler)]=sha(compiler)
    sourcepaths=[source/'soc/rocketchip/virt_riscv/common/soc.c',source/'drivers/serial/uart_htif.c',source/'drivers/timer/riscv_machine_timer.c',source/'arch/riscv/core/smp.c',source/'arch/riscv/core/fpu.c',source/'arch/riscv/core/fpu.S',source/'arch/riscv/core/iris_vme.c',source/'arch/riscv/core/iris_vme_tiles.S',source/'include/zephyr/arch/riscv/iris_vme.h']
    for p in sourcepaths:inputs[str(p)]=sha(p)
    soc=sourcepaths[0].read_text();need('tohost = (uint64_t)((success << 1) | 1)'in soc and'int success = 0;'in soc,'Source HTIF success exit, not reset loop')
    body=binary_proof(elf)
    results=[]
    for gate in gates:
        gate=Path(gate).resolve();r=json.loads((gate/'results.json').read_text())
        need(r['status']=='passed_mixed_zephyr_smp'and r['exit_status']==0 and r['timed_out']is False and r['elf_sha256']==sha(elf),'Normal exact seeded ELF execution')
        need(sha(gate/'stdout')==r['stdout_sha256']and sha(gate/'stderr')==r['stderr_sha256'],'Seeded raw output binding')
        proof=validate((gate/'stdout').read_text(),False);results.append(dict(seed=r['seed'],report=str(gate/'results.json'),report_sha256=sha(gate/'results.json'),proof=proof))
        for p in [gate/'results.json',gate/'stdout',gate/'stderr']:inputs[str(p)]=sha(p)
    need(len(results)==2 and{x['seed']for x in results}=={0,17},'Both seeded functional schedules')
    output.mkdir(parents=True);(output/'inputs').mkdir()
    for name,d in inputs.items():
        saved=output/'inputs'/d
        if not saved.exists():shutil.copyfile(name,saved)
    (output/'source.patch').write_bytes(diff);(output/'compiled-dependencies.txt').write_text(deps);(output/'HTIF-exit-disassembly.txt').write_text(asm)
    for name in ['worker','z_riscv_vstate_save','z_riscv_vstate_restore','iris_vme_enable','z_iris_vme_tiles_save','z_iris_vme_tiles_restore']:
        text=subprocess.check_output([str(compiler),'-d','--disassemble='+name,str(elf)],text=True);(output/(name+'-disassembly.txt')).write_text(text)
    corpus=dict(schema='iris.Zephyr_mixed9_functional_corpus.v1',cases=host_cases(),regions=9,harts=[0,1,2],
                guest_protocol='Unchanged IRIS_REGION and IRIS_BATCH_DONE{failed:0}; no host-invented records',
                UART_profile=PROFILE,calibration_usable=False,heldout=False,functional_only=True)
    (output/'corpus.json').write_text(json.dumps(corpus,indent=2)+'\n')
    report=dict(schema='iris.Zephyr_mixed9_bringup_qualification.v1',**{'pass':True},ELF_sha256=sha(elf),build=str(build),build_receipt_sha256=sha(build/'build.json'),
                corpus_sha256=sha(output/'corpus.json'),functional=results,compiled_kernel_dependencies=len(depfiles),HTIF_symbols={k:dict(address=v[0],size=v[1])for k,v in symbols.items()},
                source_pin=PIN,source_overlay=PATCH,UART_profile=PROFILE,all_three_hart_worker_checksums=True,binary_proof=body,
                existing_hardware_scope='Scalar6 new5d hardware passed; original285 image repeatedly stopped after25. Mixed9 is separately admitted; no inherited RVV/context FPGA qualification.',
                no_new_perhart_interrupt_counters=True,FPGA_execution_performed=False,hardware_or_network_contacted=False,
                source_image_association_verified=False,timing_certified=False,input_sha256=inputs)
    (output/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
    ready=dict(schema='iris.Zephyr_mixed9_bringup_ready.v1',status='ready_for_root_managed_preparation',ELF_sha256=sha(elf),build=str(build),
               required_regions=9,cases=3,UART_profile=PROFILE,qualification_sha256=sha(output/'qualification.json'),corpus_sha256=sha(output/'corpus.json'),
               preinit_and_postdriver_config_readback_planned=True,hardware_tested=False,hardware_contacted=False)
    (output/'ready.json').write_text(json.dumps(ready,indent=2)+'\n');return ready


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--gate',type=Path,action='append',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=qualify(a.build,a.gate,a.output);print(json.dumps(dict(status=result['status'],ELF_sha256=result['ELF_sha256'],ready_sha256=sha(a.output/'ready.json'))))
