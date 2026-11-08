#!/usr/bin/env python3
"""Compile/run actual processor timing-wait and architectural catch-path tests."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

HERE=Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    build=args.build.resolve();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    receipt=json.loads((build/'build.json').read_text())
    configure=next(c['argv'] for c in receipt['commands'] if c['phase']=='configure')
    cxx=next(s.split('=',1)[1] for s in configure if s.startswith('CXX='))
    flags=shlex.split(next(s.split('=',1)[1] for s in configure if s.startswith('CXXFLAGS=')))
    libs=shlex.split(next(s.split('=',1)[1] for s in configure if s.startswith('LIBS=')))
    source=HERE.parent.parent
    cmd=[cxx,*flags,*[v for p in [build,source/'riscv',source/'fesvr',source/'softfloat',source/'disasm'] for v in ['-iquote',str(p)]],str(HERE/'step_outcomes.cc'),'-Wl,--export-dynamic','-Wl,--start-group',*[str(build/p) for p in ['libriscv.a','libdisasm.a','libsoftfloat.a','libfesvr.a','libfdt.a']],'-Wl,--end-group',*libs,'-ldl','-o',str(out/'step_outcomes')]
    compiled=subprocess.run(cmd,capture_output=True,timeout=120)
    (out/'compile.stdout').write_bytes(compiled.stdout);(out/'compile.stderr').write_bytes(compiled.stderr)
    result={'schema':'iris.processor_step_outcomes.v1','compile_argv':cmd,'compiler_sha256':sha(cxx),'test_source_sha256':sha(HERE/'step_outcomes.cc'),'test_driver_sha256':sha(__file__),'build_receipt_sha256':sha(build/'build.json'),'compile_exit':compiled.returncode,'hardware_contacted':False,'timing_accuracy_certified':False}
    if compiled.returncode==0:
        executed=subprocess.run([str(out/'step_outcomes')],capture_output=True,timeout=30)
        (out/'stdout').write_bytes(executed.stdout);(out/'stderr').write_bytes(executed.stderr)
        result.update(exit_status=executed.returncode,executable_sha256=sha(out/'step_outcomes'),passed=executed.returncode==0 and b'STEP_OUTCOME DONE 8' in executed.stdout)
    else:
        result['passed']=False
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return 0 if result['passed'] else 1

if __name__=='__main__':
    raise SystemExit(main())
