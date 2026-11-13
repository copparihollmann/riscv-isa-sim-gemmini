#!/usr/bin/env python3
"""Exercise the UART in ordinary three-hart processes and exact live clocks."""
import argparse,hashlib,json,os,shlex,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from spike.run_functional import command
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,default=ROOT/'build/uart-device');p.add_argument('--output',type=Path,default=ROOT/'build/uart-device-check');p.add_argument('--runtime',type=Path,default=ROOT/'benchmarks/runtime.c')
    p.add_argument('--binary',type=Path);p.add_argument('--plugin',type=Path);p.add_argument('--build-receipt',type=Path)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);(out/'results.json').unlink(missing_ok=True)
    binary=(a.binary or a.build/'native/spike').resolve();plugin=(a.plugin or a.build/'native/libsifive_uart.so').resolve();build_receipt=(a.build_receipt or a.build/'build.json').resolve();identity=[sha(binary),sha(plugin)];cc=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc')
    common=[str(cc),'-O2','-g','-Wall','-Wextra','-Wno-unused-variable','-Wno-unused-function','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zicsr_zifencei','-I'+str(ROOT/'benchmarks')]
    runtime=out/'runtime.o';dependencies=out/'runtime.d'
    subprocess.run(common+['-MMD','-MF',str(dependencies),'-Dtrap_dispatch=base_trap_dispatch','-c',str(a.runtime.resolve()),'-o',str(runtime)],check=True,capture_output=True)
    runtime_inputs=[Path(x).resolve() for x in shlex.split(dependencies.read_text().replace('\\\n',' ').split(':',1)[1])]
    fixture=(ROOT/'timing/fixtures/three-hart-slow.fixture').read_text();(out/'uart-live.fixture').write_text(fixture)
    source_clock=fixture.replace('base_hz 100000000','base_hz 500000000').replace('rtc_divider 200','rtc_divider 1000').replace('hart 2 2 1','hart 2 1 1')
    (out/'uart-source-clock.fixture').write_text(source_clock)
    # Explicit ideal frame boundary stimulus, not UARTRx pin sampling.
    (out/'rx.frames').write_text('1000000 1001360 0x5a\n')
    cases=[]
    for mode in range(7):
        elf=out/f'mode{mode}.elf';subprocess.run(common+['-DUART_MODE='+str(mode),'-nostdlib','-static','-Wl,--build-id=none,--gc-sections','-T',str(ROOT/'benchmarks/link.ld'),str(ROOT/'benchmarks/start.S'),str(runtime),str(ROOT/'board/uart-device/guest.c'),'-lgcc','-o',str(elf)],check=True,capture_output=True)
        kinds=(['functional','live'] if mode in [0,2,3,4] else ['live'])+(['source-clock'] if mode==1 else [])
        for kind in kinds:
            live=kind!='functional';clockfile=out/('uart-source-clock.fixture' if kind=='source-clock' else 'uart-live.fixture')
            name=f'mode{mode}-'+kind;cmd=command(binary.resolve(),elf);cmd=['--extlib='+str(plugin.resolve()) if x.startswith('--extlib=') else x for x in cmd];cmd[-1:-1]=['--iris-bootrom='+str(ROOT/'board/evidence/bootrom.rv64.img'),'--dtb='+str(ROOT/'board/build/iris.dtb')]
            if live:cmd[-1:-1]=['--iris-timing-fixture='+str(clockfile),'--iris-timing-trace='+str(out/(name+'.graph.json'))]
            env=dict(os.environ);env.pop('IRIS_UART_RX_FRAMES',None)
            if mode==2:env['IRIS_UART_RX_FRAMES']=str(out/'rx.frames')
            start=time.perf_counter();r=subprocess.run(cmd,capture_output=True,env=env,timeout=90);(out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr)
            passed=r.returncode!=0 and b'IRIS_UART_UNKNOWN_RX_DATA' in r.stderr if mode==3 else r.returncode==0 and f'PASSED UART device mode {mode}'.encode() in r.stdout
            if mode in [0,1]:passed &= r.stdout.startswith(bytes(range(256)))
            row={'name':name,'pass':bool(passed),'argv':cmd,'exit_status':r.returncode,'expected_unknown_refusal':mode==3,'host_seconds':time.perf_counter()-start,'elf_sha256':sha(elf),'stdout_sha256':sha(out/(name+'.stdout')),'stderr_sha256':sha(out/(name+'.stderr')),'frame_stimulus_sha256':sha(out/'rx.frames') if mode==2 else None,'fixture_sha256':sha(clockfile) if live else None,'modeled_base_hz':500000000 if kind=='source-clock' else 100000000 if live else None,'graph_sha256':sha(out/(name+'.graph.json')) if live and (out/(name+'.graph.json')).is_file() else None};cases.append(row)
            if not passed:raise RuntimeError(name+' failed; see saved stdout/stderr')
    if identity!=[sha(binary),sha(plugin)]:raise RuntimeError('Device/native identity changed during test')
    # A new plugin must not silently fall back to coarse ticks on an older native.
    old=ROOT/'build/snapshot-db964603/spike-iris-functional';bad=command(old,out/'mode4.elf');bad=['--extlib='+str(plugin.resolve()) if x.startswith('--extlib=') else x for x in bad]
    rejected=subprocess.run(bad,capture_output=True,timeout=15);(out/'old-native.stderr').write_bytes(rejected.stderr)
    if rejected.returncode==0 or b'iris_device_clock_abi_v1' not in rejected.stderr:raise RuntimeError('Mismatched native/plugin pair was accepted')
    inputs=[Path(__file__),ROOT/'board/uart-device/guest.c',a.runtime.resolve(),ROOT/'benchmarks/start.S',ROOT/'benchmarks/link.ld',ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb',build_receipt]
    inputs+=runtime_inputs+[cc]
    record={'schema':'iris.uart.process_tests.v1','status':'passed_uart_process_cases','binary_sha256':identity[0],'uart_sha256':identity[1],'cases':cases,'input_sha256':{str(p):sha(p) for p in inputs},'native_plugin_mismatch_refused':True,'mismatch_exit_status':rejected.returncode,'mismatch_argv':bad,'mismatch_binary_sha256':sha(old),'mismatch_stderr_sha256':sha(out/'old-native.stderr'),'physical_uart_hz':500000000,'rx_input_boundary':'explicit frame start/completion; pin sampling unmodeled','empty_rx_unknown_policy':'fail closed on undefined data byte; status-byte read remains defined','rtl_certified':False,'calibrated_timing':False}
    (out/'results.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({'status':record['status'],'cases':len(cases)}))
if __name__=='__main__':main()
