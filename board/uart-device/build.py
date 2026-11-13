#!/usr/bin/env python3
"""Build an isolated db964-derived UART clock adapter; never edit primary artifacts."""
import argparse,hashlib,json,os,re,shlex,shutil,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
PIN='72958551566a30f19444bd7e354552824e4d0a98'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=ROOT/'build/uart-device');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);(out/'build.json').unlink(missing_ok=True)
    source=ROOT/'third_party/spike-uart-dev';base=ROOT/'third_party/riscv-isa-sim';primary=ROOT/'spike/build';native=out/'native';native.mkdir(exist_ok=True);helper=out/'helper';helper.mkdir(exist_ok=True)
    if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()!=PIN:raise RuntimeError('Wrong native base pin')
    overlay=subprocess.check_output(['git','-C',str(source),'diff','--binary','HEAD']);patch=HERE/'native-overlay.patch'
    if overlay!=patch.read_bytes():raise RuntimeError('UART native worktree differs from explicit cumulative overlay')
    base_snapshot=ROOT/'build/snapshot-db964603'
    if sha(ROOT/'spike/bin/spike-iris-functional')!='db964603d91ffb19f7e63dde0e14397635b879559011f1da8acaf5ecd06319a8' or sha(base_snapshot/'iris.patch')!='450a9418864ab562255eb0635cdda15414a709d8d6241fcd038918da027223e2':raise RuntimeError('Requires the frozen matching db964 primary build SDK')
    text=(ROOT/'board/iris_uart.hpp').read_text();needle='  // RX decoding/sampling is intentionally separate.'
    addition='''  // Read-only scheduler query; original register/state behavior is unchanged.
  std::optional<uint64_t> next_tx_event_cycles() const {
    if (!tx_busy()) return tx_enable_ && tx_.count ? std::optional<uint64_t>(1) : std::nullopt;
    return uint64_t(tx_prescaler_) + 1 +
      uint64_t(tx_bits_remaining_ - 1) * (uint64_t(divisor_) + 1);
  }

'''
    if text.count(needle)!=1:raise RuntimeError('Review updated source-backed UART helper before extending scheduler query')
    (helper/'iris_uart.hpp').write_text(text.replace(needle,addition+needle))
    originals=[primary/name for name in ['libriscv.a','libspike_main.a','libdisasm.a','libsoftfloat.a','libfesvr.a','libfdt.a','spike.o','extension.o']]
    originals+=list(primary.glob('*.h'));inputs={str(p):sha(p) for p in originals};inputs.update({str(p):sha(p) for p in [ROOT/'board/iris_uart.hpp',HERE/'clocked_uart.hpp',HERE/'plugin.cc',HERE/'clock_test.cpp',Path(__file__),patch,helper/'iris_uart.hpp']})
    evidence=ROOT/'board/uart-source-evidence.json';audit=json.loads(evidence.read_text())
    if audit['facts']['firesim_override']['value']!={'tx_entries':256,'rx_entries':256,'requested_baud_rate':3686400}:raise RuntimeError('Review changed UART geometry')
    clocks=ROOT/'hardware/evidence/firesim-clocks.freq-summary'
    rates=re.search(r'Output clock uart_clock, requested: ([\d.]+) MHz, actual: ([\d.]+) MHz',clocks.read_text())
    if not rates or tuple(map(float,rates.groups()))!=(500.0,500.0):raise RuntimeError('Source UART clock changed/unknown')
    for item in audit['sources'].values():
        path=ROOT/'board'/item['snapshot']
        if sha(path)!=item['sha256']:raise RuntimeError('UART RTL snapshot changed: '+str(path))
        inputs[str(path.resolve())]=sha(path)
    for path in [evidence,clocks,ROOT/'hardware/memory-paths.json',ROOT/'board/tests/uart_test.cpp',base_snapshot/'provenance.json',base_snapshot/'iris.patch',Path('/usr/bin/g++'),*ROOT.joinpath('timing').glob('*.hpp')]:inputs[str(path)]=sha(path)
    commands=[];start=time.perf_counter()
    def execute(cmd,name,cwd=native):
        log=out/(name+'.log')
        with log.open('w') as stream:r=subprocess.run(cmd,cwd=cwd,stdout=stream,stderr=subprocess.STDOUT)
        commands.append({'argv':cmd,'exit_status':r.returncode,'log_sha256':sha(log)})
        if r.returncode:raise RuntimeError(name+' failed; see '+str(log))
    for original in originals:
        target=native/original.name
        execute(['cp','--reflink=auto','--preserve=mode,timestamps',str(original),str(target)],'copy-'+original.name)
    # Reuse the frozen matching native objects, replace only sim.cc's model-clock
    # dispatch, then relink. The optional interface does not change sim_t/base ABI.
    dry=subprocess.run(['make','-n','-W',str(base/'riscv/sim.cc'),'sim.o'],cwd=primary,capture_output=True,text=True,check=True)
    line=next(x for x in dry.stdout.splitlines() if ' -c ' in x and str(base/'riscv/sim.cc') in x)
    compile=[x.replace(str(base),str(source)) for x in shlex.split(line)]
    execute(compile,'compile-sim')
    execute(['ar','r',str(native/'libriscv.a'),str(native/'sim.o')],'archive-sim')
    link=['/usr/bin/g++','-L.','-Wl,--export-dynamic','extension.o','-o','spike.unstripped','spike.o','libspike_main.a','libriscv.a','libdisasm.a','libsoftfloat.a','libfesvr.a','libfdt.a','-lpthread']
    execute(link,'link');execute(['strip','-o','spike','spike.unstripped'],'strip')
    includes=['-I'+str(source),'-I'+str(native),'-iquote',str(source/'riscv'),'-iquote',str(source/'fesvr'),'-I'+str(helper),'-I'+str(HERE)]
    execute(['/usr/bin/g++','-std=c++20','-O2','-Wall','-Wextra','-Werror',*includes,str(HERE/'clock_test.cpp'),'-o','clock_test'],'compile-clock-tests')
    execute([str(native/'clock_test')],'clock-tests')
    execute(['/usr/bin/g++','-std=c++20','-O2','-Wall','-Wextra','-Werror',*includes,'-I'+str(ROOT/'board'),str(ROOT/'board/tests/uart_test.cpp'),'-o','helper_test'],'compile-helper-tests')
    execute([str(native/'helper_test')],'helper-tests')
    execute(['/usr/bin/g++','-std=c++20','-O2','-fPIC','-shared',*includes,str(HERE/'plugin.cc'),'-o','libsifive_uart.so'],'compile-plugin')
    if any(sha(path)!=digest for path,digest in inputs.items()):raise RuntimeError('Build inputs changed during isolated native build')
    result={'schema':'iris.uart.native_build.v1','status':'built_and_unit_passed','upstream_spike_sha':PIN,'base_native_binary_sha256':'db964603d91ffb19f7e63dde0e14397635b879559011f1da8acaf5ecd06319a8','cumulative_overlay_sha256':hashlib.sha256(overlay).hexdigest(),'input_sha256':inputs,'commands':commands,'binary_sha256':sha(native/'spike'),'uart_sha256':sha(native/'libsifive_uart.so'),'host_seconds':time.perf_counter()-start,'physical_uart_clock_hz':500000000,'rtc_hz':500000,'native_device_abi':1,'primary_modified':False,'rtl_certified':False,'rx_sampling_certified':False}
    (out/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':result['status'],'binary_sha256':result['binary_sha256'],'uart_sha256':result['uart_sha256']}))
if __name__=='__main__':main()
