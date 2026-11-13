#!/usr/bin/env python3
"""Build the pinned experimental fork; never silently use another Spike revision."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'third_party/riscv-isa-sim'
PIN = '72958551566a30f19444bd7e354552824e4d0a98'

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def build_uart(binary, includes, build):
    """Build the source-matched finite UART with the matching native clock ABI."""
    root=HERE.parent
    source=root/'board/uart-device/plugin.cc'
    staged=HERE/'bin/.libsifive_uart.build.so'
    dependency=build/'uart-plugin.d'
    compiler=Path(shutil.which(os.environ.get('CXX','g++'))).resolve()
    flags=[str(compiler),'-std=c++20','-O2',f'-I{includes}',f'-I{build}',
           '-iquote',str(SOURCE/'riscv'),f'-I{root}/board',f'-I{root}/board/uart-device']
    command=flags+['-fPIC','-shared','-MMD','-MF',str(dependency),str(source),'-o',str(staged)]
    subprocess.run(command,check=True)
    sdk=[Path(s).resolve() for s in shlex.split(dependency.read_text().replace('\\\n',' ').split(':',1)[1])]
    required=[root/'benchmarks/uart_drain.h',root/'benchmarks/uart_drain.S',
              root/'board/uart-source-evidence.json',root/'hardware/evidence/firesim-clocks.freq-summary',
              root/'hardware/memory-paths.json',root/'board/uart-device/native-clock.patch',
              root/'board/uart-device/helper-query.patch']
    required += sorted((root/'board/uart-evidence').glob('*'))
    source_evidence=json.loads((root/'board/uart-source-evidence.json').read_text())
    required += [root/'board'/row['snapshot'] for row in source_evidence['sources'].values()]
    for row in source_evidence['sources'].values():
        if digest(root/'board'/row['snapshot'])!=row['sha256']:
            raise RuntimeError('UART source snapshot digest differs from audited source evidence')
    inputs={str(p):digest(p) for p in sorted(set(sdk+required+[compiler,Path(__file__)]))}
    if not any(p.name=='iris_clocked_device.h' for p in sdk):
        raise RuntimeError('UART plugin build omitted native clock SDK dependency')
    exports=subprocess.check_output(['nm','-D',str(binary)],text=True)
    if not any(line.split()[-1:] == ['iris_device_clock_abi_v1'] and ' T ' in line for line in exports.splitlines()):
        raise RuntimeError('Native binary lacks required UART clock ABI')
    tests=[]
    for name,test in [('clock',root/'board/uart-device/clock_test.cpp'),('helper',root/'board/tests/uart_test.cpp')]:
        target=build/('uart-'+name+'-test')
        cmd=flags+['-Wall','-Wextra','-Werror',str(test),'-o',str(target)]
        subprocess.run(cmd,check=True)
        run=subprocess.run([str(target)],check=True,text=True,capture_output=True)
        tests.append({'name':name,'argv':cmd,'source_sha256':digest(test),'stdout':run.stdout,'pass':True})
        inputs[str(test)]=digest(test)
    os.replace(staged,HERE/'bin/libsifive_uart.so')
    receipt={'schema':'iris.uart.primary_build.v1','status':'built_and_unit_passed',
             'binary_sha256':digest(binary),'uart_sha256':digest(HERE/'bin/libsifive_uart.so'),
             'native_device_abi':1,'physical_uart_clock_hz':500000000,'rtc_hz':500000,
             'argv':command,'compiler_sha256':digest(compiler),'input_sha256':inputs,
             'native_overlay_sha256':digest(HERE/'iris.patch'),'sdk_dependencies':list(map(str,sdk)),
             'tests':tests,'rtl_certified':False,'rx_sampling_certified':False}
    (HERE/'device-build.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs',type=int,default=8)
    parser.add_argument('--dtc',default=os.environ.get('DTC') or shutil.which('dtc'))
    parser.add_argument('--live-receipt',type=Path)
    parser.add_argument('--board-receipt',type=Path)
    parser.add_argument('--plic-receipt',type=Path)
    parser.add_argument('--memory-receipt',type=Path)
    parser.add_argument('--uart-receipt',type=Path)
    args=parser.parse_args()
    if not args.dtc or not Path(args.dtc).is_file(): parser.error('--dtc must identify an installed device-tree compiler')
    if args.jobs<1: parser.error('--jobs must be positive')
    pin=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
    if pin != PIN: raise SystemExit(f'Wrong Spike pin: {pin}; require {PIN}')
    actual=subprocess.check_output(['git','-C',str(SOURCE),'diff','--binary','HEAD'])
    patch=HERE/'iris.patch'
    if not patch.is_file() or actual != patch.read_bytes(): raise SystemExit('Spike source differs from recorded iris.patch')
    if not (HERE/'bin/spike-zvt-reference').exists():
        subprocess.run(['python3',str(HERE/'build_reference.py'),'--dtc',args.dtc,'--jobs',str(args.jobs)],check=True)
    build=HERE/'build'; build.mkdir(exist_ok=True)
    env=dict(os.environ,DTC=str(Path(args.dtc).resolve()),CC=os.environ.get('CC') or shutil.which('gcc'),CXX=os.environ.get('CXX') or shutil.which('g++'))
    env['PATH']=str(Path(args.dtc).resolve().parent)+os.pathsep+env['PATH']
    with (build/'configure.log').open('w') as log:
        subprocess.run([str(SOURCE/'configure'),f'--prefix={HERE}/install','--with-boost=no','--with-boost-asio=no','--with-boost-regex=no'],cwd=build,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    with (build/'build.log').open('w') as log:
        subprocess.run(['make',f'-j{args.jobs}','spike'],cwd=build,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
    bindir=HERE/'bin';bindir.mkdir(exist_ok=True)
    binary=bindir/'spike-iris-functional';staged_binary=bindir/'.spike-iris-functional.build'
    shutil.copy2(build/'spike',staged_binary)
    subprocess.run(['strip',str(staged_binary)],check=True)
    os.replace(staged_binary,binary)
    includes=HERE/'include';includes.mkdir(exist_ok=True)
    for component in ['riscv','fesvr','fdt']:
        link=includes/component
        if not link.exists():link.symlink_to(os.path.relpath(SOURCE/component,includes))
    build_uart(binary,includes,build)
    subprocess.run(['python3',str(HERE/'generate_decoder_cases.py'),str(HERE.parent/'third_party/saturn')],check=True)
    subprocess.run(['python3',str(HERE/'generate_fp8_cases.py')],check=True)
    subprocess.run(['python3',str(HERE/'compile_native_fp8.py')],check=True)
    subprocess.run(['python3',str(HERE/'compile_ieee_fma.py')],check=True)
    subprocess.run(['python3',str(HERE/'compile_shared_fma.py')],check=True)
    subprocess.run(['python3',str(HERE/'compile_fpcomp.py')],check=True)
    subprocess.run(['python3',str(HERE/'compile_bitmanip.py')],check=True)
    subprocess.run(['python3',str(HERE/'compile_csr.py')],check=True)
    subprocess.run(['python3',str(HERE/'audit_reset_hpm.py')],check=True)
    result=subprocess.run([str(HERE/'run_selftest.sh')],env=env,text=True,capture_output=True,check=True)
    (HERE/'handler-selftest.jsonl').write_text(result.stdout)
    native=subprocess.run([str(HERE/'run_native_selftest.sh')],env=env,text=True,capture_output=True)
    (HERE/'native-handler-selftest.log').write_text(native.stdout+native.stderr)
    if native.returncode:raise SystemExit(native.stdout+native.stderr)
    import re
    counts=re.search(r'native_fp8_handlers=(\d+) wide_cases=(\d+) reduction_cases=(\d+) forms=23\+18\+4',native.stdout)
    if not counts:raise SystemExit('Missing native handler validation coverage')
    native_receipt={'pass':True,'narrow_cases':int(counts[1]),'wide_cases':int(counts[2]),'reduction_cases':int(counts[3]),'forms':45,'rtl_certified':False,'log_sha256':digest(HERE/'native-handler-selftest.log')}
    (HERE/'native-selftest.json').write_text(json.dumps(native_receipt,indent=2)+'\n')
    ieee_counts=re.search(r'ieee_fma_handlers=(\d+) reduction_cases=(\d+) forms=45 formats=4 rm=5 mask/tails scalar_bf16_illegal=6 hart2_ieee_flags pass',native.stdout)
    if not ieee_counts:raise SystemExit('Missing IEEE/BF16 handler validation coverage')
    ieee_receipt={'pass':True,'operation_cases':int(ieee_counts[1]),'reduction_cases':int(ieee_counts[2]),'forms':45,'scalar_bf16_illegal_cases':6,'hart2_ieee_flags':True,'rtl_certified':False,'log_sha256':digest(HERE/'native-handler-selftest.log')}
    (HERE/'ieee-selftest.json').write_text(json.dumps(ieee_receipt,indent=2)+'\n')
    shared_counts=re.search(r'shared_fma_handlers=(\d+) reductions=(\d+) forms=45 masked_flags VFboxing vstart FS pass',native.stdout)
    if not shared_counts:raise SystemExit('Missing shared scalar-FPU handler validation coverage')
    shared_receipt={'pass':True,'operation_cases':int(shared_counts[1]),'reduction_cases':int(shared_counts[2]),'forms':45,'masked_exception_flags':True,'raw_vf_input':True,'vstart_zero_required':True,'fs_dirty_checked':True,'rtl_certified':False,'log_sha256':digest(HERE/'native-handler-selftest.log')}
    (HERE/'shared-selftest.json').write_text(json.dumps(shared_receipt,indent=2)+'\n')
    cmp_counts=re.search(r'fpcomp_handlers=(\d+) oracle_cases=(\d+) forms=22 all3harts source_flags signed_zero mask_tail altfmt FS vstart illegal_sew8=132 generic_semantics=9 core_priority=6 config_refusals=2 pass',native.stdout)
    if not cmp_counts:raise SystemExit('Missing source FPComp handler validation coverage')
    cmp_receipt={'pass':True,'handler_executions':int(cmp_counts[1]),'operation_cases':int(cmp_counts[2]),'forms':22,'illegal_sew8_cases':132,'generic_semantics_cases':9,'core_priority_cases':6,'vector_config_refusals':2,'source_selected_chunk_flags':True,'mask_tail_checked':True,'source_altfmt_checked':True,'rtl_certified':False,'log_sha256':digest(HERE/'native-handler-selftest.log')}
    (HERE/'fpcomp-selftest.json').write_text(json.dumps(cmp_receipt,indent=2)+'\n')
    csr=subprocess.run(['bash',str(HERE/'run_csr_selftest.sh')],env=env,text=True,capture_output=True)
    (HERE/'csr-handler-selftest.log').write_text(csr.stdout+csr.stderr)
    if csr.returncode:raise SystemExit(csr.stdout+csr.stderr)
    counts=re.search(r'hpm_source_checks=(\d+) csr_instructions=(\d+) harts=3 isa_profiles=2 hardware_hpm=0 generic_preserved pass',csr.stdout)
    if not counts or (int(counts[1]),int(counts[2]))!=(1656,2031):raise SystemExit('Missing source CSR handler coverage')
    (HERE/'csr-selftest.json').write_text(json.dumps({'pass':True,'checks':int(counts[1]),'actual_csr_instructions':int(counts[2]),'harts':3,'isa_profiles':2,'hardware_hpm_count':0,'generic_preserved':True,'log_sha256':digest(HERE/'csr-handler-selftest.log'),'binary_sha256':digest(binary),'overlay_sha256':digest(HERE/'iris.patch'),'rtl_certified':False},indent=2)+'\n')
    receipt_args=[]
    for name in ['live','board','plic','memory','uart']:
        path=getattr(args,name+'_receipt')
        if path is not None:receipt_args += ['--'+name+'-receipt',str(path.resolve())]
    subprocess.run(['python3',str(HERE/'run_functional.py'),'--dtc',args.dtc,*receipt_args],env=env,check=True)

if __name__=='__main__':main()
