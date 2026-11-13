#!/usr/bin/env python3
"""Replay the real UART process corpus with compressed Shuttle timing enabled."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--binary',type=Path,default=ROOT/'build/spike-shuttle-pipeline-next/spike')
    parser.add_argument('--uart',type=Path,default=ROOT/'build/spike-shuttle-pipeline-next/libsifive_uart.so')
    parser.add_argument('--build-receipt',type=Path,default=ROOT/'build/spike-shuttle-pipeline-next/pipeline-build.json')
    parser.add_argument('--output',type=Path,default=ROOT/'build/pipeline-rvc-uart')
    parser.add_argument('--counter-pipeline',action='store_true')
    parser.add_argument('--rocket-pipeline',action='store_true')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(exist_ok=True,parents=True)
    target=ROOT/'timing/fixtures/three-hart-slow.fixture';original=Path.read_text
    mode='pure-integer-rvc-counter-sequential-frontend' if args.counter_pipeline or args.rocket_pipeline else 'pure-integer-rvc-sequential-frontend'
    suffix='shuttle_pipeline '+mode+'\n'+('rocket_pipeline '+mode+'\n' if args.rocket_pipeline else '')+'pipeline_values private-pure-integer\n'
    def fixture(self,*a,**k):
        text=original(self,*a,**k)
        return text+suffix if self.resolve()==target else text
    sys.argv=[str(ROOT/'board/uart-device/check.py'),'--binary',str(args.binary.resolve()),'--plugin',str(args.uart.resolve()),
              '--build-receipt',str(args.build_receipt.resolve()),'--output',str(out)]
    with patch.object(Path,'read_text',fixture):
        original_runner=ROOT/'board/uart-device/check.py'
        code=original(original_runner).replace("b'iris_device_clock_abi_v1'", "b'iris_device_clock_abi_v4'")
        if code==original(original_runner):raise RuntimeError('expected ABI1 mismatch assertion not found')
        (out/'uart-check-abi4.py').write_text(code)
        exec(compile(code,str(original_runner),'exec'),{'__file__':str(original_runner),'__name__':'__main__'})
    record=json.loads((out/'results.json').read_text())
    if record['status']!='passed_uart_process_cases':raise RuntimeError('UART process gate missing')
    for fixture_path in [out/'uart-live.fixture',out/'uart-source-clock.fixture']:
        if 'shuttle_pipeline '+mode not in fixture_path.read_text():
            raise RuntimeError('UART live fixture omitted the compressed pipeline')
    wrapper=dict(schema='iris.shuttle.uart_regression.v1',binary_sha256=sha(args.binary),uart_sha256=sha(args.uart),
                 source_sha256=sha(__file__),runner_sha256=sha(ROOT/'board/uart-device/check.py'),
                 uart_results_sha256=sha(out/'results.json'),pipeline_mode=mode,abi_mismatch_assertion='expect missingv4 symbol on oldv1 native',adapted_runner_sha256=sha(out/'uart-check-abi4.py'),
                 rocket_pipeline=args.rocket_pipeline,
                 calibrated=False,rtl_certified=False)
    (out/'pipeline-regression.json').write_text(json.dumps(wrapper,indent=2)+'\n')


if __name__=='__main__':main()
