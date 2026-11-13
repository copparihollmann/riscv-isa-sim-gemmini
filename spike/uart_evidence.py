"""Validate finite-UART build/process receipts against their exact source and bytes."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def uart_fixture_evidence(binary,report=None):
    report=Path(report).resolve() if report is not None else ROOT/'build/uart-primary/results.json'
    evidence={}
    def reject(reason):return {'tested':False,'reason':reason},evidence
    if not report.is_file():return reject('UART process evidence not collected')
    receipt=json.loads(report.read_text());evidence[str(report)]=sha(report)
    build_path=ROOT/'spike/device-build.json'
    if not build_path.is_file():return reject('UART paired build receipt missing')
    build=json.loads(build_path.read_text())
    plugin=ROOT/'spike/bin/libsifive_uart.so'
    if any(row.get('binary_sha256')!=sha(binary) or row.get('uart_sha256')!=sha(plugin)
           for row in [receipt,build]):return reject('UART receipt does not match packaged native/plugin bytes')
    if build.get('schema')!='iris.uart.primary_build.v1' or build.get('status')!='built_and_unit_passed':
        return reject('UART primary build receipt invalid')
    if (build.get('native_device_abi'),build.get('physical_uart_clock_hz'),build.get('rtc_hz'))!=(1,500000000,500000):
        return reject('UART clock/ABI provenance inconsistent')
    if build.get('native_overlay_sha256')!=sha(ROOT/'spike/iris.patch'):
        return reject('UART native overlay provenance mismatch')
    required={'board/uart-device/plugin.cc','board/uart-device/clocked_uart.hpp','board/iris_uart.hpp',
              'third_party/riscv-isa-sim/riscv/iris_clocked_device.h','benchmarks/uart_drain.h',
              'benchmarks/uart_drain.S','board/uart-source-evidence.json',
              'hardware/evidence/firesim-clocks.freq-summary','hardware/memory-paths.json'}
    if not {str(ROOT/name) for name in required}.issubset(build.get('input_sha256',{})):
        return reject('UART source/SDK/clock/drain provenance incomplete')
    if {row.get('name') for row in build.get('tests',[])}!={'clock','helper'} or any(
            row.get('pass') is not True for row in build['tests']):
        return reject('UART helper/clock selftests missing or failed')
    if (receipt.get('schema')!='iris.uart.process_tests.v1' or
            receipt.get('status')!='passed_uart_process_cases' or
            receipt.get('native_plugin_mismatch_refused') is not True):
        return reject('UART process receipt invalid or ABI refusal missing')
    expected={'mode0-functional','mode0-live','mode1-live','mode1-source-clock',
              'mode2-functional','mode2-live','mode3-functional','mode3-live',
              'mode4-functional','mode4-live','mode5-live','mode6-live'}
    rows=receipt.get('cases',[]);names=[row.get('name') for row in rows]
    if len(names)!=len(set(names)) or set(names)!=expected:
        return reject('UART process coverage incomplete or duplicated')
    checks=[(build_path,sha(build_path)),(binary,sha(binary)),(plugin,sha(plugin))]
    for record in [build,receipt]:
        for name,digest in record.get('input_sha256',{}).items():checks.append((Path(name),digest))
    if str(build_path) not in receipt.get('input_sha256',{}):
        return reject('UART process receipt omits paired build provenance')
    for row in rows:
        name=row['name'];args=row.get('argv',[])
        if row.get('pass') is not True or not args or Path(args[0]).resolve()!=Path(binary).resolve():
            return reject('UART process case failed or native launch mismatch')
        unknown=name.startswith('mode3-')
        if (row.get('expected_unknown_refusal') is not unknown or type(row.get('exit_status')) is not int or
                (row['exit_status']==0)==unknown):return reject('UART process exit/refusal mismatch')
        checks += [(Path(args[-1]),row['elf_sha256']),
                   (report.parent/(name+'.stdout'),row['stdout_sha256']),
                   (report.parent/(name+'.stderr'),row['stderr_sha256'])]
        for flag,digest in [('--extlib=',sha(plugin))]:
            paths=[arg.split('=',1)[1] for arg in args if arg.startswith(flag)]
            if len(paths)!=1:return reject('UART plugin launch provenance missing')
            checks.append((Path(paths[0]),digest))
        live=not name.endswith('-functional')
        for flag,key in [('--iris-timing-fixture=','fixture_sha256'),('--iris-timing-trace=','graph_sha256')]:
            paths=[arg.split('=',1)[1] for arg in args if arg.startswith(flag)]
            if live:
                if len(paths)!=1 or not row.get(key):return reject('UART live fixture/graph provenance missing')
                checks.append((Path(paths[0]),row[key]))
            elif paths or row.get(key) is not None:return reject('UART functional/live provenance inconsistent')
        if name.startswith('mode2-'):checks.append((report.parent/'rx.frames',row['frame_stimulus_sha256']))
    mismatch=receipt.get('mismatch_argv',[])
    if (not mismatch or receipt.get('mismatch_exit_status')==0 or
            type(receipt.get('mismatch_exit_status')) is not int or
            not receipt.get('mismatch_binary_sha256')):return reject('UART ABI negative launch provenance incomplete')
    checks += [(Path(mismatch[0]),receipt['mismatch_binary_sha256']),
               (report.parent/'old-native.stderr',receipt['mismatch_stderr_sha256'])]
    for path,digest in checks:
        if not path.is_file() or sha(path)!=digest:return reject('UART source/artifact digest mismatch')
        evidence[str(path)]=digest
    if b'iris_device_clock_abi_v1' not in (report.parent/'old-native.stderr').read_bytes():
        return reject('UART ABI negative diagnostic missing')
    for row in rows:
        name=row['name'];out=(report.parent/(name+'.stdout')).read_bytes();err=(report.parent/(name+'.stderr')).read_bytes()
        mode=int(name[4])
        if mode==3:
            if b'IRIS_UART_UNKNOWN_RX_DATA' not in err:return reject('UART unknown-data refusal diagnostic missing')
        elif f'PASSED UART device mode {mode}'.encode() not in out:
            return reject('UART process completion marker missing')
        if mode in [0,1] and not out.startswith(bytes(range(256))):
            return reject('UART finite FIFO byte-order proof missing')
    return {'tested':True,'process_cases':len(rows),'unknown_rx_refusals':2,
            'native_plugin_mismatch_refused':True,'native_device_abi':1,
            'binary_sha256':sha(binary),'uart_sha256':sha(plugin),
            'physical_uart_clock_hz':500000000,'rtc_hz':500000,
            'scope':'source-backed finite TX/RX FIFOs, register semantics, modeled clock deadlines and completion drain',
            'rx_pin_sampling_qualified':False,'rtl_certified':False,'calibrated':False},evidence
