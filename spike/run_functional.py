#!/usr/bin/env python3
"""Run actual guest ELFs and capture correctness evidence, never timing calibration."""
import argparse
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import struct
import subprocess
import time

HERE=Path(__file__).resolve().parent
PIN='72958551566a30f19444bd7e354552824e4d0a98'
COMPUTE='rv64gcv_zfh_zvfh_zba_zbb_zbs_zvbb_zvl256b_zvfofp8min_zvfbfmin_zvfbfa_zvt32t_zvti8i32mm_zvtofp8fmm'
DMA='rv64gcv_zfh_zvfh_zvl256b_zvbb'
VALIDATOR=HERE.parent/'benchmarks/validate_console.py'
CORPUS=HERE.parent/'benchmarks/calibration-corpus.json'
_spec=importlib.util.spec_from_file_location('iris_validate_console',VALIDATOR)
_validator=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_validator)
_uart_spec=importlib.util.spec_from_file_location('iris_uart_evidence',HERE/'uart_evidence.py')
_uart=importlib.util.module_from_spec(_uart_spec);_uart_spec.loader.exec_module(_uart)
_csr_spec=importlib.util.spec_from_file_location('iris_csr_rtl_evidence',HERE/'csr_rtl_evidence.py')
_csr=importlib.util.module_from_spec(_csr_spec);_csr_spec.loader.exec_module(_csr)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def symbols(path):
    """Read defined ELF64 little-endian symbols; no toolchain subprocess required."""
    raw=Path(path).read_bytes()
    if raw[:6]!=b'\x7fELF\x02\x01':raise ValueError('Require ELF64 little-endian guest')
    hdr=struct.unpack_from('<16sHHIQQQIHHHHHH',raw)
    sections=[struct.unpack_from('<IIQQQQIIQQ',raw,hdr[6]+i*hdr[11]) for i in range(hdr[12])]
    result={}
    for sec in sections:
        if sec[1]!=2:continue
        strs=sections[sec[6]]; strings=raw[strs[4]:strs[4]+strs[5]]
        for offset in range(sec[4],sec[4]+sec[5],sec[9]):
            name,info,other,index,value,size=struct.unpack_from('<IBBHQQ',raw,offset)
            if index and name<len(strings):result[strings[name:].split(b'\0',1)[0].decode('utf8',errors='replace')]=value
    return result

def command(binary,elf,board=True,reference=False):
    common=[str(binary)]
    if reference:common += [f'--isa={COMPUTE}_zicntr_zihpm','-p1','-m0x80000000:0x100000000']
    elif board:
        common += ['--iris-vme',f'--isa={DMA}',f'--hart-isa=0:{COMPUTE}',f'--hart-isa=1:{COMPUTE}',f'--hart-isa=2:{DMA}','-p3','-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000',f'--extlib={HERE}/bin/libsifive_uart.so','--device=sifive_uart,0x10020000']
    else:common += ['--iris-vme',f'--isa={COMPUTE}_zicntr_zihpm','-p1','-m0x80000000:0x100000000']
    return common+[str(elf)]

def run_case(name,cmd,env,out,expected=0,timeout=60):
    start=time.perf_counter()
    try:
        proc=subprocess.run(cmd,env=env,capture_output=True,text=True,timeout=timeout)
    except subprocess.TimeoutExpired as exc:raise RuntimeError(f'{name} timed out') from exc
    elapsed=time.perf_counter()-start
    stdout=out/f'{name}.stdout';stderr=out/f'{name}.stderr'
    stdout.write_text(proc.stdout);stderr.write_text(proc.stderr)
    rows=[json.loads(line.split(' ',1)[1]) for line in proc.stdout.splitlines() if line.startswith('IRIS_REGION ')]
    passed=proc.returncode==expected and all(row['pass'] for row in rows)
    if expected==0 and rows:
        try:_validator.validate(proc.stdout,json.loads(CORPUS.read_text()),3,name=='smoke')
        except (ValueError,TypeError,KeyError):passed=False
    if expected==0 and not rows:passed &= 'PASSED' in proc.stdout
    result={'name':name,'argv':cmd,'elf_sha256':sha(cmd[-1]),'exit_status':proc.returncode,'expected_exit_status':expected,'pass':bool(passed),'host_elapsed_seconds':elapsed,'region_count':len(rows),'measured_region_instructions':sum(r['instret_delta'] for r in rows),'stdout_sha256':sha(stdout),'stderr_sha256':sha(stderr),'timing_certified':False}
    fp8_exact=[{'format':fmt,'exact':int(exact),'total':int(total)} for fmt,exact,total in re.findall(r'^(mm\.[^:]+): (\d+)/(\d+) bit-exact',proc.stdout,re.M)]
    if fp8_exact:result['fp8_sequential_bit_exact']=fp8_exact
    if name=='vme-fp8-directed':result['pass'] &= len(fp8_exact)==4 and all(row['exact']==row['total'] for row in fp8_exact)
    result['verification_kind']='expected-nonzero-exit' if expected else 'embedded-golden-correctness'
    if fp8_exact and any(row['exact']!=row['total'] for row in fp8_exact):result['verification_kind']='embedded-tolerance-pass-with-bitwise-divergences'
    # Region counts exclude startup/synchronization: never present them as full-run MIPS.
    return result

