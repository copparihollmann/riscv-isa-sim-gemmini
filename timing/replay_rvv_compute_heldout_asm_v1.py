#!/usr/bin/env python3
"""Freeze actual model predictions without opening protected hardware timings.

The controlled debugger stop follows all measurements and precedes UART. It
does not establish normal guest exit, end-to-end performance or simulation speed.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
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
sys.path.insert(0, str(ROOT / 'firesim'))
from iris_model.guest_regions import Instructions
from rvv_compute_heldout_asm_review import ELF, inspect, proof, validator

READY = 'bdb33551771c34c9af11b438aa417c7b4bbf45ced4d7cbc780180a6b34790a27'
PLAN = '96f1a2164f68db556393f50f329e4f698c136e17424d7ac33cc1eac478f5f06e'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def need(condition, message):
    if not condition:
        raise ValueError(message)


def verify_bindings(bindings):
    for path, expected in bindings.items():
        need(sha(path) == expected, 'Changed bound input/output: ' + path)


def decode(text, corpus, elf):
    lines = text.splitlines()
    need(lines and lines[0] == ':' and
         all(re.fullmatch(r'0x[0-9a-f]{16}', line) for line in lines[1:]),
         'Exact debugger value stream')
    values = [int(line, 16) for line in lines[1:]]
    need(len(values) == 2 + 1320 * 17 + 2 + 3 and values[:2] == [0, 1320]
         and values[-5:-3] == [0, 1320], 'Stable completed sentinel/count and all records')
    expected = validator().canonical(corpus)
    rows = []
    for index, wanted in enumerate(expected):
        ci, hart, start, issue, end, ir0, ir1, ir2, actual, program_expected, mismatch, \
            checked, vl, t0, t1, ip0, ip1 = values[2 + 17 * index:2 + 17 * (index + 1)]
        need(ci == index and hart == wanted['hart'], 'Compiled record order/hart')
        need(start < issue <= end and ir0 <= ir1 <= ir2 and t0 <= t1,
             'Ordered actual phase counters')
        row = dict(wanted, start_cycle=start, issue_cycle=issue, end_cycle=end,
                   instret_delta=ir2-ir0, issue_instret_delta=ir1-ir0,
                   drain_instret_delta=ir2-ir1, checksum=actual,
                   expected_checksum=program_expected, mismatch_or=mismatch,
                   checked_words=checked, vl=vl, mtime_before=t0, mtime_after=t1,
                   msip_before=ip0, msip_after=ip1)
        need(all(type(row[key]) is type(value) and row[key] == value
                 for key, value in wanted.items()), 'Independent complete element/count/checksum golden')
        need(row['issue_instret_delta'] >= wanted['operations'], 'Actual instruction-count lower bound')
        case = corpus['cases'][index]
        row.update(internal_split=case['internal_split'],
                   semantic_parent_case_id=case['semantic_parent_case_id'])
        rows.append(row)
    binary = proof.Elf(elf.read_bytes())
    waiting = {pc + delta for pc, size, word in proof.instructions(binary, 'benchmark_main')
               if size == 4 and word == 0x10500073 for delta in (0, 4, 8)}
    need(values[-3] in waiting and values[-1] in waiting, 'Actual hart0/2 compiled WFI loops')
    return rows


def qualify_prefix(path, rows, elf, rom):
    raw = path.read_bytes()
    need(raw.endswith(b'\n'), 'Flushed actual counter-prefix records')
    prefixes = [json.loads(line) for line in raw.splitlines()]
    need(len(prefixes) == 3960, 'Exactly three mcycle endpoints per case')
    code, previous, lookup = Instructions(elf, rom), {}, {}
    for item in prefixes:
        hart, sequence = item['hart'], item['sequence']
        need(type(hart) is int and hart in (0, 1) and type(sequence) is int
             and sequence > previous.get(hart, -1), 'Ordered typed endpoint ownership')
        previous[hart] = sequence
        for key in ('value', 'read_cycle', 'pc', 'raw', 'csr', 'destination'):
            need(type(item[key]) is int and item[key] >= 0, 'Typed actual CSR field')
        word = item['raw']
        need(word == code.read(item['pc']) and word & 127 == 0x73 and word >> 20 in (0xb00, 0xc00)
             and item['csr'] == word >> 20 and item['destination'] == (word >> 7) & 31
             and item['result_discarded'] is False, 'Exact returning counter opcode from this ELF')
        key = hart, item['value']
        need(key not in lookup, 'Unique actual counter observation')
        lookup[key] = item
    for row in rows:
        endpoints = [lookup[row['hart'], row[key]] for key in ('start_cycle', 'issue_cycle', 'end_cycle')]
        need(endpoints[0]['sequence'] < endpoints[1]['sequence'] < endpoints[2]['sequence']
             and endpoints[0]['read_cycle'] < endpoints[1]['read_cycle'] <= endpoints[2]['read_cycle'],
             'Actual source-clock CSR endpoint order')
        for label, endpoint in zip(('begin', 'issue', 'drain'), endpoints):
            row[label + '_pc'] = endpoint['pc']
            row[label + '_global_read_cycle'] = endpoint['read_cycle']
    identities = {item['calibration_identity'] for item in prefixes}
    need(len(identities) == 1, 'One executed fixture identity')
    return next(iter(identities))


def main(args):
    build, out, capsule, fixture, plan = [p.resolve() for p in
        (args.build, args.output, args.capsule, args.fixture, args.plan)]
    need(args.timeout > 0, 'Positive owned timeout required')
    need(sha(build / 'ready.json') == READY and sha(plan) == PLAN, 'Frozen packet and prevalidation policy')
    ready = json.loads((build / 'ready.json').read_text())
    verify_bindings({str(build / name): digest for name, digest in ready['artifact_sha256'].items()})
    need(sha(capsule / 'manifest.json') == args.capsule_sha256, 'Exact preselected capsule')
    manifest = json.loads((capsule / 'manifest.json').read_text())
    verify_bindings({str(capsule / name): digest for name, digest in manifest['artifact_sha256'].items()})
    need(sha(capsule / 'spike') == manifest['binary_sha256'] and
         sha(capsule / 'libsifive_uart.so') == manifest['uart_sha256'], 'Exact native/UART pair')
    elf = build / 'guest.elf'
    need(sha(elf) == ELF, 'Exact protected compiled ELF')
    corpus = json.loads((build / 'corpus.json').read_text())
    layout = json.loads((build / 'layout.json').read_text())
    inspect(elf.read_bytes(), corpus, layout)
    out.mkdir(parents=True, exist_ok=False)
    address = lambda name: layout['objects'][name]['address']
    commands = ['rs 0', f'while mem {address("rvv_measurements_done"):x} ffffffffffffffff',
                f'mem {address("rvv_measurements_done"):x}', f'mem {address("rvv_record_count"):x}']
    commands += [f'mem {address("rvv_records") + 192 * i + 8 * j:x}'
                 for i in range(1320) for j in range(17)]
    commands += [f'mem {address("rvv_measurements_done"):x}', f'mem {address("rvv_record_count"):x}',
                 'pc 0', 'pc 1', 'pc 2', 'quit']
    (out / 'commands.txt').write_text('\n'.join(commands) + '\n')
    dma = 'rv64gcv_zfh_zvfh_zvl256b_zvbb'
    compute = ('rv64gcv_zfh_zvfh_zba_zbb_zbs_zvbb_zvl256b_zvfofp8min_zvfbfmin_zvfbfa_'
               'zvt32t_zvti8i32mm_zvtofp8fmm')
    rom, dtb = ROOT / 'board/evidence/bootrom.rv64.img', ROOT / 'board/build/iris.dtb'
    argv = [str(capsule / 'spike'), '-d', '--debug-cmd=' + str(out / 'commands.txt'),
            '--iris-timing-fixture=' + str(fixture), '--iris-timing-trace=' + str(out / 'native-summary.json'),
            '--extlib=' + str(capsule / 'libsifive_uart.so'), '--iris-vme', '--isa=' + dma,
            '--hart-isa=0:' + compute, '--hart-isa=1:' + compute, '--hart-isa=2:' + dma, '-p3',
            '-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000',
            '--device=sifive_uart,0x10020000', '--iris-bootrom=' + str(rom), '--dtb=' + str(dtb), str(elf)]
    files = [Path(__file__).resolve(), capsule / 'manifest.json', capsule / 'spike',
             capsule / 'libsifive_uart.so', fixture, elf, build / 'ready.json', build / 'corpus.json',
             build / 'layout.json', build / 'qualification.json', out / 'commands.txt', plan, rom, dtb,
             ROOT / 'firesim/rvv_compute_heldout_asm_review.py',
             ROOT / 'benchmarks/rvv_compute_heldout_asm_v1/validate.py']
    inputs = {str(path): sha(path) for path in files}
    qualification = json.loads((build / 'qualification.json').read_text())
    verify_bindings(qualification['input_sha256'])
    inputs.update(qualification['input_sha256'])
    env = {key: value for key, value in os.environ.items()
           if not key.startswith('IRIS_EMPIRICAL_') and key != 'IRIS_FATAL_PCS'}
    env['IRIS_EMPIRICAL_FEATURES'] = str(out / 'features.jsonl')
    if args.async_trace:
        env['IRIS_EMPIRICAL_ASYNC_TRACE'] = str(out / 'async.jsonl')
    helper_path = ROOT / 'spike/empirical_launch_v2.py'
    helper_spec = importlib.util.spec_from_file_location('heldout_fatal_elf', helper_path)
    helper = importlib.util.module_from_spec(helper_spec)
    helper_spec.loader.exec_module(helper)
    env['IRIS_FATAL_PCS'] = ','.join(hex(v) for v in sorted(set(helper.fatal_addresses(elf).values())))
    inputs[str(helper_path)] = sha(helper_path)
    report = dict(schema='iris.protected_ASM_frozen_prediction.v1', status='running',
                  argv=argv, input_sha256=inputs, hardware_contacted=False,
                  reserved_timing_labels_consumed=False, fit_performed=False,
                  normal_guest_exit_verified=False, intentional_postmeasurement_debugger_stop=True,
                  whole_run_timing_or_speed_claim=False, diagnostic_only=args.diagnostic_only)
    def save():
        (out / 'run.json').write_text(json.dumps(report, indent=2) + '\n')
    save()
    started = time.monotonic()
    with (out / 'stdout').open('w') as stdout, (out / 'stderr').open('w') as stderr:
        process = subprocess.Popen(argv, stdout=stdout, stderr=stderr, env=env, start_new_session=True)
        report['pid'] = process.pid
        save()
        try:
            report['debugger_exit_status'] = process.wait(timeout=args.timeout)
            report['timed_out'] = False
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            report.update(debugger_exit_status=process.returncode, timed_out=True)
    report['host_seconds'] = time.monotonic() - started
    try:
        need(report['debugger_exit_status'] == 0 and not report['timed_out'], 'Complete model measurement readback')
        rows = decode((out / 'stderr').read_text(), corpus, elf)
        identity = qualify_prefix(out / 'features.jsonl', rows, elf, rom)
        need([line.split()[2] for line in fixture.read_text().splitlines()
              if line.startswith('empirical_profile ')] == [identity], 'Executed exact fixture identity')
        verify_bindings(inputs)
        (out / 'regions.jsonl').write_text(''.join(json.dumps(row, sort_keys=True) + '\n' for row in rows))
        report.update(status='completed_all1320_measurements_with_controlled_debugger_stop',
                      **{'pass': True}, regions=1320, complete_per_element_goldens=184128,
                      actual_CSR_ELF_endpoint_joins=3960, actual_mcycle_prefix_records=3960,
                      train_regions=0, reserved_regions=1320, calibration_identity=identity)
    except (ValueError, KeyError, OSError, TypeError) as error:
        report.update(status='failed', **{'pass': False}, error=str(error))
    report['output_sha256'] = {str(path): sha(path) for path in out.iterdir()
        if path.name in ('stdout', 'stderr', 'features.jsonl', 'regions.jsonl', 'native-summary.json', 'async.jsonl')}
    save()
    if report['pass'] and not args.diagnostic_only:
        freeze = dict(schema='iris.protected_ASM_prediction_freeze.v1', **{'pass': True},
                      frozen_at_utc=datetime.now(timezone.utc).isoformat(),
                      protected_timing_labels_consumed=False, fitting_permitted=False,
                      source_plan_sha256=PLAN, capsule_manifest_sha256=args.capsule_sha256,
                      fixture_sha256=sha(fixture), run_sha256=sha(out / 'run.json'),
                      input_sha256=inputs, output_sha256=report['output_sha256'])
        (out / 'freeze.json').write_text(json.dumps(freeze, indent=2) + '\n')
    print(json.dumps({key: report.get(key) for key in ('pass', 'status', 'regions', 'host_seconds', 'error')}))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    for name in ('build', 'output', 'capsule', 'fixture', 'plan'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--capsule-sha256', required=True)
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--async-trace', action='store_true')
    parser.add_argument('--diagnostic-only', action='store_true',
                        help='Exercise the replay/parser; do not create a selected-prediction freeze')
    raise SystemExit(main(parser.parse_args()))
