#!/usr/bin/env python3
"""Read completed CPU-layout v2 records without its post-ROI bulk UART loop.

Uses the existing Spike debugger, the unchanged ELF and modeled step(). This is
an intentional post-ROI stop, never a normal guest-exit or whole-run speed claim.
The first qualification must compare its complete prefix with a normal replay.
"""
import argparse
import collections
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
from iris_model.guest_regions import Instructions


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prefix(path):
    raw = Path(path).read_bytes()
    boundary = raw.rfind(b'\n') + 1
    # exit(0) in interactive_quit does not destroy the feature ofstream. Preserve
    # and disclose its incomplete final buffer; never silently discard a row.
    records = [json.loads(line) for line in raw[:boundary].splitlines()]
    if any(row.get('schema') != 'iris.empirical.prefix.v1' for row in records):
        raise ValueError('Unexpected prefix schema')
    return records, len(raw)-boundary


def decode_words(text, proof, observations, instructions):
    lines = text.splitlines()
    if not lines or lines[0] != ':' or any(not re.fullmatch(r'0x[0-9a-f]{16}', v) for v in lines[1:]):
        raise ValueError('Unexpected debugger output, trap or missing initial step marker')
    words = [int(v, 16) for v in lines[1:]]
    if len(words) != 2304*8+4 or words[-4] != 0:
        raise ValueError('Incomplete record dump or nonzero guest failure flag')
    functions = proof['functions']
    if len(functions) != 64 or proof.get('all64_actual_loop_offsets_and_opcode_widths_verified') is not True:
        raise ValueError('Complete actual-ELF layout proof required')
    by_key = collections.defaultdict(list)
    for row in observations:
        by_key[(row['hart'], row['pc'], row['value'])].append(row)
    result = []
    used = set()
    for index in range(2304):
        begin, end, retired, value, counter, loop_pc, begin_pc, end_pc = words[index*8:index*8+8]
        hart, repeat, nindex, findex = index % 3, index//3 % 3, index//9 % 4, index//36
        n = (16, 64, 256, 1024)[nindex]
        fn = functions[findex]
        mode, offset = ('compact' if findex < 32 else 'wide'), 2*(findex % 32)
        if (fn['mode'] != mode or fn['offset'] != offset or value != hart+1+3*n or counter != n
                or retired != 3*n+2+(hart == 2) or begin >= end
                or (loop_pc, begin_pc, end_pc) != (fn['loop_pc'], fn['begin_pc'], fn['end_pc'])):
            raise ValueError('Numeric/counter/PC mismatch at main record '+str(index))
        matched = []
        for pc, cycle in ((begin_pc, begin), (end_pc, end)):
            rows = by_key[(hart, pc, cycle)]
            if len(rows) != 1:
                raise ValueError('Missing/ambiguous actual CSR prefix boundary')
            row = rows[0]
            identity = (hart, row['sequence'])
            if (identity in used or row['csr'] not in (0xB00, 0xC00)
                    or row['result_discarded'] or row['raw'] != instructions.read(pc)):
                raise ValueError('Returning CSR/ELF instruction mismatch')
            used.add(identity)
            matched.append(row)
        if matched[0]['read_cycle'] >= matched[1]['read_cycle'] or matched[0]['sequence'] >= matched[1]['sequence']:
            raise ValueError('Reversed modeled ROI')
        result.append({'case_id': f'cpu.layout.v2.{mode}.off{offset}.n{n}.repeat{repeat}',
            'region': 'loop', 'hart': hart, 'mode': mode, 'loop_offset': offset, 'n': n, 'repeat': repeat,
            'start_cycle': begin, 'end_cycle': end, 'instret_delta': retired, 'checksum': value,
            'expected_checksum': hart+1+3*n, 'counter_end': counter, 'loop_pc': loop_pc,
            'begin_pc': begin_pc, 'end_pc': end_pc, 'pass': True,
            'observation_source': 'post_ROI_debugger_known_memory_readback',
            'begin_read_cycle': matched[0]['read_cycle'], 'end_read_cycle': matched[1]['read_cycle']})
    return result


def analyze(directory, proof_path, normal_prefix=None):
    directory, proof_path = Path(directory).resolve(), Path(proof_path).resolve()
    prepared = json.loads((directory/'prepared.json').read_text())
    receipt = json.loads((directory/'run.json').read_text())
    if receipt['status'] != 'debugger_stopped' or receipt['exit_status'] != 0 or receipt.get('guest_full_completion') is not False:
        raise ValueError('Successful intentional debugger stop required')
    for path, digest in prepared['input_sha256'].items():
        if sha(path) != digest:
            raise ValueError('Changed input: '+path)
    for path, digest in receipt['output_sha256'].items():
        if sha(path) != digest:
            raise ValueError('Changed output: '+path)
    argv = prepared['argv']
    elf = Path(argv[-1])
    proof = json.loads(proof_path.read_text())
    if proof['elf_sha256'] != sha(elf):
        raise ValueError('Actual ELF proof mismatch')
    rom = next(a.split('=', 1)[1] for a in argv if a.startswith('--iris-bootrom='))
    observations, tail = prefix(directory/'features.jsonl')
    rows = decode_words((directory/'stderr').read_text(), proof, observations, Instructions(elf, rom))
    normal_count = None
    if normal_prefix:
        normal, normal_tail = prefix(normal_prefix)
        if len(normal) < len(observations) or observations != normal[:len(observations)]:
            raise ValueError('Debugger changes normal modeled timing/prefix history')
        normal_count = len(normal)
    out = directory/'main-regions.jsonl'
    with out.open('x') as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True)+'\n')
    paths = [directory/'prepared.json', directory/'run.json', directory/'stderr', directory/'features.jsonl',
             proof_path, Path(__file__).resolve(), out]
    if normal_prefix: paths.append(Path(normal_prefix).resolve())
    report = {'schema': 'iris.cpu_layout_debugger_readback_validation.v1', 'pass': True,
        'main_regions': len(rows), 'independent_numeric_counter_PC_checks': len(rows)*6,
        'actual_CSR_ELF_boundary_joins': len(rows)*2,
        'normal_timing_prefix_invariance_verified': bool(normal_prefix),
        'normal_prefix_records': normal_count, 'identical_complete_prefix_records': len(observations) if normal_prefix else None,
        'preserved_unterminated_final_prefix_bytes': tail,
        'host_seconds': receipt['host_seconds'], 'all_main_goldens_passed': True,
        'intentional_post_ROI_debugger_stop': True, 'normal_guest_exit_verified': False,
        'noop_controls_validated': False, 'whole_run_timing_or_speed_claim': False,
        'hardware_contacted': False, 'global_heldout_consumed': False,
        'input_sha256': {str(p): sha(p) for p in paths}}
    with (directory/'validation.json').open('x') as stream:
        json.dump(report, stream, indent=2); stream.write('\n')
    return report


