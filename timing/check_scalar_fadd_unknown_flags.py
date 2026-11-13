#!/usr/bin/env python3
"""Actual zero-exception FADD must preserve uninitialized FFLAGS on all harts."""
import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    base = json.loads((ROOT / 'build/scalar-fadd-guest-dep-v2/build.json').read_text())
    crt = ROOT / 'benchmarks/start.S'
    text = crt.read_text()
    if text.count('  csrw fcsr, zero') != 1:
        raise ValueError('Expected exactly one explicit CRT FCSR initialization')
    private_crt = out / 'start-without-FCSR-init.S'
    private_crt.write_text(text.replace('  csrw fcsr, zero', '  .4byte 0x00000013'))
    guest = ROOT / 'timing/scalar_fadd_unknown_flags.c'
    pair = ROOT / 'build/scalar-fadd-phase-qualified-9b4932fe-v1'
    launch = json.loads((ROOT / 'build/scalar-fadd-directed-v3/dep/argv.json').read_text())
    rows = []
    for h in range(3):
        dest = out / ('hart' + str(h))
        dest.mkdir()
        elf = dest / 'guest.elf'
        argv = [str(private_crt) if x == str(crt) else
                str(guest) if x.endswith('/timing/scalar_fadd_guest.c') else
                '-DSCALAR_UNKNOWN_HART=' + str(h) if x.startswith('-DSCALAR_FADD_TEST=') else
                str(elf) if x.endswith('/scalar-fadd-guest-dep-v2/guest.elf') else x
                for x in base['argv']]
        compile_result = subprocess.run(argv, capture_output=True)
        (dest / 'build.stdout').write_bytes(compile_result.stdout)
        (dest / 'build.stderr').write_bytes(compile_result.stderr)
        if compile_result.returncode:
            raise ValueError('Private guest build failed')
        cmd = [str(pair / 'spike')]
        for x in launch[1:-1]:
            if x.startswith('--extlib='):
                x = '--extlib=' + str(pair / 'libsifive_uart.so')
            if x.startswith('--iris-timing-trace='):
                x = '--iris-timing-trace=' + str(dest / 'summary.json')
            cmd.append(x)
        cmd.append(str(elf))
        inputs = {str(q): sha(q) for q in (Path(__file__), guest, crt, private_crt, elf,
                  Path(argv[0]), pair / 'spike', pair / 'libsifive_uart.so',
                  ROOT / 'benchmarks/runtime.c', ROOT / 'benchmarks/runtime.h',
                  ROOT / 'benchmarks/uart_drain.h', ROOT / 'benchmarks/link.ld',
                  ROOT / 'board/evidence/bootrom.rv64.img', ROOT / 'board/build/iris.dtb',
                  ROOT / 'build/scalar-fadd-first-v1/fixture')}
        env = {k: v for k, v in os.environ.items() if not k.startswith('IRIS_EMPIRICAL_')}
        env['IRIS_EMPIRICAL_ASYNC_TRACE'] = str(dest / 'events.jsonl')
        begin = time.monotonic()
        run = subprocess.run(cmd, capture_output=True, timeout=60, env=env)
        (dest / 'stdout').write_bytes(run.stdout)
        (dest / 'stderr').write_bytes(run.stderr)
        err = run.stderr.decode()
        events = [json.loads(line) for line in (dest / 'events.jsonl').read_text().splitlines()]
        writes = [e for e in events if e['event'] == 'scalar_fadd_FPR_WRITE']
        passed = (run.returncode != 0 and 'IRIS_UNDEFINED_STATE' in err and
                  ('hart=' + str(h)) in err and 'unit=frm' in err and 'known=0x0' in err and
                  len(writes) == 1 and writes[0]['flags'] == 0 and
                  all(sha(q) == digest for q, digest in inputs.items()))
        row = dict(hart=h, pass_=passed, compile_argv=argv, argv=cmd,
                   input_sha256=inputs, exit_status=run.returncode,
                   host_seconds=time.monotonic() - begin,
                   actual_fadd_zero_exception_writes=writes,
                   unknown_flags_CSR_copies_allowed_until_required_dynamic_FRM=True,
                   expected_source_unknown_refusal=True, fake_hardware_trap_claimed=False,
                   stdout_sha256=sha(dest / 'stdout'), stderr_sha256=sha(dest / 'stderr'))
        row['pass'] = row.pop('pass_')
        (dest / 'report.json').write_text(json.dumps(row, indent=2) + '\n')
        rows.append(row)
    result = dict(schema='iris.scalar_fadd_actual_prior_unknown_flags.v1',
                  pass_=all(r['pass'] for r in rows), cases=rows,
                  immutable_native_changed=False, common_CRT_changed=False,
                  private_CRT_difference='one4-byte FCSR initialization replaced by4-byte NOP',
                  hardware_contacted=False, calibrated=False)
    result['pass'] = result.pop('pass_')
    (out / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(pass_=result['pass'], cases=3, report_sha256=sha(out / 'report.json'))))
    if not result['pass']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
