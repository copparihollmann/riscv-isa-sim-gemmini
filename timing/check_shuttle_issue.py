#!/usr/bin/env python3
"""Compile/check the source-backed issue primitive and retain exact evidence."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    output=ROOT/'build/shuttle-issue';output.mkdir(parents=True,exist_ok=True)
    receipt=output/'results.json'
    receipt.unlink(missing_ok=True)
    compiler=Path(shutil.which('g++') or '')
    if not compiler.is_file():raise ValueError('g++ unavailable')
    verify=['python3',str(HERE/'generate_shuttle_issue.py'),'--verify-live']
    checked=subprocess.run(verify,text=True,capture_output=True)
    (output/'source-check.stdout').write_text(checked.stdout)
    (output/'source-check.stderr').write_text(checked.stderr)
    if checked.returncode:raise RuntimeError('source verification failed: '+checked.stderr)
    binary=output/'test_shuttle_issue'
    command=[str(compiler),'-std=c++17','-O2','-Wall','-Wextra','-Werror',
             str(HERE/'shuttle_issue.cpp'),str(HERE/'test_shuttle_issue.cpp'),'-o',str(binary)]
    built=subprocess.run(command,text=True,capture_output=True)
    (output/'build.log').write_text(built.stdout+built.stderr)
    if built.returncode:raise RuntimeError('issue primitive build failed: '+built.stderr)
    run=subprocess.run([str(binary)],text=True,capture_output=True)
    (output/'tests.stdout').write_text(run.stdout);(output/'tests.stderr').write_text(run.stderr)
    if run.returncode:raise RuntimeError('issue checks failed: '+run.stdout+run.stderr)
    match=re.search(r'^shuttle_issue_checks=(\d+) scalar_templates=(\d+) rtl_certified=false timing_calibrated=false$',run.stdout,re.M)
    if not match:raise RuntimeError('missing issue-check coverage receipt')
    sources=[HERE/name for name in ('shuttle_issue.cpp','shuttle_issue.hpp','shuttle_decode_rows.inc',
             'test_shuttle_issue.cpp','generate_shuttle_issue.py','check_shuttle_issue.py','run_shuttle_issue_tests.sh','SHUTTLE_ISSUE.md')]
    sources += sorted((HERE/'shuttle-evidence').glob('*'))
    sources += [HERE/'shuttle_issue_sources.json']
    record={'schema_version':1,'status':'passed_source_bound_issue_primitive',
            'checks':int(match[1]),'scalar_templates':int(match[2]),
            'source_verification_command':verify,'build_command':command,
            'compiler':str(compiler.resolve()),'compiler_sha256':sha(compiler),
            'compiler_version':subprocess.check_output([str(compiler),'--version'],text=True).splitlines()[0],
            'binary_sha256':sha(binary),'source_sha256':{str(path.relative_to(ROOT)):sha(path) for path in sources},
            'artifact_sha256':{path.name:sha(path) for path in output.iterdir() if path.is_file() and path!=receipt},
            'integrated_into_spike':False,'timing_calibrated':False,'rtl_certified':False,
            'scope':'RRD selection/control templates, supplied pipeline/front-end state, and structural EX/MEM/WB result stages; not a timing simulator'}
    receipt.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'status':record['status'],'checks':record['checks'],'scalar_templates':record['scalar_templates'],'receipt':str(receipt)}))


if __name__=='__main__':main()
