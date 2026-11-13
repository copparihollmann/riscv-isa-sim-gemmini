"""Bounded exact functional execution on one low-priority CPU; no hardware launch."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

A = Path('/users/copparihollmann/iris-work/out/artifacts/probes/utilization-correction-v1/approved-operator-campaign-20261110-v1')


def main(packet):
    meta = json.loads((packet / 'build-receipt.json').read_text())
    if hashlib.sha256(Path(meta['elf']).read_bytes()).hexdigest() != meta['elf_sha256']:
        raise ValueError('ELF changed')
    previous = json.loads((A / 'vme-layout-factorial90-20261111-v1/packet/native-run.json').read_text())
    argv = previous['argv'].copy()
    argv[2], argv[-1] = '19', meta['elf']
    spike = next(Path(x) for x in argv if Path(x).name == 'spike')
    if hashlib.sha256(spike.read_bytes()).hexdigest() != previous['simulator_sha256']:
        raise ValueError('Simulator changed')
    owner = dict(pid=os.getpid(), proc_start=Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(')', 1)[1].split()[19],
                 CPU=19, nice=10, hardware_actions=False, script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (packet / 'native-owner.json').write_text(json.dumps(owner, indent=2) + '\n')
    started = time.monotonic()
    with (packet / 'native.stdout').open('xb') as stdout, (packet / 'native.stderr').open('xb') as stderr:
        try:
            rc = subprocess.run(argv, stdout=stdout, stderr=stderr, timeout=5400).returncode
            timed_out = False
        except subprocess.TimeoutExpired:
            rc, timed_out = None, True
    result = dict(argv=argv, returncode=rc, timed_out=timed_out, host_seconds=time.monotonic() - started,
                  ELF_sha256=meta['elf_sha256'], simulator_sha256=previous['simulator_sha256'],
                  stdout_sha256=hashlib.sha256((packet / 'native.stdout').read_bytes()).hexdigest(),
                  stderr_sha256=hashlib.sha256((packet / 'native.stderr').read_bytes()).hexdigest(),
                  hardware_actions=False, target_timing=False, native_pass=False)
    if rc == 0 and not timed_out:
        with (packet / 'qualification.stdout').open('xb') as stdout, (packet / 'qualification.stderr').open('xb') as stderr:
            gate = subprocess.run([sys.executable, '-B', str(Path(__file__).with_name('qualify_three_pass.py')),
                                   '--packet', str(packet), '--console', str(packet / 'native.stdout'),
                                   '--output', str(packet / 'native-admission'),
                                   '--counter-semantics', 'instruction_count_not_modeled_cycles'],
                                  stdout=stdout, stderr=stderr, timeout=600)
        result['native_pass'] = gate.returncode == 0
    (packet / 'native-run.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'argv'}), flush=True)
    return result['native_pass']


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--packet', type=Path, required=True)
    sys.exit(0 if main(p.parse_args().packet.resolve()) else 1)
