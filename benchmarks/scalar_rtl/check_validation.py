#!/usr/bin/env python3
"""Check that forged scalar validation summaries cannot hide raw failures."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import tempfile

from verify_components import audit
from validate_components import sha


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--predictions', type=Path, required=True)
    parser.add_argument('--prediction-manifest-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    baseline = audit(args.run.resolve(), args.predictions.resolve(), args.prediction_manifest_sha256)
    checks = []
    with tempfile.TemporaryDirectory(prefix='iris-scalar-audit-') as temp:
        work = Path(temp) / 'run'
        shutil.copytree(args.run, work)
        original = json.loads((work / 'report.json').read_text())
        mutations = [('promote-calibration', lambda r: r.update(timing_calibrated=True)),
                     ('omit-case', lambda r: r['runs'].pop()),
                     ('fabricate-error', lambda r: r['comparisons'][0].update(signed_error_percent=1)),
                     ('invert-aggregate-claim', lambda r: r.update(all_regions_within_2_percent=not original['all_regions_within_2_percent']))]
        for name, mutate in mutations:
            report = copy.deepcopy(original)
            mutate(report)
            (work / 'report.json').write_text(json.dumps(report))
            try:
                audit(work, args.predictions.resolve(), args.prediction_manifest_sha256)
            except ValueError as exc:
                checks.append(dict(name=name, rejected=True, reason=str(exc)))
            else:
                raise ValueError('fabricated validation accepted: ' + name)
        (work / 'report.json').write_text(json.dumps(original))
        try:
            audit(work, args.predictions.resolve(), '0' * 64)
        except ValueError as exc:
            checks.append(dict(name='wrong-prediction-anchor', rejected=True, reason=str(exc)))
        else:
            raise ValueError('wrong prediction anchor accepted')
        # Repair every enclosing hash/receipt after changing the raw checksum.
        # The semantic decoder must still reject it, rather than relying only
        # on an unmodified hash in an outer JSON file.
        report = copy.deepcopy(original)
        run = report['runs'][0]
        directory = work / ('alu' + str(run['operations']))
        signature = directory / 'signature'
        saved_signature = signature.read_bytes()
        words = signature.read_text().splitlines()
        words[12] = f'{int(words[12], 16) ^ 1:016x}'
        signature.write_text('\n'.join(words) + '\n')
        run['artifact_sha256']['signature'] = sha(signature)
        (directory / 'results.json').write_text(json.dumps(run))
        for name in ('signature', 'results.json'):
            rel = str((directory / name).relative_to(work))
            report['artifact_sha256'][rel] = sha(directory / name)
        (work / 'report.json').write_text(json.dumps(report))
        try:
            audit(work, args.predictions.resolve(), args.prediction_manifest_sha256)
        except ValueError as exc:
            checks.append(dict(name='wrong-checksum-with-repaired-hashes', rejected=True, reason=str(exc)))
        else:
            raise ValueError('semantically invalid signature accepted')
        signature.write_bytes(saved_signature)
    result = dict(schema='iris.scalar_component_validation_adversarial_checks.v1', pass_=True,
                  baseline=baseline, rejections=checks, source_sha256=sha(Path(__file__)), hardware_contacted=False)
    (out / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    for path in (Path(__file__), Path(__file__).with_name('verify_components.py'), Path(__file__).with_name('validate_components.py')):
        shutil.copyfile(path, out / path.name)
    print(json.dumps(dict(status='passed', rejection_count=len(checks))))


if __name__ == '__main__':
    main()
