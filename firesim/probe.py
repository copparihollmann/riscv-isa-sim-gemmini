#!/usr/bin/env python3
"""Inspect the FPGA host without launching, killing or flashing a simulation."""
import argparse
import datetime
import json
from pathlib import Path

from batch_runner import inspect_remote


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='sohumpc')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = {'schema_version': 1, 'host': args.host,
              'observed_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        report['remote'] = inspect_remote(args.host)
        report['status'] = 'reachable'
        report['smoke_passed'] = False
        result = 0
    except Exception as error:
        report.update(status='unverified', error=str(error), smoke_passed=False)
        result = 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(args.output)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
