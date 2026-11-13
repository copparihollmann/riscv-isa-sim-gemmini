#!/usr/bin/env python3
"""Replay the existing live-memory corpus with the isolated pipeline enabled."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import timing.memory_live_check as memory


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--binary', type=Path, default=ROOT/'build/spike-shuttle-pipeline/spike')
    parser.add_argument('--uart', type=Path, default=ROOT/'build/spike-shuttle-pipeline/libsifive_uart.so')
    parser.add_argument('--output', type=Path, default=ROOT/'build/pipeline-memory-regression')
    parser.add_argument('--rvc', action='store_true')
    parser.add_argument('--counter-pipeline',action='store_true')
    parser.add_argument('--rocket-pipeline',action='store_true')
    args = parser.parse_args()
    original = memory.fixture
    mode='pure-integer-rvc-sequential-frontend' if args.rvc else 'pure-integer-sequential-frontend'
    if args.counter_pipeline or args.rocket_pipeline:mode='pure-integer-rvc-counter-sequential-frontend'
    suffix='shuttle_pipeline '+mode+'\n'+('rocket_pipeline '+mode+'\n' if args.rocket_pipeline else '')
    memory.fixture = lambda *a, **k: original(*a, **k)+suffix
    sys.argv = [str(ROOT/'timing/memory_live_check.py'), '--binary', str(args.binary.resolve()),
                '--uart', str(args.uart.resolve()), '--output', str(args.output.resolve())]
    result = memory.main()
    if result:
        raise RuntimeError('existing memory corpus failed with pipeline enabled')
    out = args.output.resolve()
    source = Path(__file__).resolve()
    (out/'pipeline-wrapper.py').write_bytes(source.read_bytes())
    receipt = json.loads((out/'results.json').read_text())
    if receipt['status'] != 'passed_address_routed_live_fixtures':
        raise RuntimeError('missing successful memory corpus receipt')
    report = dict(schema='iris.shuttle.memory_regression.v1', calibrated=False, rtl_certified=False,
                  wrapper_sha256=sha(source), memory_runner_sha256=sha(ROOT/'timing/memory_live_check.py'),
                  memory_results_sha256=sha(out/'results.json'),
                  binary_sha256=sha(args.binary), uart_sha256=sha(args.uart),
                  pipeline_mode=mode,
                  rocket_pipeline=args.rocket_pipeline,
                  pipeline_enabled_in_all_fixtures=all('shuttle_pipeline '+mode in p.read_text()
                                                     for p in out.glob('*.fixture')))
    if not report['pipeline_enabled_in_all_fixtures']:
        raise RuntimeError('a regression fixture omitted the pipeline selector')
    (out/'pipeline-regression.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':
    main()
