#!/usr/bin/env python3
"""Replay live counter/IPI/ordering semantics with the byte-matched pipeline pair."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--binary',type=Path,default=ROOT/'build/spike-shuttle-pipeline-next/spike')
    parser.add_argument('--uart',type=Path,default=ROOT/'build/spike-shuttle-pipeline-next/libsifive_uart.so')
    parser.add_argument('--output',type=Path,default=ROOT/'build/pipeline-rvc-live8')
    parser.add_argument('--counter-pipeline',action='store_true')
    parser.add_argument('--rocket-pipeline',action='store_true')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(exist_ok=True,parents=True)
    targets={ROOT/'timing/fixtures/three-hart-fast.fixture',ROOT/'timing/fixtures/three-hart-slow.fixture'}
    read=Path.read_text;run=subprocess.run;adapted=[]
    mode='pure-integer-rvc-counter-sequential-frontend' if args.counter_pipeline or args.rocket_pipeline else 'pure-integer-rvc-sequential-frontend'
    suffix='shuttle_pipeline '+mode+'\n'+('rocket_pipeline '+mode+'\n' if args.rocket_pipeline else '')+'pipeline_values private-pure-integer\n'
    def fixture(self,*a,**k):
        text=read(self,*a,**k)
        return text+suffix if self.resolve() in targets else text
    def matched_run(argv,*a,**k):
        if argv and argv[0]=='strip':
            if Path(argv[1]).resolve()!=out/'spike':raise RuntimeError('unexpected strip target')
            adapted.append('retain_exact_native_bytes')
            return subprocess.CompletedProcess(argv,0)
        if str(ROOT/'spike/devices/src/sifive_uart.cc') in argv:
            if argv[-2]!='-o' or Path(argv[-1]).resolve()!=out/'libsifive_uart.so':raise RuntimeError('unexpected UART compile target')
            shutil.copy2(args.uart.resolve(),out/'libsifive_uart.so');adapted.append('use_matched_finite_clocked_UART')
            return subprocess.CompletedProcess(argv,0)
        return run(argv,*a,**k)
    sys.argv=[str(ROOT/'build/combined-dev/live_check.py'),'--binary',str(args.binary.resolve()),'--output',str(out)]
    with patch.object(Path,'read_text',fixture),patch.object(subprocess,'run',matched_run):
        runpy.run_path(str(ROOT/'build/combined-dev/live_check.py'),run_name='__main__')
    record=json.loads((out/'results.json').read_text())
    if record['status']!='passed_integration_fixtures' or len(adapted)!=2 or sha(out/'spike')!=sha(args.binary) or sha(out/'libsifive_uart.so')!=sha(args.uart):
        raise RuntimeError('live replay omitted exact-byte adaptations')
    wrapper=dict(schema='iris.shuttle.live_regression.v1',binary_sha256=sha(args.binary),uart_sha256=sha(args.uart),
                 source_sha256=sha(__file__),runner_sha256=sha(ROOT/'build/combined-dev/live_check.py'),
                 live_results_sha256=sha(out/'results.json'),adaptations=adapted,
                 pipeline_mode=mode,rocket_pipeline=args.rocket_pipeline,calibrated=False,rtl_certified=False)
    (out/'pipeline-regression.json').write_text(json.dumps(wrapper,indent=2)+'\n')


if __name__=='__main__':main()