def live_fixture_evidence(binary,report=None):
    root=HERE.parent;report=Path(report).resolve() if report is not None else root/'build/timing-live/results.json'
    if not report.is_file():return {'tested':False,'reason':'Live fixture evidence not collected'},{}
    receipt=json.loads(report.read_text());evidence={str(report):sha(report)}
    if receipt.get('status')!='passed_integration_fixtures' or receipt.get('binary_sha256')!=sha(binary):
        return {'tested':False,'reason':'Live fixture report does not match packaged binary'},evidence
    required={'counter-fast','counter-slow','counter-idle-gated','counter-seed','counter-seed-repeat',
              'order-load-first','order-store-first','exit-busy-peers'}
    rows=receipt.get('results',[]);names=[row.get('name') for row in rows]
    if len(set(names))!=len(names) or not required.issubset(names):
        return {'tested':False,'reason':'Live fixture coverage incomplete or duplicated'},evidence
    negative=receipt.get('negative_results',[]);negative_names=[row.get('name') for row in negative]
    if len(set(negative_names))!=len(negative_names) or not {'no-calibration-claim','missing-hart','negative-latency'}.issubset(negative_names):
        return {'tested':False,'reason':'Live fixture rejection coverage incomplete or duplicated'},evidence
    if not receipt.get('generated_dts_sha256'):
        return {'tested':False,'reason':'Live fixture DTB clock evidence missing'},evidence
    checks=[(report.parent/'fixture.dts',receipt['generated_dts_sha256'])]
    required_sources={'timing/live_check.py','timing/counter_guest.c','timing/order_guest.S','timing/exit_guest.S',
                      'timing/fixtures/three-hart-fast.fixture','timing/fixtures/three-hart-slow.fixture',
                      'benchmarks/start.S','benchmarks/runtime.c','benchmarks/runtime.h','benchmarks/link.ld'}
    if not required_sources.issubset(receipt.get('source_sha256',{})):
        return {'tested':False,'reason':'Live fixture source provenance incomplete'},evidence
    for name,digest in receipt.get('source_sha256',{}).items():
        path=root/name
        if not path.is_file() or sha(path)!=digest:return {'tested':False,'reason':'Live fixture source digest mismatch'},evidence
        evidence[str(path)]=digest
    for row in rows:
        if row.get('pass') is not True:return {'tested':False,'reason':'Live fixture case failed'},evidence
        args=row['argv'];checks += [(Path(args[0]),receipt['binary_sha256']),(Path(args[-1]),row['elf_sha256']),
            (Path(next(a.split('=',1)[1] for a in args if a.startswith('--extlib='))),receipt['uart_sha256']),
            (Path(next(a.split('=',1)[1] for a in args if a.startswith('--iris-timing-fixture='))),row['fixture_sha256']),
            (Path(next(a.split('=',1)[1] for a in args if a.startswith('--iris-timing-trace='))),row['graph_sha256']),
            (report.parent/(row['name']+'.stdout'),row['stdout_sha256']),
            (report.parent/(row['name']+'.stderr'),row['stderr_sha256'])]
    for row in negative:
        if row.get('pass') is not True or type(row.get('exit_status')) is not int or row['exit_status']==0:
            return {'tested':False,'reason':'Live fixture rejection case failed'},evidence
        checks += [(report.parent/(row['name']+'.fixture'),row['fixture_sha256']),
                   (report.parent/(row['name']+'.stderr'),row['stderr_sha256'])]
    for path,digest in checks:
        if not path.is_file() or sha(path)!=digest:return {'tested':False,'reason':'Live fixture artifact digest mismatch'},evidence
        evidence[str(path)]=digest
    return {'tested':True,'checks':len(receipt['results']),'binary_sha256':sha(binary),'calibrated':False,'scope':receipt['scope']},evidence


def board_fixture_evidence(binary,report=None):
    root=HERE.parent;report=Path(report).resolve() if report is not None else root/'build/board-integration/results.json'
    if not report.is_file():return {'tested':False,'reason':'Physical-board integration not collected'},{}
    receipt=json.loads(report.read_text());evidence={str(report):sha(report)}
    if receipt.get('status')!='passed_physical_boot_integration' or receipt.get('binary_sha256')!=sha(binary):
        return {'tested':False,'reason':'Physical-board receipt does not match packaged binary'},evidence
    required={'smoke','batch','counter-clock','pma','clint-0','clint-1','clint-2','clint-3','clint-4','clint-5'}
    if not required.issubset({r['name'] for r in receipt['results']}):return {'tested':False,'reason':'Physical-board integration coverage incomplete'},evidence
    checks=[(root/'board/integration_check.py',receipt['runner_sha256'])]
    checks += [(root/name,digest) for name,digest in receipt.get('guest_source_sha256',{}).items()]
    for row in receipt['results']:
        if row.get('pass') is not True:return {'tested':False,'reason':'Physical-board integration case failed'},evidence
        args=row['argv'];checks += [(Path(args[-1]),row['elf_sha256']),(report.parent/(row['name']+'.stdout'),row['stdout_sha256']),(report.parent/(row['name']+'.stderr'),row['stderr_sha256'])]
        for flag,key in [('--iris-bootrom=','rom_sha256'),('--dtb=','dtb_sha256'),('--extlib=','uart_sha256')]:
            checks.append((Path(next(a.split('=',1)[1] for a in args if a.startswith(flag))),receipt[key]))
        if row.get('proof',{}).get('graph_sha256'):
            checks.append((Path(next(a.split('=',1)[1] for a in args if a.startswith('--iris-timing-trace='))),row['proof']['graph_sha256']))
    for path,digest in checks:
        if not path.is_file() or sha(path)!=digest:return {'tested':False,'reason':'Physical-board artifact digest mismatch'},evidence
        evidence[str(path)]=digest
    return {'tested':True,'checks':len(receipt['results']),'binary_sha256':sha(binary),'rtl_certified':False,'zephyr_smp_certified':False},evidence

