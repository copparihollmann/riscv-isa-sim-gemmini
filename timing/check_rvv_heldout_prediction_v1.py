#!/usr/bin/env python3
"""Actual replay admission and corruption controls; opens no hardware timings."""
import argparse
import copy
import json
from pathlib import Path
import tempfile

from replay_rvv_compute_heldout_asm_v1 import ROOT, decode, need, qualify_prefix, sha, verify_bindings


def main(args):
    run, build, out = [path.resolve() for path in (args.run, args.build, args.output)]
    out.mkdir(parents=True, exist_ok=False)
    report = json.loads((run / 'run.json').read_text())
    need(report['pass'] is True and report['diagnostic_only'] is True and not (run / 'freeze.json').exists(),
         'Own successful nonselected actual replay required')
    verify_bindings(report['input_sha256'])
    verify_bindings(report['output_sha256'])
    corpus = json.loads((build / 'corpus.json').read_text())
    elf, rom = build / 'guest.elf', ROOT / 'board/evidence/bootrom.rv64.img'
    text = (run / 'stderr').read_text()
    rows = decode(text, corpus, elf)
    identity = qualify_prefix(run / 'features.jsonl', rows, elf, rom)
    tests = []

    def refused(name, operation):
        try:
            operation()
        except (ValueError, KeyError, IndexError):
            tests.append(dict(name=name, rejected=True))
        else:
            raise ValueError('Corrupt evidence accepted: ' + name)

    lines = text.splitlines()
    for name, index, value in [('done_unfinished', 1, 2**64-1), ('count_short', 2, 1319),
                               ('wrong_record_index', 3, 3), ('hart2', 4, 2),
                               ('actual_checksum', 11, 0), ('program_expected_checksum', 12, 0),
                               ('mismatch', 13, 1), ('wrong_word_count', 14, 1),
                               ('wrong_vl', 15, 1), ('hart0_not_parked', len(lines)-3, 0)]:
        mutated = list(lines)
        mutated[index] = '0x' + format(value, '016x')
        refused(name, lambda mutated=mutated: decode('\n'.join(mutated) + '\n', corpus, elf))
    refused('missing_record_word', lambda: decode('\n'.join(lines[:-1]) + '\n', corpus, elf))
    refused('diagnostic_text_in_value_stream', lambda: decode(text + 'unexpected\n', corpus, elf))
    prefixes = [json.loads(line) for line in (run / 'features.jsonl').read_text().splitlines()]
    with tempfile.TemporaryDirectory(prefix='iris-heldout-controls-') as temporary:
        path = Path(temporary) / 'prefix.jsonl'
        for key, value in [('hart', 2), ('sequence', True), ('value', True), ('read_cycle', -1),
                           ('raw', 0x13), ('destination', 0), ('result_discarded', True)]:
            mutated = copy.deepcopy(prefixes)
            mutated[0][key] = value
            path.write_text(''.join(json.dumps(row) + '\n' for row in mutated))
            refused('prefix_' + key, lambda: qualify_prefix(path, copy.deepcopy(rows), elf, rom))
        path.write_text(''.join(json.dumps(row) + '\n' for row in prefixes[:-1]))
        refused('missing_counter_endpoint', lambda: qualify_prefix(path, copy.deepcopy(rows), elf, rom))
    inputs = [Path(__file__).resolve(), ROOT / 'timing/replay_rvv_compute_heldout_asm_v1.py',
              run / 'run.json', run / 'stderr', run / 'features.jsonl', build / 'corpus.json', elf, rom]
    result = dict(schema='iris.protected_prediction_admission_controls.v1', **{'pass': True},
                  actual_regions=1320, actual_independent_word_checks=184128,
                  actual_CSR_ELF_joins=3960, calibration_identity=identity,
                  negative_controls=tests, selected_prediction_created=False,
                  hardware_timing_labels_opened=False, timing_accuracy_evidence=False,
                  input_sha256={str(path): sha(path) for path in inputs})
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(pass_=True, negative_controls=len(tests), report_sha256=sha(out / 'report.json'))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    for name in ('run', 'build', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    main(parser.parse_args())
