#!/usr/bin/env python3
"""Saved whole OPU array versus an independent physical-state/readout oracle."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from hardware.fpcomp_unit.check import closure


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def corpus(path, pipelined=False):
    oracle = ROOT / 'spike/generate_fp8_cases.py'
    spec = importlib.util.spec_from_file_location('independent_array_fp8', oracle)
    arithmetic = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(arithmetic)
    state = [[[0 for c in range(16)] for r in range(16)] for slot in range(16)]
    records = []
    special = [0, 0x80, 1, 0x7f, 0xff, 0x7c, 0xfc, 0x38, 0x3c, 0x7e, 0xfe, 0x40, 0x20, 0x91, 0x69, 0xbc]
    for fa in range(2):
        for fb in range(2):
            for rm in range(5):
                for sample in range(4):
                    index = len(records)
                    rows = [16 if pipelined else 0, 1, 7, 16][sample]
                    cols = [16, 5, 15, 16][sample]
                    slots = [(index + 3 * cr) % 16 for cr in range(4)]
                    left = [special[(r + index) % 16] for r in range(16)]
                    upper = [special[(3 * c + 5 * index + 1) % 16] for c in range(16)]
                    expected = []
                    for r in range(16):
                        for c in range(16):
                            slot = slots[r // 4]
                            if r < rows and c < cols:
                                state[slot][r][c] = arithmetic.fma(left[r], upper[c], state[slot][r][c], fa, fb, rm)
                            expected.append(state[slot][r][c])
                    records.append([index, fa, fb, rm, (1 << rows) - 1, (1 << cols) - 1, *slots, *left, *upper, *expected])
    magic = 'IRIS_ARRAY_FP8_V2' if pipelined else 'IRIS_ARRAY_FP8_V1'
    path.write_text(magic + ' ' + str(len(records)) + '\n' + ''.join(' '.join(map(str, row)) + '\n' for row in records))
    return len(records)


def bindings(path, sv):
    declarations = ['CData shift_zero=0;']
    seen = set()

    def field(name):
        seen.add(name)
        return '&top.' + name

    for member, name in [('left', 'in_l'), ('upper', 'in_t'), ('row_en', 'row_en'), ('col_en', 'col_en')]:
        rows = ['{{' + ','.join(field(f'io_op_{name}_{i}_{j}') for j in range(4)) + '}}' for i in range(4)]
        declarations.append('std::array<std::array<CData*,4>,4> ' + member + '{{' + ','.join(rows) + '}};')
    for member, name in [('mrf', 'mrf_idx'), ('row_idx', 'row_idx'), ('col_idx', 'col_idx'), ('macc', 'macc'),
                         ('zero', 'zero'), ('mvin', 'mvin'), ('mvin_col', 'mvin_col'), ('mv_en', 'mv_en')]:
        declarations.append('std::array<CData*,4> ' + member + '{{' + ','.join(field(f'io_op_{name}_{i}') for i in range(4)) + '}};')
    declarations.append('std::array<CData*,4> shift{{&shift_zero,' + ','.join(field(f'io_op_shift_{i}') for i in range(1, 4)) + '}};')
    declarations.append('std::array<IData*,4> output{{' + ','.join('&top.io_out_' + str(i) for i in range(4)) + '}};')
    seen.update('io_op_' + n for n in ('signed_l', 'signed_t', 'fp8', 'e5m2_l', 'e5m2_t', 'rm'))
    actual = set(re.findall(r'input\s+(?:\[[^\]]+\]\s+)?(io_op_\w+)', sv.read_text()))
    if seen != actual:
        raise ValueError('saved array port profile differs: ' + repr(seen ^ actual))
    path.write_text('\n'.join(declarations) + '\n')
    return len(actual)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--pipeline', action='store_true', help='Four consecutive independent FP8 entries per format/rounding group')
    args = parser.parse_args()
    out = args.output.resolve()
    if args.verify:
        receipt = json.loads((out / 'results.json').read_text())
        for name, digest in receipt['artifact_sha256'].items():
            path = (out / name).resolve()
            if not path.is_relative_to(out) or sha(path) != digest:
                raise ValueError('changed/escaped array proof artifact')
        for original, digest in receipt['input_sha256'].items():
            if sha(out / 'inputs' / digest) != digest:
                raise ValueError('changed archived input ' + original)
        binary = out / 'model/VOuterArray'
        run = subprocess.run([binary, out / 'fp8-cases.txt'], capture_output=True, text=True, timeout=120)
        if run.returncode or json.loads(run.stdout) != receipt['checks']:
            raise ValueError('array replay disagrees with frozen proof')
        if any(c['exit_status'] == 0 for c in receipt['negative_controls']):
            raise ValueError('missing array negative control')
        print(json.dumps(dict(verified=True, **receipt['checks'], full_soc_certified=False)))
        return
    out.mkdir(parents=True, exist_ok=False)
    count = corpus(out / 'fp8-cases.txt', args.pipeline)
    rtl = ROOT / 'build/rtl-verilator'
    base = json.loads((rtl / 'manifest.json').read_text())
    paths = closure('OuterProductUnit', rtl / 'gen-collateral')
    for path in paths:
        if sha(path) != base['sim_source_sha256'].get(str(path)):
            raise ValueError('changed generated array RTL')
    port_count = bindings(out / 'port_bindings.inc', rtl / 'gen-collateral/OuterProductUnit.sv')
    tool = Path('/scratch/eygao/iris-cy/.conda-env')
    perl, verilator, vroot = tool / 'bin/perl', tool / 'bin/verilator', tool / 'share/verilator'
    compiler = Path(shutil.which('g++')).resolve()
    model = out / 'model'
    argv = [perl, verilator, '--cc', '--exe', '--build', '-j', '4', '--top-module', 'OuterProductUnit',
            '--prefix', 'VOuterArray', '-O3', '-Wno-fatal', '--Mdir', model,
            '-CFLAGS', '-std=c++20 -I' + str(out),
            '-MAKEFLAGS', 'CXX=' + str(compiler) + ' LINK=' + str(compiler) + ' AR=ar RANLIB=ranlib',
            *paths, HERE / 'driver.cc']
    started = time.monotonic()
    build = subprocess.run(list(map(str, argv)), env=dict(os.environ, VERILATOR_ROOT=str(vroot)), capture_output=True, text=True, timeout=600)
    (out / 'build.log').write_text(build.stdout + build.stderr)
    if build.returncode:
        raise RuntimeError('array build failed; inspect preserved build.log')
    binary = model / 'VOuterArray'
    runstart = time.monotonic()
    run = subprocess.run([binary, out / 'fp8-cases.txt'], capture_output=True, text=True, timeout=120)
    seconds = time.monotonic() - runstart
    (out / 'stdout').write_text(run.stdout)
    (out / 'stderr').write_text(run.stderr)
    if run.returncode:
        raise RuntimeError('array mismatch; inspect preserved stderr')
    checks = json.loads(run.stdout)
    negative = []
    lines = (out / 'fp8-cases.txt').read_text().splitlines()
    changed = lines[:]
    # First actual active FP8 row is index1: row0/column0. Repairing the corpus
    # syntax must not conceal an incorrect independent arithmetic result.
    record = changed[2].split()
    record[42] = str(int(record[42]) ^ 1)
    changed[2] = ' '.join(record)
    for name, text in [('wrong-golden', '\n'.join(changed) + '\n'), ('truncated', '\n'.join(lines[:-1]) + '\n')]:
        path = out / (name + '.txt')
        path.write_text(text)
        result = subprocess.run([binary, path], capture_output=True, text=True, timeout=120)
        (out / (name + '.stdout')).write_text(result.stdout)
        (out / (name + '.stderr')).write_text(result.stderr)
        if result.returncode == 0:
            raise ValueError('array admitted invalid corpus ' + name)
        negative.append(dict(name=name, exit_status=result.returncode, stderr=name + '.stderr'))
    sources = [*paths, HERE / 'driver.cc', Path(__file__), out / 'port_bindings.inc', ROOT / 'spike/generate_fp8_cases.py',
               rtl / 'manifest.json', ROOT / 'hardware/manifest.json', compiler, perl, verilator,
               ROOT / 'third_party/saturn/src/main/scala/exu/OuterProductUnit.scala']
    # Retain actual compiler prerequisites, including generated model headers.
    for dep in model.glob('*.d'):
        text = dep.read_text().replace('\\\n', ' ')
        for item in text.split(':', 1)[-1].split():
            path = Path(item)
            if not path.is_absolute():
                path = model / path
            if path.is_file():
                sources.append(path.resolve())
    ldd = subprocess.check_output(['ldd', binary], text=True)
    (out / 'ldd.txt').write_text(ldd)
    if 'not found' in ldd:
        raise ValueError('missing array runtime library')
    for path in re.findall(r'(?:=>\s*)?(/[^\s]+)', ldd):
        if Path(path).is_file():
            sources.append(Path(path))
    (out / 'inputs').mkdir()
    inputs = {}
    for path in sources:
        path = path.resolve()
        digest = sha(path)
        target = out / 'inputs' / digest
        if not target.exists():
            shutil.copyfile(path, target)
        inputs[str(path)] = digest
    receipt = dict(schema='iris.saved_opu_array_proof.v1', checks=checks, fp8_records=count, port_inputs_checked=port_count,
                   source_fir_sha256=base['source_fir_sha256'], input_sha256=inputs, build_argv=list(map(str, argv)),
                   compiler_version=subprocess.check_output([compiler, '--version'], text=True),
                   binary_sha256=sha(binary), build_and_run_seconds=time.monotonic() - started,
                   native_seconds=seconds, native_array_edges_per_second=checks['native_edges'] / seconds,
                   negative_controls=negative,
                   scope='Physical saved array only: independent initialized MRF, row/column write routing, vertical readout chain, enables, integer and sequential FP8; no instruction decoder/sequencer/VRF/OS/whole-SoC timing qualification.',
                   uninitialized_state_assumed_zero=False, scalar_or_vector_instruction_throughput_measured=False,
                   source_clock_gating_qualified=False, timing_calibrated=False, full_soc_certified=False,
                   matches_ethan_firesim_image=False, hardware_contacted=False)
    receipt['artifact_sha256'] = {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file() and not p.is_relative_to(out / 'inputs')}
    (out / 'results.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(checks))


if __name__ == '__main__':
    main()