def parse_cpu_layout(dts):
    rows={}
    for match in re.finditer(r'cpu@([0-9a-f]+)\s*\{([^{}]*)',dts,re.S):
        fields=match[2]
        hart=int(re.search(r'\breg\s*=\s*<([^>]+)>',fields)[1],0)
        if hart in rows:raise ValueError('duplicate hart in generated CPU layout')
        pmp=int(re.search(r'riscv,pmpregions\s*=\s*<([^>]+)>',fields)[1],0)
        grain=int(re.search(r'riscv,pmpgranularity\s*=\s*<([^>]+)>',fields)[1],0)
        mmu=re.search(r'mmu-type\s*=\s*"([^"]+)"',fields)[1]
        rows[hart]={'hart':hart,'pmp_entries':pmp,'pmp_granularity':grain,'mmu':mmu}
    if set(rows)!={0,1,2} or any(row['pmp_entries']!=(8 if hart==2 else 0) or
            row['pmp_granularity']!=4 or row['mmu']!='riscv,sv39' for hart,row in rows.items()):
        raise ValueError('generated DTS does not match three-hart Iris CPU layout')
    return [rows[hart] for hart in range(3)]

def shared_policy_inputs():
    """Refuse stale source-derived numeric rules before publishing a receipt."""
    policy=json.loads((HERE/'shared-fpu-policy.json').read_text())
    if policy['hardware_dtypes_sha256']!=sha(HERE.parent/'hardware/dtypes.json'):
        raise ValueError('Shared scalar-FPU hardware datatype evidence is stale')
    inputs={}
    for row in policy['source_inputs'].values():
        path=HERE.parent/row['path']
        if not path.is_file() or sha(path)!=row['sha256']:
            raise ValueError('Shared scalar-FPU policy source differs: '+row['path'])
        checkout=HERE.parent/'third_party'/Path(row['path']).parts[1]
        revision=subprocess.check_output(['git','-C',str(checkout),'rev-parse','HEAD'],text=True).strip()
        if revision!=row['git_sha']:raise ValueError('Shared scalar-FPU policy revision differs: '+row['path'])
        inputs[str(path)]=row['sha256']
    proof=json.loads((HERE/'shared-decoder-proof.json').read_text())
    if proof['snapshot_sha256']!=sha(HERE/'shared-evidence/fpu-decoder4.fir') or len(proof['cases'])!=21 or any(row['wflags_true_terms'] for row in proof['cases']):
        raise ValueError('Shared scalar-FPU elaborated decoder proof is stale or incomplete')
    hardware=json.loads((HERE.parent/'hardware/manifest.json').read_text())
    if proof['fir_sha256']!=hardware['sources']['firesim-fir']['sha256']:
        raise ValueError('Shared scalar-FPU proof is from a different elaborated design')
    return inputs

def fpcomp_policy_inputs():
    """Bind source rules and all five elaborated scalar-extraction decoders."""
    policy=json.loads((HERE/'fpcomp-policy.json').read_text());inputs={}
    if policy['hardware_manifest_sha256']!=sha(HERE.parent/'hardware/manifest.json') or policy['hardware_dtypes_sha256']!=sha(HERE.parent/'hardware/dtypes.json'):
        raise ValueError('FPComp policy uses a different hardware configuration')
    for name,row in policy['source_inputs'].items():
        path=HERE.parent/name
        if not path.is_file() or sha(path)!=row['sha256']:raise ValueError('FPComp policy source differs: '+name)
        checkout=HERE.parent/'third_party'/Path(name).parts[1]
        revision=subprocess.check_output(['git','-C',str(checkout),'rev-parse','HEAD'],text=True).strip()
        if revision!=row['git_sha']:raise ValueError('FPComp policy revision differs: '+name)
        inputs[str(path)]=row['sha256']
    fir=json.loads((HERE.parent/'hardware/manifest.json').read_text())['sources']['firesim-fir']['sha256']
    expected_modules={'FPUDecoder','FPUDecoder_1','FPUDecoder_2','FPUDecoder_3','FPUDecoder_4'};modules=[]
    for name,row in policy['scalar_vf_decoder_proofs'].items():
        path=HERE/name;proof=json.loads(path.read_text());modules.append(proof['module'])
        if sha(path)!=row['sha256'] or sha(HERE/row['snapshot'])!=row['snapshot_sha256'] or proof['snapshot_sha256']!=row['snapshot_sha256'] or proof['fir_sha256']!=fir:
            raise ValueError('FPComp elaborated decoder proof differs: '+name)
        if len(proof['cases'])!=11 or len(proof['wflags_pla_terms'])!=17 or any(case['wflags_true_terms'] for case in proof['cases']):
            raise ValueError('FPComp scalar-extraction coverage differs: '+name)
    if len(modules)!=5 or set(modules)!=expected_modules:raise ValueError('FPComp decoder modules incomplete')
    return inputs