def run(args):
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    argv = json.loads(args.argv.read_text())
    if any(a in ('-d', '--debug') or a.startswith('--debug-cmd=') for a in argv):
        raise ValueError('Input must describe a normal replay')
    argv = [a for a in argv if not a.startswith('--iris-timing-trace=')]
    elf = Path(argv[-1])
    # Resolve the actual object locations/sizes instead of assuming a build layout.
    process = subprocess.run([args.nm, '-S', '--defined-only', str(elf)], check=True, capture_output=True, text=True)
    objects = {}
    for line in process.stdout.splitlines():
        fields = line.split()
        if len(fields) == 4 and fields[3] in ('rows', 'noops', 'failed'):
            objects[fields[3]] = (int(fields[0], 16), int(fields[1], 16))
    if set(objects) != {'rows', 'noops', 'failed'} or {k: v[1] for k, v in objects.items()} != {'rows': 0x24000, 'noops': 0x240, 'failed': 4}:
        raise ValueError('CPU layout v2 object geometry required')
    row_base, noop_base, failed_base = [objects[k][0] for k in ('rows', 'noops', 'failed')]
    commands = ['rs 1000000', f'while mem {noop_base+24:x} 0']
    commands += [f'mem {p:x}' for p in range(row_base, row_base+0x24000, 8)]
    commands += [f'mem {failed_base:x}', 'pc 0', 'pc 1', 'pc 2', 'quit']
    (directory/'commands.txt').write_text('\n'.join(commands)+'\n')
    argv[1:1] = ['-d', '--debug-cmd='+str(directory/'commands.txt')]
    (directory/'argv.json').write_text(json.dumps(argv, indent=2)+'\n')
    (directory/'symbols.txt').write_text(process.stdout)
    paths = [Path(argv[0]), elf, args.argv.resolve(), args.proof.resolve(), Path(args.nm).resolve(),
             directory/'commands.txt', directory/'argv.json', directory/'symbols.txt', Path(__file__).resolve()]
    paths += [Path(a.split('=', 1)[1]) for a in argv if a.startswith(('--extlib=', '--iris-timing-fixture=', '--iris-bootrom=', '--dtb='))]
    prepared = {'schema': 'iris.cpu_layout_debugger_readback_experiment.v1', 'status': 'prepared',
        'argv': argv, 'hardware_contacted': False, 'final_heldout_consumed': False,
        'input_sha256': {str(p): sha(p) for p in paths}, 'full_guest_completion_expected': False}
    (directory/'prepared.json').write_text(json.dumps(prepared, indent=2)+'\n')
    receipt = dict(prepared, status='running')
    started = time.monotonic()
    with (directory/'stdout').open('w') as out, (directory/'stderr').open('w') as err:
        child = subprocess.Popen(argv, stdout=out, stderr=err, start_new_session=True,
            env=dict(os.environ, IRIS_EMPIRICAL_FEATURES=str(directory/'features.jsonl')))
        receipt['pid'] = child.pid
        (directory/'run.json').write_text(json.dumps(receipt, indent=2)+'\n')
        try:
            receipt['exit_status'] = child.wait(timeout=args.timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            os.killpg(child.pid, signal.SIGTERM)
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL); child.wait()
            receipt.update(exit_status=child.returncode, timed_out=True)
    receipt.update(status='debugger_stopped' if receipt['exit_status'] == 0 else 'failed',
        host_seconds=time.monotonic()-started, guest_full_completion=False,
        output_sha256={str(p): sha(p) for p in directory.iterdir() if p.name in ('stdout', 'stderr', 'features.jsonl')})
    (directory/'run.json').write_text(json.dumps(receipt, indent=2)+'\n')
    return analyze(directory, args.proof, args.normal_prefix)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--argv', type=Path)
    parser.add_argument('--proof', type=Path, required=True)
    parser.add_argument('--normal-prefix', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--analyze-existing', action='store_true')
    parser.add_argument('--nm', default='/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-nm')
    parser.add_argument('--timeout', type=float, default=180)
    args = parser.parse_args()
    if not args.analyze_existing and args.argv is None: parser.error('--argv is required for a fresh run')
    report = analyze(args.output, args.proof, args.normal_prefix) if args.analyze_existing else run(args)
    print(json.dumps({k: report[k] for k in ('pass', 'main_regions', 'host_seconds', 'normal_timing_prefix_invariance_verified')}))


if __name__ == '__main__':
    main()
