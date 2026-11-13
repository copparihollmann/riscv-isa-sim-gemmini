#!/usr/bin/env python3
"""New finite functional backing/source-LP checks; no hardware/native changes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--kind',choices=['service'],required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sdk=ROOT/'build/serial-memory-context-sdk-v2/fased/sdk'
    cpp=ROOT/f'timing/fased_backing_{args.kind}_v2_check.cpp'
    source=[Path(__file__).resolve(),cpp,ROOT/'timing/fased_backing_ledger_v1.hpp',Path('/usr/bin/g++').resolve()]
    libs=[]
    if args.kind=='service':
        source += [ROOT/'timing/fased_backing_service_v2.hpp',sdk/'fased_service.hpp',sdk/'libiris_fased_service.a',sdk.parent/'build.json']
        libs=[str(sdk/'libiris_fased_service.a'),'-pthread','-latomic']
    inputs={str(p):sha(p)for p in source};start=time.monotonic();rows=[]
    def run(name,argv,timeout=180):
        with(out/(name+'.stdout')).open('wb')as so,(out/(name+'.stderr')).open('wb')as se:
            p=subprocess.Popen(argv,stdout=so,stderr=se,start_new_session=True)
            try:code=p.wait(timeout=timeout);timed=False
            except subprocess.TimeoutExpired:
                timed=True
                try:os.killpg(p.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:code=p.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    try:os.killpg(p.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    code=p.wait()
        row=dict(name=name,argv=argv,exit_status=code,timed_out=timed);rows.append(row);return row
    exe=out/'check'
    argv=['/usr/bin/g++','-O2','-std=c++20','-Wall','-Wextra','-Werror','-I'+str(sdk),'-I'+str(ROOT/'timing'),'-isystem','/scratch/eygao/iris-cy/.conda-env/share/verilator/include',str(cpp),*libs,'-o',str(exe)]
    compile_run=run('compile',argv)
    if compile_run['exit_status'] or compile_run['timed_out']:
        result=dict(schema='iris.FASED_backing_check.v2',**{'pass':False},stage='compile',commands=rows,input_sha256=inputs)
    else:
        positive=run('positive',[str(exe)])
        passed=positive['exit_status']==0 and not positive['timed_out']
        positive_result=json.loads((out/'positive.stdout').read_text())if passed else None
        controls=[]
        if passed and args.kind=='service':
            for option,message in [('--wrong-latency','source due/registered-egress latency phase'),('--wrong-id','actual R ID/data/last'),('--bad-wlast','AWLEN_WLAST_MISMATCH'),('--unknown-byte','UNKNOWN_STROBED_BYTE'),('--unmapped','UNMAPPED_BYTES'),('--unknown-address','UNKNOWN_REQUIRED_FIELD'),('--unprepared','STALE_COMMIT')]:
                row=run(option[2:],[str(exe),option],60)
                row['required_error']=message;row['refused_as_expected']=row['exit_status']!=0 and not row['timed_out']and message in(out/(option[2:]+'.stderr')).read_text();controls.append(row)
                passed &= row['refused_as_expected']
        unchanged=all(sha(Path(p))==h for p,h in inputs.items());passed &= unchanged
        result=dict(schema='iris.FASED_backing_check.v2',**{'pass':bool(passed)},kind=args.kind,positive=positive_result,negative_controls=controls,commands=rows,input_sha256=inputs,inputs_unchanged=unchanged,
                    executable_sha256=sha(exe),source_LP_control_changed=False,full_FASED_ingress_egress_host_token_bridge=False,
                    external_visibility='explicit disjoint-line/external-fence service only; intermediate host visibility not claimed',
                    hardware_or_network_contacted=False,protected_performance_labels_consumed=False,native_or_provider_changed=False,calibration_usable=False,timing_certified=False)
    result['host_seconds']=time.monotonic()-start
    result['output_sha256']={str(p):sha(p)for p in out.iterdir()if p.is_file()}
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(pass_=result['pass'],report_sha256=sha(out/'report.json'),host_seconds=result['host_seconds'])))
    return 0 if result['pass']else 1


if __name__=='__main__':
    raise SystemExit(main())
