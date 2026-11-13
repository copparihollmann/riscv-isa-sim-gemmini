#!/usr/bin/env python3
"""Qualify the existing scalar6 Zephyr protocol for a new Ethan-profile ELF."""
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
PROFILE={'requested_baud':3676470,'clock_hz':500000000,'divisor':135}


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
    if not ok:raise ValueError(msg)
def host_cases():
    # Independently count row-strided M16N16K16 and valid 6x6 3x3 convolution.
    return [dict(id='zephyr.gemm16',active_harts=[0,1,2],region='kernel',expected_checksums_by_hart=[len(range(h,16,3))*16*16 for h in range(3)]),
            dict(id='zephyr.conv2d8',active_harts=[0,1,2],region='kernel',expected_checksums_by_hart=[len(range(h,6,3))*6*9 for h in range(3)])]


def validate(text,require_driver_exit):
    lines=text.splitlines();need(not any(x in text for x in ('IRIS_FATAL','ASSERTION FAIL','*** FAILED ***')),'Guest/driver fatal')
    profiles=[json.loads(x.split(' ',1)[1])for x in lines if x.startswith('IRIS_UART_PROFILE ')]
    need(profiles==[PROFILE]and all(type(v)is int for v in profiles[0].values()),'Actual Ethan UART DIV135 profile required')
    rows=[json.loads(x.split(' ',1)[1])for x in lines if x.startswith('IRIS_REGION ')]
    want=[(c,h,c['expected_checksums_by_hart'][h])for c in host_cases()for h in c['active_harts']]
    need(len(rows)==6,'Exact scalar6 region count');previous={}
    for r,(c,h,expected)in zip(rows,want):
        need(all(type(r.get(k))is int for k in ('hart','hart_mask','checksum','start_cycle','end_cycle','instret_delta')),'Typed actual region fields')
        need(r['case_id']==c['id']and r['region']=='kernel'and r['hart']==h and r['hart_mask']==7 and r['role']=='scalar.compute','Actual SMP role/order')
        need(r['checksum']==expected,'Independent scalar numerical checksum')
        need(0<=r['start_cycle']<r['end_cycle']<2**64 and 0<r['instret_delta']<2**64 and r['start_cycle']>=previous.get(h,0),'Actual program counter boundaries')
        previous[h]=r['end_cycle']
    footer=[json.loads(x.split(' ',1)[1])for x in lines if x.startswith('IRIS_BATCH_DONE ')]
    need(footer==[{'failed':0}]and type(footer[0]['failed'])is int,'Exact existing guest completion protocol')
    if require_driver_exit:
        exits=re.findall(r'COMMAND_EXIT_CODE="([0-9]+)"',text)
        need(exits==['0']and text.count('COMMAND_EXIT_CODE')==1 and '*** PASSED ***'in text,'Driver normal exit-zero required; DONE alone is insufficient')
    return dict(regions=6,case_count=2,harts=[0,1,2],all_independent_checksums_passed=True,
                normal_guest_protocol_completed=True,driver_exit_verified=require_driver_exit,
                UART_divisor_readback=PROFILE,
                interrupt_scope='Pinned workers each complete two1ms k_sleep calls and shared mutex/yield/semaphore work; no per-hart ISR/IPI counters are emitted.',
                HTIF_scope='Actual sys_arch_reboot writes success1; normal external driver exit must also be verified',
                timing_certified=False)


