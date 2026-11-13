#!/usr/bin/env python3
"""Actual fatal/recoverable/normal executions of a byte-bound empirical launcher."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spike.empirical_launch_v2 import launcher_text, fatal_addresses


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(argv, directory, timeout=30):
    directory.mkdir()
    env = dict(os.environ, IRIS_EMPIRICAL_FEATURES=str(directory / 'features.jsonl'))
    env.pop('IRIS_FATAL_PCS', None)
    started = time.monotonic(); timed = False
    with (directory / 'stdout').open('wb') as stdout, (directory / 'stderr').open('wb') as stderr:
        child = subprocess.Popen(argv, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
        try: code = child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed = True; os.killpg(child.pid, signal.SIGTERM)
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired: os.killpg(child.pid, signal.SIGKILL); child.wait()
            code = child.returncode
    result = {'argv': argv, 'exit_status': code, 'timed_out': timed,
            'host_seconds': time.monotonic() - started,
            'stdout_sha256': sha(directory / 'stdout'), 'stderr_sha256': sha(directory / 'stderr'),
            'stdout_path':str(directory / 'stdout'),'stderr_path':str(directory / 'stderr'),
            'execution_receipt':str(directory / 'execution.json')}
    (directory / 'execution.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def assembly(target, symbol=None):
    body = (f'  j {symbol}\n' if symbol else
            '  la t0, recover\n  csrw mtvec,t0\n  .2byte 0\n'
            '  la t0,tohost\n  li t1,1\n  sd t1,0(t0)\n')
    ending = (f'.globl {symbol}\n.type {symbol},@function\n{symbol}:\n  j {symbol}\n' if symbol else
              '.balign 4\nrecover:\n  csrr t0,mcause\n  li t1,2\n  bne t0,t1,bad\n'
              '  csrr t0,mepc\n  addi t0,t0,2\n  csrw mepc,t0\n  mret\n'
              'bad:\n  la t0,tohost\n  li t1,3\n  sd t1,0(t0)\n  j park\n')
    return ('.option norvc\n.section .text.init,"ax",@progbits\n.globl _start\n_start:\n'
            f'  csrr t0,mhartid\n  li t1,{target}\n  bne t0,t1,park\n' + body +
            'park:\n  wfi\n  j park\n' + ending +
            '.section .tohost,"aw",@progbits\n.balign 64\n.globl tohost,fromhost\n'
            'tohost: .dword 0\nfromhost: .dword 0\n')


def main():
    parser = argparse.ArgumentParser(__doc__)
    for name in ('native', 'launcher', 'native-selftest', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    native, launcher = args.native.resolve(), args.launcher.resolve()
    receipt = json.loads(args.native_selftest.read_text())
    if receipt.get('pass') is not True or receipt.get('native_binary_sha256') != sha(native):
        raise ValueError('Exact successful native selftest required')
    original = next(r for r in receipt['runs'] if r['name'] == 'selected')
    fixture = Path(next(v.split('=', 1)[1] for v in original['argv'] if v.startswith('--iris-timing-fixture=')))
    python = Path(sys.executable).resolve()
    if launcher.read_text() != launcher_text(native, sha(native), python, sha(python)):
        raise ValueError('Exact rendered launcher required')
    from spike.check_empirical_parser_v2 import check_parser
    check_parser(out / 'parser-controls')
    compiler = Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc')
    link = ROOT / 'benchmarks/link.ld'; runs = []; inputs = {str(p): sha(p) for p in
        (native, launcher, python, compiler, link, args.native_selftest.resolve(), Path(__file__).resolve(),
         ROOT / 'spike/empirical_launch_v2.py', ROOT / 'spike/check_empirical_parser_v2.py',
         ROOT / 'spike/check_empirical_refusals_v1.py', fixture)}
    for option in original['argv']:
        if option.startswith(('--extlib=', '--iris-bootrom=', '--dtb=')):
            path = Path(option.split('=', 1)[1]); inputs[str(path)] = sha(path)
    def command(program, binary, folder):
        return [str(binary), *[('--iris-timing-trace=' + str(folder / 'native-summary.json')
            if x.startswith('--iris-timing-trace=') else x) for x in original['argv'][1:-1]], str(program)]
    for hart, symbol in enumerate(('z_fatal_error', 'z_riscv_fatal_error', 'k_sys_fatal_error_handler')):
        source = out / ('fatal' + str(hart) + '.S'); elf = source.with_suffix('.elf'); source.write_text(assembly(hart, symbol))
        subprocess.run([str(compiler), '-march=rv64imac_zicsr', '-mabi=lp64', '-nostdlib', '-static',
                        '-Wl,--build-id=none', '-T', str(link), str(source), '-o', str(elf)], check=True)
        nm=compiler.with_name('riscv64-unknown-elf-nm')
        nm_text=subprocess.check_output([str(nm),'-P','--defined-only',str(elf)],text=True)
        matches=[line.split() for line in nm_text.splitlines() if line.split()and line.split()[0]==symbol]
        if len(matches)!=1 or matches[0][1].lower()!='t':raise ValueError('Independent nm fatal code symbol missing/ambiguous')
        fatal_pc=int(matches[0][2],16)
        if fatal_addresses(elf).get(symbol)!=fatal_pc:raise ValueError('Parser disagrees with independent nm code symbol')
        inputs[str(nm)]=sha(nm)
        directory = out / ('fatal' + str(hart)); row = run(command(elf, launcher, directory), directory)
        error = (directory / 'stderr').read_text()
        if (row['timed_out'] or row['exit_status'] == 0
                or not re.search(r'IRIS_FATAL hart=' + str(hart) + r' pc=0x' + format(fatal_pc,'x') + r' .*cause=', error)):
            raise ValueError('Automatic fatal handler did not stop the requested hart: ' + error[-1000:])
        row.update(name='automatic-fatal-hart' + str(hart), fatal_symbol_pc=fatal_pc, **{'pass':True}); runs.append(row)
        inputs[str(source)] = sha(source); inputs[str(elf)] = sha(elf)
    source = out / 'recoverable.S'; source.write_text(assembly(0)); elf = source.with_suffix('.elf')
    subprocess.run([str(compiler), '-march=rv64imac_zicsr', '-mabi=lp64', '-nostdlib', '-static',
                    '-Wl,--build-id=none', '-T', str(link), str(source), '-o', str(elf)], check=True)
    directory = out / 'recoverable'; row = run(command(elf, launcher, directory), directory)
    if row['exit_status'] != 0 or row['timed_out']: raise ValueError('Recoverable illegal instruction did not resume')
    row.update(name='recoverable-illegal-instruction', **{'pass':True}); runs.append(row)
    inputs[str(source)] = sha(source); inputs[str(elf)] = sha(elf)
    numeric = Path(original['argv'][-1]); inputs[str(numeric)] = sha(numeric); parity = []
    for name, binary in [('direct', native), ('wrapped', launcher)]:
        directory = out / name; row = run(command(numeric, binary, directory), directory, 90)
        if row['exit_status'] != 0 or row['timed_out']: raise ValueError('Numeric/clock parity execution failed')
        row.update(name=name, **{'pass':True}); runs.append(row); parity.append((directory / 'stdout').read_bytes())
    if parity[0] != parity[1]: raise ValueError('Launcher changed numeric or program-visible modeled counters')
    strip = compiler.with_name('riscv64-unknown-elf-strip'); stripped = out / 'stripped.elf'
    subprocess.run([str(strip), '--strip-all', '-o', str(stripped), str(numeric)], check=True)
    directory = out / 'stripped'; row = run(command(stripped, launcher, directory), directory)
    if row['exit_status'] == 0 or 'IRIS_LAUNCH_REFUSED' not in (directory / 'stderr').read_text():
        raise ValueError('Missing fatal-symbol coverage did not fail closed')
    row.update(name='stripped-ELF-refusal', **{'pass':True}); runs.append(row)
    inputs[str(strip)] = sha(strip); inputs[str(stripped)] = sha(stripped)
    if any(sha(p) != value for p, value in inputs.items()): raise ValueError('Launcher test input changed')
    outputs = {str(p): sha(p) for p in out.rglob('*') if p.is_file() and p.name in
               ('stdout', 'stderr', 'features.jsonl', 'native-summary.json', 'execution.json', 'parser-report.json')}
    report = {'schema': 'iris.empirical_fatal_launcher_selftest.v2', 'pass': True,
        'native_binary_sha256': sha(native), 'launcher_sha256': sha(launcher), 'fixture_sha256': sha(fixture),
        'parser_policy':'fatal-ELF-exec-v2', 'fatal_symbol_pc_exact_match_verified':True,
        'parser_negative_controls_passed':True, 'fatal_harts_verified': [0, 1, 2], 'recoverable_trap_verified': True,
        'normal_numeric_counter_parity_verified': True, 'stripped_ELF_refused': True,
        'runs': runs, 'hardware_contacted': False, 'input_sha256': inputs, 'output_sha256': outputs}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'pass': True, 'cases': len(runs), 'report_sha256': sha(out / 'report.json')}))


if __name__ == '__main__': main()