def plic_fixture_evidence(binary,report=None):
    root=HERE.parent;report=Path(report).resolve() if report is not None else root/'build/plic-integration/results.json'
    if not report.is_file():return {'tested':False,'reason':'PLIC process integration not collected'},{}
    receipt=json.loads(report.read_text());evidence={str(report):sha(report)}
    if receipt.get('status')!='passed_process_regressions' or receipt.get('binary_sha256')!=sha(binary):
        return {'tested':False,'reason':'PLIC process receipt does not match packaged binary'},evidence
    rows=receipt.get('results',[]);modes=[row.get('mode') for row in rows]
    if len(modes)!=10 or set(modes)!=set(range(10)):
        return {'tested':False,'reason':'PLIC process coverage incomplete or duplicated'},evidence
    required_sources={'board/plic_guest.c','board/plic_integration_check.py','board/iris_plic.hpp',
                      'benchmarks/start.S','benchmarks/runtime.c','benchmarks/runtime.h','benchmarks/link.ld',
                      'third_party/riscv-isa-sim/riscv/plic.cc','third_party/riscv-isa-sim/riscv/devices.h'}
    if not required_sources.issubset(receipt.get('source_sha256',{})):
        return {'tested':False,'reason':'PLIC process source provenance incomplete'},evidence
    checks=[(root/name,digest) for name,digest in receipt['source_sha256'].items()]
    for row in rows:
        if row.get('pass') is not True:return {'tested':False,'reason':'PLIC process case failed'},evidence
        args=row['argv'];checks += [(Path(args[0]),receipt['binary_sha256']),(Path(args[-1]),row['elf_sha256']),
            (report.parent/('plic-'+str(row['mode'])+'.stdout'),row['stdout_sha256']),
            (report.parent/('plic-'+str(row['mode'])+'.stderr'),row['stderr_sha256'])]
        flags=[('--extlib=','uart_sha256')]
        if row.get('physical_boot'):flags += [('--iris-bootrom=','rom_sha256'),('--dtb=','dtb_sha256')]
        for flag,key in flags:checks.append((Path(next(a.split('=',1)[1] for a in args if a.startswith(flag))),receipt[key]))
    for path,digest in checks:
        if not path.is_file() or sha(path)!=digest:return {'tested':False,'reason':'PLIC process artifact digest mismatch'},evidence
        evidence[str(path)]=digest
    return {'tested':True,'checks':len(rows),'binary_sha256':sha(binary),'rtl_certified':False},evidence

