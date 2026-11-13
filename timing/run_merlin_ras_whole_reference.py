#!/usr/bin/env python3
"""Run one owned, bounded, unchanged-ELF whole-CPU RAS diagnostic."""
import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--elf', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--timeout', type=int, default=1800)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    reference = a.reference.resolve()
    elf = a.elf.resolve()
    cmd = [str(reference / 'simulator-preload'), '+permissive', '+verilator+seed+1',
           '+verilator+rand+reset+2', '+loadmem=1', '+max-cycles=3000000',
           '+init_write=0x2000004:0x1', '+init_write=0x2000008:0x1', '+permissive-off', str(elf)]
    files = [reference / 'simulator-preload', reference / 'build.json', elf, Path(__file__)]
    files += [q for q in elf.parent.iterdir() if q.name in
              ('guest.c', 'kernel.c', 'twin.build.log', 'encodings.json', 'golden.json')]
    inputs = {str(q): sha(q) for q in files}
    r = dict(schema='iris.merlin_RAS_actual_whole_CPU_bounded_run.v1', status='running',
             argv=cmd, input_sha256=inputs, timeout_seconds=a.timeout,
             source_FIR_sha256=json.loads((reference / 'build.json').read_text())['source_FIR_sha256'],
             target_RTL_modified=False, ELF_modified=False, internal_state_driven=False,
             architectural_state_initialization_shortcuts=False, hardware_contacted=False,
             full_four_state_definedness_available=False, source_image_association_verified=False,
             normal_guest_exit_claimed=False)
    (out / 'run.json').write_text(json.dumps(r, indent=2) + '\n')
    start = time.monotonic()
    with (out / 'stdout').open('wb') as so, (out / 'stderr').open('wb') as se:
        proc = subprocess.Popen(cmd, stdout=so, stderr=se)
        r['owned_child_pid'] = proc.pid
        (out / 'run.json').write_text(json.dumps(r, indent=2) + '\n')
        try:
            rc = proc.wait(timeout=a.timeout)
            timed_out = False
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.terminate()
            try:
                rc = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                rc = proc.wait(timeout=5)
    raw = (out / 'stderr').read_text(errors='replace')
    witnesses = [line for line in raw.splitlines() if line.startswith('WHOLE_UNWRITTEN_RAS_READ')]
    progress = [line for line in raw.splitlines() if line.startswith('RTL_PROGRESS')]
    r.update(status='actual_whole_CPU_unwritten_RAS_witness_validation_required' if witnesses
             else 'bounded_prefix_no_unwritten_read_observed',
             exit_status=rc, timed_out=timed_out, host_seconds=time.monotonic() - start,
             inputs_unchanged=all(sha(q) == d for q, d in inputs.items()),
             stdout_sha256=sha(out / 'stdout'), stderr_sha256=sha(out / 'stderr'),
             unwritten_RAS_witnesses=witnesses, last_progress=progress[-1] if progress else None,
             full_goal_complete=False, timing_certified=False)
    (out / 'run.json').write_text(json.dumps(r, indent=2) + '\n')
    print(json.dumps({k: r[k] for k in
                      ('status', 'host_seconds', 'timed_out', 'exit_status', 'last_progress')}))


if __name__ == '__main__':
    main()
