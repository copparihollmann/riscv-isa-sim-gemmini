#!/usr/bin/env python3
"""Check actual seeded transcripts and adversarial acceptance boundaries."""
import argparse
import hashlib
import json
from pathlib import Path

from validate import validate


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(build, gates, output):
    output.mkdir(parents=True, exist_ok=False)
    corpus = json.loads((build / 'corpus.json').read_text())
    inputs = {str(p.resolve()): digest(p) for p in [Path(__file__), Path(__file__).with_name('cases.py'),
              Path(__file__).with_name('validate.py'), build / 'build.json', build / 'corpus.json', build / 'probe.elf']}
    reports = []
    for gate in gates:
        receipt = json.loads((gate / 'report.json').read_text())
        if receipt.get('pass') is not True or receipt['elf_sha256'] != digest(build / 'probe.elf'):
            raise ValueError('Exact positive functional gate required')
        validate((gate / 'stdout').read_text(), corpus, build / 'probe.elf')
        inputs.update({str((gate / name).resolve()): digest(gate / name) for name in ('report.json', 'stdout', 'stderr')})
        reports.append({'seed': receipt['seed'], 'report_sha256': digest(gate / 'report.json')})
    if {r['seed'] for r in reports} != {0, 17} or len(reports) != 2:
        raise ValueError('Both independent functional seeds required')
    text = (gates[0] / 'stdout').read_text()
    lines = text.splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith('IRIS_REGION '))
    record = json.loads(lines[first].split(' ', 1)[1])
    negatives = []
    for field, bad in [('trap_cause', 0), ('illegal_delta', 0), ('pc_match', 0),
                       ('destination_bits', 0), ('fcsr', 0), ('checksum', 0),
                       ('hart', True), ('trial_id', 99), ('instruction', 0),
                       ('operand_bits', 42), ('trap_pc', 0x80000000), ('end_cycle', 0)]:
        changed = dict(record)
        changed[field] = bad
        modified = list(lines)
        modified[first] = 'IRIS_REGION ' + json.dumps(changed)
        negatives.append((field, '\n'.join(modified) + '\n'))
    negatives += [('missing_region', '\n'.join(lines[:first]+lines[first+1:])+'\n'),
                  ('duplicate_region', text+lines[first]+'\n'),
                  ('missing_begin', '\n'.join(line for line in lines if not line.startswith('IRIS_PROBE_BEGIN '))+'\n'),
                  ('fatal', text+'IRIS_FATAL {}\n')]
    results = []
    for name, modified in negatives:
        rejected = False
        try:
            validate(modified, corpus, build / 'probe.elf')
        except ValueError as error:
            rejected = True
            reason = str(error)
        if not rejected:
            raise ValueError('Bad transcript was accepted: ' + name)
        path = output / (name + '.stdout')
        path.write_text(modified)
        results.append({'case': name, 'rejected': True, 'reason': reason,
                        'transcript_sha256': digest(path)})
    report = {'schema': 'iris.scalar_bf16_acceptance.v1', 'pass': True,
              'elf_sha256': digest(build / 'probe.elf'), 'gates': reports,
              'negative_controls': results, 'input_sha256': inputs,
              'hardware_contacted': False, 'calibration_usable': False}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'pass': True, 'negative_controls': len(results)}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--gate', type=Path, action='append', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    run(a.build.resolve(), [g.resolve() for g in a.gate], a.output.resolve())
