#!/usr/bin/env python3
"""Prove Compute128 front permission precedes withheld owned memory responses."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from native_test_support import checked, sha

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--sdk', type=Path, required=True,
                        help='Directory containing frozen Saturn timing/ownership headers and library')
    parser.add_argument('--cxx', type=Path, default=shutil.which('g++'))
    parser.add_argument('--sdk-report', type=Path, help='Optional frozen SDK provenance receipt to hash')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.cxx is None:
        parser.error('Pass --cxx or add a C++20 compiler to PATH')
    sdk = args.sdk.resolve()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    compiler = args.cxx.resolve()
    source = HERE / 'compute128_vle8_withheld.cc'
    binary = out / 'withheld-load'
    library = sdk / 'libiris_saturn_live_bridge.a'
    files = [Path(__file__).resolve(), HERE / 'native_test_support.py', source, compiler,
             sdk / 'saturn_timing.hpp', sdk / 'saturn_timing_ownership.hpp', library]
    if args.sdk_report is not None:
        files.append(args.sdk_report.resolve())
    inputs = {str(p): sha(p) for p in files}
    argv = [str(compiler), '-O2', '-std=c++20', '-I' + str(sdk), str(source), str(library),
            '-pthread', '-latomic', '-o', str(binary)]
    checked(inputs)
    built = subprocess.run(argv, capture_output=True, timeout=120)
    (out / 'build.stdout').write_bytes(built.stdout)
    (out / 'build.stderr').write_bytes(built.stderr)
    results = []
    if built.returncode == 0:
        for vl in (1, 3, 16, 32):
            for seed in (1, 17):
                label = f'vl{vl}-seed{seed}'
                command = [str(binary), str(vl), str(seed)]
                run = subprocess.run(command, capture_output=True, timeout=30)
                stdout = out / (label + '.stdout')
                stderr = out / (label + '.stderr')
                stdout.write_bytes(run.stdout)
                stderr.write_bytes(run.stderr)
                rows = [json.loads(line.split(' ', 1)[1]) for line in run.stdout.decode().splitlines()
                        if line.startswith('RESULT ')]
                passed = run.returncode == 0 and len(rows) == 1 and rows[0]['pass']
                results.append(dict(argv=command, passed=passed, exit_status=run.returncode,
                                    result=rows[0] if len(rows) == 1 else None,
                                    stdout_sha256=sha(stdout), stderr_sha256=sha(stderr)))
                print(label, bool(passed), flush=True)
    checked(inputs)
    report = dict(schema='iris.Compute128_source_withheld_load_permission.v2',
                  passed=built.returncode == 0 and len(results) == 8 and all(r['passed'] for r in results),
                  results=results, compiler_argv=argv, compile_exit=built.returncode,
                  input_sha256=inputs, binary_sha256=sha(binary) if binary.exists() else None,
                  source_EX_to_PFC_permission_edges=2, memory_request_bytes=16,
                  physical_ATL_bus_bytes=32, source_rtl_or_library_modified=False,
                  internal_state_or_ready_injected=False, hardware_contacted=False,
                  timing_parameters_fitted=False, timing_accuracy_certified=False,
                  external_fixture='Identity M-mode TLB and ready ATL; D withheld64edges. Matching actual16B Get owners returned on32B bus. Authored service fixture, not latency calibration.',
                  knownness_scope='Explicit two-state source cut; numeric zeros only from observed physical reset-scrub writes. Check1024VRF bytes including tails and non-destination.')
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
