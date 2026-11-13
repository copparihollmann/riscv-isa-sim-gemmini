#!/usr/bin/env python3
"""Verify or execute smoke then broad fitting, analyzing both run outcomes."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import fcntl
import json
from pathlib import Path
import signal
import sys

from analyze_campaign import analyze
from batch_runner import digest, execute as execute_managed
from run_prepared import verify


def run(campaign_path, output, execute=False, allocation_id=None, host='sohumpc', timeout=1800):
    campaign = json.loads(campaign_path.read_text())
    if campaign.get('schema') != 'iris.managed_batched_campaign.v1' or campaign.get('order') != ['smoke', 'broad-fit']:
        raise ValueError('Reviewed smoke/broad campaign required')
    jobs = campaign['jobs']
    if [j['name'] for j in jobs] != campaign['order'] or len(jobs) != 2:
        raise ValueError('Invalid campaign job order')
    # Verify every job before the first lifecycle. The runner repeats all guards.
    for job in jobs:
        path = Path(job['job']).resolve()
        if digest(path / 'run.json') != job['run_receipt_sha256']:
            raise ValueError('Prepared campaign receipt changed: ' + job['name'])
        manifest = verify(path)
        if manifest['elf_sha256'] != job['elf_sha256']:
            raise ValueError('Campaign ELF changed')
    if not execute:
        return {'status': 'locally_verified_not_executed', 'hardware_contacted': False}
    if not allocation_id:
        raise ValueError('Actual operator allocation ID required')
    output.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'iris.managed_campaign_execution.v1', 'campaign_sha256': digest(campaign_path),
              'jobs': [], 'calibration_usable': False}
    for job in jobs:
        name = job['name']; path = Path(job['job']).resolve()
        row = {'name': name, 'entrypoint': 'verified batch_runner.execute',
               'host': host, 'allocation_id': allocation_id, 'timeout_seconds_per_phase': timeout}
        report['jobs'].append(row)
        try:
            with (output / (name + '.stdout')).open('x') as stdout, (output / (name + '.stderr')).open('x') as stderr, \
                    redirect_stdout(stdout), redirect_stderr(stderr):
                # Use the verified runner in this process, so cancellation enters
                # its owned cleanup rather than killing a supervising child.
                manifest = verify(path)
                manifest['execution_runner_sha256'] = digest(Path(__file__))
                with (path.parent / '.iris-firesim-manager.lock').open('a') as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    execute_managed(path / 'manager', path, host, allocation_id, timeout, manifest)
            row['runner_exit_status'] = 0
        except BaseException as error:
            row.update(runner_error=str(error), runner_exit_status=1,
                       interrupted=isinstance(error, KeyboardInterrupt))
        # execute_managed returns only after its cleanup/capture path. Failure
        # analysis retains capture/guest failure separately and never relaunches.
        analysis = analyze(path, output / (name + '-analysis'))
        row['analysis_report_sha256'] = digest(output / (name + '-analysis/report.json'))
        row['passed'] = row['runner_exit_status'] == 0 and analysis.get('managed_run_passed') is True
        report['status'] = 'continuing' if row['passed'] else 'stopped_after_failure'
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        if not row['passed']:
            return report
    report['status'] = 'completed_uncertified'
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    def interrupted(signum, frame):
        raise KeyboardInterrupt('Interrupted by signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGHUP, interrupted)
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('campaign', type=Path); parser.add_argument('--execute', action='store_true')
    parser.add_argument('--authorization-id','--allocation-id',dest='allocation_id'); parser.add_argument('--output', type=Path)
    parser.add_argument('--host', default='sohumpc'); parser.add_argument('--timeout', type=int, default=1800)
    args = parser.parse_args()
    if args.timeout <= 0 or args.execute and not args.output:
        parser.error('Positive timeout and fresh --output for execution required')
    report = run(args.campaign.resolve(), args.output.resolve() if args.output else None,
                 args.execute, args.allocation_id, args.host, args.timeout)
    print(json.dumps(report))
    return 1 if report.get('status') == 'stopped_after_failure' else 0


if __name__ == '__main__':
    raise SystemExit(main())
