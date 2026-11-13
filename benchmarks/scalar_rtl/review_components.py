#!/usr/bin/env python3
"""Publish an audited scalar component table without promoting its scope."""
import argparse
import json
from pathlib import Path
import shutil

from verify_components import audit
from validate_components import sha


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--predictions', type=Path, required=True)
    parser.add_argument('--prediction-manifest-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    checked = audit(args.run.resolve(), args.predictions.resolve(), args.prediction_manifest_sha256)
    report = json.loads((args.run / 'report.json').read_text())
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    exact = sum(r['signed_error_percent'] == 0 for r in report['comparisons'])
    text = ('# Frozen scalar component validation\n\n'
            f"{exact}/60 regions match exactly. The aggregate ±2% component check "
            + ('passes' if checked['all_regions_within_2_percent'] else 'fails') + '. '
            'All measured regions and failures appear below. Positive signed error means the model is slower.\n\n'
            'Predictions were frozen before these reference executions. The reference is the distinct saved '
            'standalone IrisConfig RTL, not an attested equivalent of Ethan\'s deployed FireSim image. '
            'Each row is an identical-ELF, guest-mcycle-delimited scalar region. '
            'This result does not certify frontend/cache/branch/vector/VME timing, whole workloads, '
            'end-to-end accuracy or the final Merlin/Miles holdouts.\n\n'
            '| ADDI count | Hart | Stream | RTL cycles | Predicted cycles | Signed error |\n'
            '| ---: | ---: | --- | ---: | ---: | ---: |\n')
    for row in sorted(report['comparisons'], key=lambda r: (r['operations'], r['hart'], r['kind'])):
        text += (f"| {row['operations']} | {row['hart']} | {row['kernel']} | {row['reference_cycles']} "
                 f"| {row['predicted_cycles']} | {row['signed_error_percent']:+.3f}% |\n")
    text += ('\nRaw signatures, source/ELF/binary inputs and runtime dependencies are retained in the named '
             'reference and prediction directories. The auditor checks archived inputs, exact compiled bodies, '
             'both raw signatures, every counter/checksum contract and the complete table. '
             'Neither a fitted offset nor relaxed expected values are used.\n')
    (out / 'summary.md').write_text(text)
    (out / 'audit.json').write_text(json.dumps(checked, indent=2) + '\n')
    for name in ('review_components.py', 'verify_components.py', 'validate_components.py'):
        shutil.copyfile(Path(__file__).with_name(name), out / name)
    manifest = dict(schema='iris.scalar_component_validation_review.v2',
                    reference_report=str((args.run / 'report.json').resolve()),
                    reference_report_sha256=sha(args.run / 'report.json'),
                    prediction_manifest=str((args.predictions / 'manifest.json').resolve()),
                    prediction_manifest_sha256=args.prediction_manifest_sha256,
                    all_regions_within_2_percent=checked['all_regions_within_2_percent'],
                    timing_calibrated=False, full_workload_held_out=False, deployed_image_equivalence=False,
                    hardware_contacted=False, artifact_sha256={p.name: sha(p) for p in out.iterdir() if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(dict(summary=str(out / 'summary.md'), manifest_sha256=sha(out / 'manifest.json'), exact_regions=exact)))


if __name__ == '__main__':
    main()