def memory_fixture_evidence(binary,report=None):
    """Accept only named, hash-bound conservative scalar memory fixtures."""
    root=HERE.parent;report=Path(report).resolve() if report is not None else root/'build/memory-live/results.json'
    if not report.is_file():return {'tested':False,'reason':'Scalar memory live evidence not collected'},{}
    receipt=json.loads(report.read_text());evidence={str(report):sha(report)}
    if receipt.get('status')!='passed_address_routed_live_fixtures' or receipt.get('binary_sha256')!=sha(binary):
        return {'tested':False,'reason':'Scalar memory live receipt does not match packaged binary'},evidence
    required={'regions-fast','regions-slow','load-first','store-first','seed17','seed17-repeat'}
    rejected={'vector':'MEMORY_OPERATION_UNMODELED','mprv':'TRANSLATED_MEMORY_UNMODELED',
              'missing-port':'memory stage port missing','ambiguous':'AMBIGUOUS_MEMORY_ROUTE',
              'missing-route':'MEMORY_ROUTE_MISSING','zero-clock':'explicit clock',
              'rv32':'IRIS_TIMING_SCALAR_MEMORY_REQUIRES_RV64'}
    rows=receipt.get('results',[]);negative=receipt.get('negative_results',[])
    if len(rows)!=len(required) or {row.get('name') for row in rows}!=required or len(negative)!=len(rejected) or {row.get('name') for row in negative}!=set(rejected):
        return {'tested':False,'reason':'Scalar memory coverage is incomplete or duplicated'},evidence
    if receipt.get('calibrated') is not False or receipt.get('iris_accuracy_certified') is not False:
        return {'tested':False,'reason':'Synthetic memory fixtures cannot certify Iris timing accuracy'},evidence
    required_sources={'timing/memory_live_check.py','timing/memory_guest.c','timing/memory_guard_guest.S',
        'timing/scalar_memory.hpp','timing/scalar_memory.cpp','timing/memory_path.hpp','timing/memory_path.cpp',
        'timing/iris_timing.hpp','timing/iris_timing.cpp','timing/order_guest.S',
        'benchmarks/start.S','benchmarks/runtime.c','benchmarks/runtime.h','benchmarks/link.ld'}
    if not required_sources.issubset(receipt.get('source_sha256',{})):
        return {'tested':False,'reason':'Scalar memory fixture source provenance incomplete'},evidence
    checks=[(root/name,digest) for name,digest in receipt['source_sha256'].items()]
    checks.append((HERE/'bin/libsifive_uart.so',receipt['uart_sha256']))
    for row in rows:
        if row.get('pass') is not True:return {'tested':False,'reason':'Scalar memory fixture failed'},evidence
        args=row['argv']
        checks += [(Path(args[0]),receipt['binary_sha256']),(Path(args[-1]),row['elf_sha256']),
            (Path(next(arg.split('=',1)[1] for arg in args if arg.startswith('--extlib='))),receipt['uart_sha256']),
            (Path(next(arg.split('=',1)[1] for arg in args if arg.startswith('--iris-timing-fixture='))),row['fixture_sha256']),
            (Path(next(arg.split('=',1)[1] for arg in args if arg.startswith('--iris-timing-trace='))),row['graph_sha256']),
            (report.parent/(row['name']+'.stdout'),row['stdout_sha256']),
            (report.parent/(row['name']+'.stderr'),row['stderr_sha256'])]
    for row in negative:
        if row.get('pass') is not True or type(row.get('exit_status')) is not int or row['exit_status']==0:
            return {'tested':False,'reason':'Scalar memory rejection failed'},evidence
        name=row['name'];stderr=report.parent/(name+'.stderr')
        if not stderr.is_file() or rejected[name] not in stderr.read_text():
            return {'tested':False,'reason':'Scalar memory rejection diagnostic missing'},evidence
        checks += [(report.parent/(name+'.fixture'),row['fixture_sha256']),(stderr,row['stderr_sha256'])]
        if name in {'vector','mprv'}:
            if type(row.get('functional_exit_status')) is not int or row['functional_exit_status']!=0:return {'tested':False,'reason':'Memory rejection functional control failed'},evidence
            checks += [(report.parent/(name+'.elf'),row['elf_sha256']),
                (report.parent/(name+'.functional.stdout'),row['functional_stdout_sha256']),
                (report.parent/(name+'.functional.stderr'),row['functional_stderr_sha256'])]
    for path,digest in checks:
        if not path.is_file() or sha(path)!=digest:return {'tested':False,'reason':'Scalar memory fixture artifact digest differs'},evidence
        evidence[str(path)]=digest
    return {'tested':True,'checks':len(rows),'rejections':len(negative),'binary_sha256':sha(binary),
        'calibrated':False,'iris_accuracy_certified':False,'scope':receipt['scope'],
        'vector_memory_qualified':False,'cache_coherence_qualified':False,'pipeline_qualified':False},evidence

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dtc',default=os.environ.get('DTC') or shutil.which('dtc'))
    parser.add_argument('--live-receipt',type=Path)
    parser.add_argument('--board-receipt',type=Path)
    parser.add_argument('--plic-receipt',type=Path)
    parser.add_argument('--memory-receipt',type=Path)
    parser.add_argument('--uart-receipt',type=Path)
    args=parser.parse_args()
    if not args.dtc:parser.error('--dtc required')
    binary=HERE/'bin/spike-iris-functional'
    if not binary.is_file():parser.error('Run build.py first')
    env=dict(os.environ);env['PATH']=str(Path(args.dtc).resolve().parent)+os.pathsep+env['PATH']
    out=HERE/'results';out.mkdir(exist_ok=True)
    dts_command=command(binary,HERE/'benchmarks/cpu_config.elf')
    dts_command.insert(-1,'--dump-dts')
    generated_dts=subprocess.check_output(dts_command,env=env,text=True,stderr=subprocess.PIPE)
    cpu_layout=parse_cpu_layout(generated_dts)
    (out/'cpu-layout.dts').write_text(generated_dts)
    results=[]
    for stem in ['smoke','batch']:
        elf=HERE.parent/f'benchmarks/build/{stem}.elf'
        if not elf.exists():raise SystemExit(f'Missing required guest: {elf}; build benchmarks first')
        syms=symbols(elf)
        fatal=[syms[s] for s in ['z_fatal_error','k_sys_fatal_error_handler','z_fatal_halt'] if s in syms]
        env.pop('IRIS_FATAL_PCS',None)
        if fatal:env['IRIS_FATAL_PCS']=','.join(hex(x) for x in sorted(set(fatal)))
        results.append(run_case(stem,command(binary,elf),env,out))
    batch_elf=HERE.parent/'benchmarks/build/batch.elf'
    for name,seed in [('batch-seed-1',1),('batch-seed-1-repeat',1),('batch-seed-2',2)]:
        cmd=command(binary,batch_elf);cmd.insert(1,f'--iris-schedule-seed={seed}')
        result=run_case(name,cmd,env,out);result['schedule_seed']=seed;results.append(result)
    identical=(out/'batch-seed-1.stdout').read_bytes()==(out/'batch-seed-1-repeat.stdout').read_bytes()
    results[-2]['pass'] &= identical
    results[-2]['repeat_stdout_identical']=identical
    for name in ['hart2-vector-arithmetic','hart2-vector-move','cpu-dtypes','native-fp8','wide-reduce-fp8','ieee-bf16','shared-fpu','fpcomp','bitmanip','cpu_config','csr_config']:
        elf=HERE/f'benchmarks/{name}.elf'
        if not elf.is_file():raise SystemExit('Missing CPU dtype guest; run compile_saturn.py')
        results.append(run_case(name,command(binary,elf),env,out))
        if name=='fpcomp':
            rows=[json.loads(line.split(' ',1)[1]) for line in (out/'fpcomp.stdout').read_text().splitlines() if line.startswith('IRIS_FPCOMP ')]
            results[-1]['pass'] &= rows==[{'hart0_cases':4224,'hart1_cases':4224,'hart2_cases':4224,'illegal_cases':132}]
            results[-1]['per_hart_execution_proof']=rows
        if name=='bitmanip':
            rows=[json.loads(line.split(' ',1)[1]) for line in (out/'bitmanip.stdout').read_text().splitlines() if line.startswith('IRIS_BITMANIP ')]
            results[-1]['pass'] &= len(rows)==3 and {r['hart'] for r in rows}=={0,1,2} and all(
                r['scalar_cases']==(0 if r['hart']==2 else 12) and r['illegal_cases']==(4 if r['hart']==2 else 0)
                and r['vector_sew_cases']==4 for r in rows)
            results[-1]['per_hart_bitmanip']=rows
        if name=='cpu_config':
            rows=[json.loads(line.split(' ',1)[1]) for line in (out/'cpu_config.stdout').read_text().splitlines() if line.startswith('IRIS_CPUCONFIG ')]
            results[-1]['pass'] &= len(rows)==3 and {r['hart'] for r in rows}=={0,1,2} and all(
                r['pmp_entries']==(8 if r['hart']==2 else 0) and r['pmp_illegal_cases']==(0 if r['hart']==2 else 2)
                and r['sv39'] is True and r['sv48_rejected'] is True
                and r['padded_pmp_read_zero_write_ignored'] is (r['hart']==2) for r in rows)
            results[-1]['per_hart_cpu_config']=rows
        if name=='csr_config':
            rows=[json.loads(line.split(' ',1)[1]) for line in (out/'csr_config.stdout').read_text().splitlines() if line.startswith('IRIS_CSRCONFIG ')]
            expected={'checks':122,'hardware_hpm_counters':0,'padded_slots':29,'mcounteren':7,'scounteren':7,'mcountinhibit':5,'rdtime_illegal':True,'mtime_advances':True}
            results[-1]['pass'] &= len(rows)==3 and {r['hart'] for r in rows}=={0,1,2} and all(
                all(r.get(key)==value for key,value in expected.items()) for r in rows)
            results[-1]['per_hart_csr_config']=rows
    cease=run_case('cease-capability',command(binary,HERE/'benchmarks/cease.elf'),env,out,expected=1)
    cease['pass'] &= ('PASSED compute CEASE illegal probes on harts0/1' in (out/'cease-capability.stdout').read_text()
                      and 'IRIS_UNSUPPORTED_CORE_INSTRUCTION hart=2' in (out/'cease-capability.stderr').read_text())
    cease['verification_kind']='expected-model-capability-refusal'
    results.append(cease)
    # Explicit fatal entry stops immediately, with guest trap context.
    fatal_env=dict(env,IRIS_FATAL_PCS=hex(symbols(HERE.parent/'benchmarks/build/smoke.elf')['_start']))
    fatal=run_case('fatal-entry',command(binary,HERE.parent/'benchmarks/build/smoke.elf'),fatal_env,out,expected=1)
    fatal['pass'] &= all(word in (out/'fatal-entry.stderr').read_text() for word in ['IRIS_FATAL','hart=','pc=','cause=','tval='])
    results.append(fatal)
    for stem in ['vme-directed','vme-directed-mx','vme-fused-lm2-gemm-transpose','vme-fp8-directed','vme-fp8-gemm']:
        elf=HERE/f'benchmarks/{stem}.riscv'
        if not elf.exists():raise SystemExit(f'Missing required Saturn corpus ELF: {elf}; run compile_saturn.py')
        if stem in ['vme-directed','vme-directed-mx']:
            result=run_case(stem,command(binary,elf,board=False),env,out,expected=1)
            result['pass'] &= 'IRIS_UNSUPPORTED_COLUMN_MOVE' in (out/f'{stem}.stderr').read_text()
            result['expected_model_capability_refusal']='column-move-out'
            result['verification_kind']='expected-model-capability-refusal'
            results.append(result)
        else:results.append(run_case(stem,command(binary,elf,board=False),env,out))
        reference=HERE/'bin/spike-zvt-reference'
        if reference.exists():results.append(run_case(stem+'-reference',command(reference,elf,reference=True),env,out))
    for stem,name in [('miles-vme-fused','miles-heldout'),('miles-vme-i8','miles-i8-heldout')]:
        miles=HERE.parent/f'benchmarks/build/{stem}.elf'
        if not miles.exists():raise SystemExit(f'Missing required held-out ELF: {miles}; run benchmarks/build_heldout.py')
        results.append(run_case(name,command(binary,miles,board=False),env,out))
        reference=HERE/'bin/spike-zvt-reference'
        if not reference.exists():raise SystemExit('Missing pristine reference binary')
        results.append(run_case(name+'-reference',command(reference,miles,reference=True),env,out))
    live_fixture,live_evidence=live_fixture_evidence(binary,args.live_receipt)
    board_fixture,board_evidence=board_fixture_evidence(binary,args.board_receipt)
    plic_fixture,plic_evidence=plic_fixture_evidence(binary,args.plic_receipt)
    memory_fixture,memory_evidence=memory_fixture_evidence(binary,args.memory_receipt)
    uart_fixture,uart_evidence=_uart.uart_fixture_evidence(binary,args.uart_receipt)
    live_evidence.update(board_evidence)
    live_evidence.update(plic_evidence)
    live_evidence.update(memory_evidence)
    live_evidence.update(uart_evidence)
    selected_csr,selected_csr_inputs=_csr.selected_csr_evidence()
    live_evidence.update(selected_csr_inputs)
    source=HERE.parent/'third_party/riscv-isa-sim' 
    archive=subprocess.check_output(['git','-C',str(source),'archive','HEAD'])
    manifest={'schema_version':1,'upstream_spike_sha':PIN,'live_integration_fixture':live_fixture,'physical_board_integration':board_fixture,'plic_process_integration':plic_fixture,'external_evidence_inputs':live_evidence,'base_source_archive_sha256':hashlib.sha256(archive).hexdigest(),'target_patch_sha256':sha(HERE/'iris.patch'),'evidence_inputs':{str(p.relative_to(HERE)):sha(p) for p in [HERE/'handler-selftest.jsonl',HERE/'decoder_sources.json',HERE/'benchmarks/build.json',HERE/'fp8-oracle.json',HERE/'dtypes.json',HERE/'native-selftest.json',HERE/'native-handler-selftest.log',HERE/'native-fp8-oracle.json',HERE/'wide-fp8-oracle.json',HERE/'fp8-reduction-oracle.json',HERE/'native-guest-oracle.json',HERE/'fp8-reduction-oracle.json',HERE/'benchmarks/native-fp8-build.json',HERE/'benchmarks/ieee-fma-build.json',HERE/'benchmarks/bitmanip-build.json',HERE/'ieee-fma-oracle.json',HERE/'scalar-bf16-decoder-proof.json',HERE/'core-instruction-gaps.json',HERE/'results/cpu-layout.dts',HERE/'ieee-selftest.json',HERE/'shared-selftest.json',HERE/'shared-fma-oracle.json',HERE/'shared-fpu-policy.json',HERE/'shared-decoder-proof.json',HERE/'shared-evidence/fpu-decoder4.fir',HERE/'benchmarks/shared-fpu-build.json'] if p.is_file()},'binary':str(binary),'binary_sha256':sha(binary),'reference_binary_sha256':sha(HERE/'bin/spike-zvt-reference') if (HERE/'bin/spike-zvt-reference').exists() else None,'external_source_inputs':{str(p):sha(p) for p in sorted(set(list((HERE.parent/'timing').glob('*.cpp'))+list((HERE.parent/'timing').glob('*.hpp'))+list((HERE.parent/'timing').glob('*.py'))+list((HERE.parent/'timing').glob('*.c'))+list((HERE.parent/'timing').glob('*.S'))+list((HERE.parent/'timing/fixtures').glob('*'))+list((HERE.parent/'board').glob('*.hpp'))+list((HERE.parent/'board').glob('*.py'))+list((HERE.parent/'board').glob('*.cpp'))+list((HERE.parent/'board').glob('*.c'))+list((HERE.parent/'board').glob('*.json'))+list((HERE.parent/'board/evidence').glob('*'))+list((HERE.parent/'hardware/memory-evidence').glob('*'))+[HERE.parent/'hardware/memory-paths.json',HERE.parent/'third_party/shuttle/src/main/scala/dmem/DCache.scala',HERE.parent/'third_party/shuttle/src/main/scala/common/Parameters.scala',HERE.parent/'third_party/rocket-chip/src/main/scala/rocket/DCache.scala',HERE.parent/'third_party/rocket-chip/src/main/scala/rocket/HellaCache.scala',HERE.parent/'third_party/rocket-chip/src/main/scala/rocket/RocketCore.scala',HERE.parent/'third_party/rocket-chip/src/main/scala/rocket/IDecode.scala',HERE.parent/'third_party/rocket-chip/src/main/scala/rocket/CustomInstructions.scala',HERE.parent/'third_party/rocket-chip/src/main/scala/rocket/CSR.scala',HERE.parent/'third_party/shuttle/src/main/scala/exu/Core.scala',VALIDATOR,CORPUS,HERE.parent/'third_party/saturn/src/main/scala/common/Parameters.scala',HERE.parent/'third_party/saturn/src/main/scala/frontend/EarlyDecode.scala',HERE.parent/'hardware/dtypes.json',HERE.parent/'third_party/saturn/src/main/scala/exu/OuterProductUnit.scala',HERE.parent/'third_party/saturn/src/main/scala/exu/fp/FPFMAPipe.scala',HERE.parent/'third_party/saturn/src/main/scala/exu/fp/e5M3ToFp8.scala',HERE.parent/'third_party/saturn/src/main/scala/exu/fp/SharedFPFMA.scala',HERE.parent/'third_party/saturn/src/main/scala/exu/ExecutionUnit.scala',HERE.parent/'third_party/saturn/src/main/scala/frontend/PipelinedFaultCheck.scala',HERE.parent/'third_party/rocket-chip/src/main/scala/tile/FPU.scala',HERE.parent/'third_party/saturn/src/main/scala/backend/Backend.scala',HERE.parent/'third_party/saturn/src/main/scala/backend/ExecuteSequencer.scala',HERE.parent/'third_party/saturn/src/main/scala/backend/SpecialSequencer.scala',HERE.parent/'third_party/shuttle/src/main/scala/exu/Core.scala',HERE.parent/'third_party/shuttle/src/main/scala/exu/FPU.scala',HERE.parent/'third_party/saturn/src/main/scala/exu/fp/fp8ToE5M3.scala',HERE.parent/'third_party/hardfloat/hardfloat/src/main/scala/RoundAnyRawFNToRecFN.scala',HERE.parent/'third_party/hardfloat/hardfloat/src/main/scala/RecFNToRecFN.scala',HERE.parent/'third_party/hardfloat/hardfloat/src/main/scala/MulAddRecFN.scala']))},'hardware_manifest_sha256':sha(HERE.parent/'hardware/manifest.json'),'decoder_source_inputs':json.loads((HERE/'decoder_sources.json').read_text())['inputs'],'device_source_sha':'887b868db313805c7163f7cc519a7b9e74d92c98','device_binary_sha256':sha(HERE/'bin/libsifive_uart.so'),'source_inputs':{str(p.relative_to(HERE)):sha(p) for p in sorted(HERE.rglob('*')) if p.is_file() and (p.suffix in {'.py','.sh','.cc','.h','.hpp','.patch','.S','.ld','.c'}) and 'build' not in p.parts and 'reference-source' not in p.parts},'selftest':{'cpu_layout':cpu_layout,'handler_results':[json.loads(s) for s in (HERE/'handler-selftest.jsonl').read_text().splitlines()] if (HERE/'handler-selftest.jsonl').exists() else [],'guest_results':results,'native_fp8':json.loads((HERE/'native-selftest.json').read_text()),'ieee_fma':json.loads((HERE/'ieee-selftest.json').read_text()),'shared_fpu':json.loads((HERE/'shared-selftest.json').read_text())},'certification':{'functional_rtl':False,'zephyr_smp':False,'modeled_time':False,'accuracy_2_percent':False},'launch_isa':{'0':COMPUTE,'1':COMPUTE,'2':DMA},'datatype_coverage':json.loads((HERE/'dtypes.json').read_text()),'functional_run_mips':None,'functional_run_mips_reason':'Complete-run retirement count not instrumented; region-only instruction counts must not be used as full-run MIPS.'}
    manifest['external_source_inputs'].update(shared_policy_inputs())
    manifest['scalar_memory_live_integration']=memory_fixture
    manifest.pop('device_source_sha',None)
    manifest['device_implementation']='iris-clocked-uart-source-bound'
    manifest['uart_device_integration']=uart_fixture
    manifest['evidence_inputs']['device-build.json']=sha(HERE/'device-build.json')
    manifest['external_source_inputs'].update(fpcomp_policy_inputs())
    manifest['selftest']['fpcomp']=json.loads((HERE/'fpcomp-selftest.json').read_text())
    manifest['reset_definedness']=json.loads((HERE/'fpcomp-policy.json').read_text())['reset_definedness']
    manifest['selftest']['configured_csrs']=json.loads((HERE/'csr-selftest.json').read_text())
    manifest['configured_csrs']={'hardware_hpm_counters_per_hart':[0,0,0],'counteren_read_mask':7,
        'mcountinhibit_read_mask':5,'csr_time_implemented':False,'mtime_source':'CLINT MMIO',
        'synthetic_profiler_counters_are_hardware_counters':False,'uninitialized_counteren_reset_tracking':False}
    manifest['selected_csr_rtl_reference']=selected_csr
    csr_policy=json.loads((HERE/'reset-hpm-policy.json').read_text())
    for name,row in csr_policy['source_inputs'].items():
        path=HERE.parent/name
        if sha(path)!=row['sha256']:raise RuntimeError('CSR source policy input changed: '+name)
        manifest['external_source_inputs'][str(path)]=row['sha256']
    csr_evidence=[HERE/name for name in ['csr-selftest.json','csr-handler-selftest.log','reset-hpm-policy.json','benchmarks/csr-config-build.json']]+list((HERE/'reset-hpm-evidence').glob('*.fir'))
    manifest['evidence_inputs'].update({str(path.relative_to(HERE)):sha(path) for path in csr_evidence})
    fpcomp_evidence=[HERE/name for name in ['fpcomp-selftest.json','fpcomp-oracle.json','fpcomp-policy.json','benchmarks/fpcomp-build.json']]+list(HERE.glob('fpcomp-FPUDecoder*-proof.json'))+list((HERE/'fpcomp-evidence').glob('*.fir'))
    manifest['evidence_inputs'].update({str(path.relative_to(HERE)):sha(path) for path in fpcomp_evidence})
    (HERE/'provenance.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'pass':all(r['pass'] for r in results),'tests':len(results),'artifact':str(HERE/'provenance.json')}))
    raise SystemExit(0 if all(r['pass'] for r in results) else 1)

if __name__=='__main__':
    import sys
    os.execv(sys.executable,[sys.executable,str(HERE/'selftest.py'),'--kind','guests',*sys.argv[1:]])