def qualify(build,gates,output):
    sys.path.insert(0,str(ROOT/'timing'));from fp8_format_functional_audit_v1 import Elf
    build,output=Path(build).resolve(),Path(output).resolve();need(not output.exists(),'Fresh qualification output')
    record=json.loads((build/'build.json').read_text());elf=build/'zephyr/zephyr.elf'
    need(record['status']=='built'and record['zephyr_sha']==PIN and record['source_patch_sha256']is None,'Clean pinned scalar Zephyr source')
    need(record['uart_profile']['name']=='ethan-firesim'and record['uart_profile']['expected_divisor']==135,'Ethan overlay build, not physical115200')
    need(sha(elf)==record['artifact_sha256']['zephyr/zephyr.elf'],'Successful exact build ELF')
    source=Path(record['source']);need(subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()==PIN,'Current source pin')
    need(not subprocess.check_output(['git','-C',str(source),'status','--porcelain','--untracked-files=all']), 'Pinned upstream clone must remain clean')
    config={}
    for line in(build/'zephyr/.config').read_text().splitlines():
        if line.startswith('CONFIG_')and'='in line:k,_,v=line.partition('=');config[k]=v
    for k,v in {'CONFIG_SMP':'y','CONFIG_MP_MAX_NUM_CPUS':'3','CONFIG_IRIS_BENCH_WORKERS':'3','CONFIG_IRIS_BENCH_HART_MASK':'7','CONFIG_IRIS_BENCH_EXIT_ON_COMPLETION':'y','CONFIG_UART_HTIF':'y','CONFIG_UART_SIFIVE':'y','CONFIG_SYS_CLOCK_HW_CYCLES_PER_SEC':'500000'}.items():need(config.get(k)==v,'Required compiled configuration '+k)
    need(config.get('CONFIG_RISCV_ISA_EXT_V')!='y'and config.get('CONFIG_IRIS_BENCH_VME')!='y'and config.get('CONFIG_RISCV_PMP')!='y','Finite scalar bringup avoids vector/PMP assumptions')
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
    sourcepaths=[source/'soc/rocketchip/virt_riscv/common/soc.c',source/'drivers/serial/uart_htif.c',source/'drivers/timer/riscv_machine_timer.c',source/'arch/riscv/core/smp.c']
    for p in sourcepaths:inputs[str(p)]=sha(p)
    soc=sourcepaths[0].read_text();need('tohost = (uint64_t)((success << 1) | 1)'in soc and'int success = 0;'in soc,'Source HTIF success exit, not reset loop')
    results=[]
    for gate in gates:
        gate=Path(gate).resolve();r=json.loads((gate/'results.json').read_text())
        need(r['status']=='passed_scalar_zephyr_smp'and r['exit_status']==0 and r['timed_out']is False and r['elf_sha256']==sha(elf),'Normal exact seeded ELF execution')
        need(sha(gate/'stdout')==r['stdout_sha256']and sha(gate/'stderr')==r['stderr_sha256'],'Seeded raw output binding')
        proof=validate((gate/'stdout').read_text(),False);results.append(dict(seed=r['seed'],report=str(gate/'results.json'),report_sha256=sha(gate/'results.json'),proof=proof))
        for p in [gate/'results.json',gate/'stdout',gate/'stderr']:inputs[str(p)]=sha(p)
    need(len(results)==2 and{x['seed']for x in results}=={0,17},'Both seeded functional schedules')
    output.mkdir(parents=True);(output/'inputs').mkdir()
    for name,d in inputs.items():
        saved=output/'inputs'/d
        if not saved.exists():shutil.copyfile(name,saved)
    (output/'compiled-dependencies.txt').write_text(deps);(output/'HTIF-exit-disassembly.txt').write_text(asm)
    corpus=dict(schema='iris.Zephyr_scalar6_functional_corpus.v1',cases=host_cases(),regions=6,harts=[0,1,2],
                guest_protocol='Unchanged IRIS_REGION and IRIS_BATCH_DONE{failed:0}; no host-invented records',
                UART_profile=PROFILE,calibration_usable=False,heldout=False,functional_only=True)
    (output/'corpus.json').write_text(json.dumps(corpus,indent=2)+'\n')
    report=dict(schema='iris.Zephyr_scalar6_bringup_qualification.v1',**{'pass':True},ELF_sha256=sha(elf),build=str(build),build_receipt_sha256=sha(build/'build.json'),
                corpus_sha256=sha(output/'corpus.json'),functional=results,compiled_kernel_dependencies=len(depfiles),HTIF_symbols={k:dict(address=v[0],size=v[1])for k,v in symbols.items()},
                source_pin=PIN,source_overlay=None,UART_profile=PROFILE,all_three_hart_worker_checksums=True,
                existing_hardware_scope='Several285-region diagnostic Zephyr images passed; original image repeatedly stopped after25. Cause unproved; scalar6 is a new exact ELF/hardware attempt.',
                no_new_perhart_interrupt_counters=True,FPGA_execution_performed=False,hardware_or_network_contacted=False,
                source_image_association_verified=False,timing_certified=False,input_sha256=inputs)
    (output/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
    ready=dict(schema='iris.Zephyr_scalar6_bringup_ready.v1',status='ready_for_root_managed_preparation',ELF_sha256=sha(elf),build=str(build),
               required_regions=6,cases=2,UART_profile=PROFILE,qualification_sha256=sha(output/'qualification.json'),corpus_sha256=sha(output/'corpus.json'),
               preinit_and_postdriver_config_readback_planned=True,hardware_tested=False,hardware_contacted=False)
    (output/'ready.json').write_text(json.dumps(ready,indent=2)+'\n');return ready


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--gate',type=Path,action='append',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=qualify(a.build,a.gate,a.output);print(json.dumps(dict(status=result['status'],ELF_sha256=result['ELF_sha256'],ready_sha256=sha(a.output/'ready.json'))))
