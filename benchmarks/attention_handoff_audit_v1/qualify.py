"""Validate handoff metadata, then delegate unchanged math/output to the parent reader."""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys

sys.path.insert(0, '/scratch/copparihollmann/merlin-gather-compat-integration-v1/src')
HERE = Path(__file__).resolve().parent
A = Path('/users/copparihollmann/iris-work/out/artifacts/probes/utilization-correction-v1/approved-operator-campaign-20261110-v1')
PARENT = A / 'attn/i8-only-next3-v1'
READER = A / 'attn/target-tools-i8-v2/postgate.py'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def handoffs(text, expected):
    rows, done, kept = [], [], []
    for line in text.splitlines():
        if line.startswith('ATTN_HANDOFF v1 '):
            values = list(map(int, line.split()[2:]))
            if len(values) != 12:
                raise ValueError('Malformed handoff frame')
            index, command, hart, status, registered, sequence, msb, msa, sb, rb, sa, ra = values
            if (index != len(rows) or command not in (1, 4) or hart != 0 or status
                    or registered not in (0, 1) or sb > sa or rb > ra
                    or (command == 1 and sequence <= 0) or (command == 4 and (sequence or not registered))):
                raise ValueError('Invalid command/context metadata')
            if rows and (sb < rows[-1][10] or rb < rows[-1][11]):
                raise ValueError('Non-monotone thread context counters')
            rows.append(values)
        elif line.startswith('ATTN_HANDOFF_DONE '):
            if line != f'ATTN_HANDOFF_DONE v1 {expected} 0':
                raise ValueError('Incomplete or overflowed handoff audit')
            done.append(line)
        elif line.startswith('ATTN_HANDOFF'):
            raise ValueError('Unknown handoff protocol')
        else:
            kept.append(line)
    if len(rows) != expected or len(done) != 1 or sum(r[1] == 4 for r in rows) != 1:
        raise ValueError('Missing/duplicated context frames or registration')
    enabled = False
    for r in rows:
        if r[1] == 4:
            enabled = True
        if bool(r[4]) != enabled:
            raise ValueError('Unexpected matrix registration lifetime')
    return rows, '\n'.join(kept) + '\n'


def qualify(packet, console, output, semantics):
    output.mkdir(parents=True, exist_ok=False)
    report = dict(pass_=False, performance_ineligible=True, physical_busy=None,
                  production_retest_still_required=True)
    try:
        build = json.loads((packet / 'build-receipt.json').read_text())
        if sha(build['ELF']) != build['ELF_sha256']:
            raise ValueError('ELF changed')
        for p, h in build['input_sha256'].items():
            if sha(p) != h:
                raise ValueError('Source changed: ' + p)
        raw = console.read_bytes()
        text = io.TextIOWrapper(io.BytesIO(raw), encoding='utf-8', newline=None).read()
        rows, normalized = handoffs(text, build['expected_handoffs'])
        normalized_path = output / 'attention-only.console'
        normalized_path.write_text(normalized)
        parent = json.loads((PARENT / 'build.json').read_text())
        parent.update(elf=build['ELF'], elf_sha256=build['ELF_sha256'])
        parent_path = output / 'bound-parent-build.json'
        parent_path.write_text(json.dumps(parent, indent=2) + '\n')
        spec = importlib.util.spec_from_file_location('attention_parent_reader', READER)
        reader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(reader)
        numerical = reader.check(normalized_path, output / 'numerical', semantics, parent_path)
        if not numerical['pass'] or numerical['trials'] != 42:
            raise ValueError('Full numerical parent gate failed: ' + str(numerical.get('error')))
        (output / 'handoffs.json').write_text(json.dumps(rows) + '\n')
        report.update(pass_=True, trials=42, handoff_records=len(rows),
                      matrix_saves=rows[-1][10], matrix_restores=rows[-1][11],
                      command_intervals_with_save=sum(r[10] > r[8] for r in rows),
                      command_intervals_with_restore=sum(r[11] > r[9] for r in rows),
                      ELF_sha256=build['ELF_sha256'], console_sha256=hashlib.sha256(raw).hexdigest(),
                      reader_sha256=sha(__file__), parent_reader_sha256=sha(READER),
                      numerical_report_sha256=sha(output / 'numerical/report.json'),
                      normalization='Only independently validated handoff frames removed; numerical values and original frame order unchanged.')
    except Exception as exc:
        report['error'] = repr(exc)
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)
    return report['pass_']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--packet', type=Path, required=True)
    parser.add_argument('--console', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--counter-semantics', choices=['target_mcycle_uncalibrated', 'instruction_count_not_modeled_cycles'], required=True)
    args = parser.parse_args()
    sys.exit(0 if qualify(args.packet, args.console, args.output, args.counter_semantics) else 1)
