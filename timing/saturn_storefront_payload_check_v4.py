#!/usr/bin/env python3
"""Compare new source storefront slice to the frozen complete compute unit."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shlex
import signal
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb')as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--source-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);source=a.source_build.resolve();build=json.loads((source/'build.json').read_text());assert build['pass']is True
    full=ROOT/'build/saturn-timing-ownership-sdk-v7';fullbuild=json.loads((full/'build.json').read_text())
    headers=[x[2:]for x in fullbuild['argv'][0]if isinstance(x,str)and x.startswith('-I')]
    cpp=ROOT/'timing/saturn_storefront_payload_check_v4.cpp';helper=ROOT/'timing/saturn_timing_reset_writers.cpp';libs=[source/'model/VComputeStorefront__ALL.a',full/'sdk/libiris_saturn_timing.a']
    inputs=[Path(__file__).resolve(),cpp,helper,source/'build.json',source/'extraction.json',full/'build.json',*libs,Path('/usr/bin/g++').resolve()]
    initial={str(x):sha(x)for x in inputs};rows=[];start=time.monotonic()
    def run(name,argv,timeout=180):
        with(out/(name+'.stdout')).open('wb')as so,(out/(name+'.stderr')).open('wb')as se:
            environment=dict(os.environ);environment.pop("IRIS_STOREFRONT_PORT_TRACE",None)
            if name=="positive":environment["IRIS_STOREFRONT_PORT_TRACE"]=str(out/(name+".ports.bin"))
            proc=subprocess.Popen(list(map(str,argv)),stdout=so,stderr=se,start_new_session=True,env=environment)
            try:rc=proc.wait(timeout=timeout);timed=False
            except subprocess.TimeoutExpired:
                timed=True
                try:os.killpg(proc.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:rc=proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    try:os.killpg(proc.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    rc=proc.wait()
        row=dict(name=name,argv=list(map(str,argv)),exit_status=rc,timed_out=timed);rows.append(row);return rc==0 and not timed
    exe=out/'check';deps=out/'check.d';cmd=['/usr/bin/g++','-O2','-std=c++20','-MD','-MF',deps,'-I'+str(source/'model'),'-I'+str(ROOT/'timing'),*['-I'+x for x in headers],cpp,'-Wl,--start-group',*libs,'-Wl,--end-group','-pthread','-latomic','-o',exe]
    passed=run('compile',cmd);positive=None;controls=[]
    if passed:
        passed=run('positive',[exe]);positive=json.loads((out/'positive.stdout').read_text())if passed else None
    if passed:
        for flag in ['--wrong-half','--wrong-id']:
            ok=not run(flag[2:],[exe,flag],60)and not rows[-1]['timed_out']and('source returned load half-word payload'in(out/(flag[2:]+'.stderr')).read_text()or'actual load response tag/generation owner'in(out/(flag[2:]+'.stderr')).read_text());controls.append(dict(flag=flag,refused_as_expected=ok));passed &= ok
    compiled={}
    if deps.exists():
        for x in shlex.split(deps.read_text().replace('\\\n',' ').split(':',1)[1]):
            path=Path(x)
            if path.is_file():compiled[str(path)]=sha(path)
    unchanged=all(sha(x)==h for x,h in initial.items());passed &= unchanged
    report=dict(schema='iris.compute_Saturn_storefront_payload_check.v4',**{'pass':bool(passed)},positive=positive,negative_controls=controls,commands=rows,input_sha256=initial,compiled_dependency_sha256=compiled,inputs_unchanged=unchanged,
        host_seconds=time.monotonic()-start,source_RTL_changed=False,internal_state_injected=False,
        raw_port_scope='Actual source load/store sixteen-byte ports; random partial masks/data, lower/upper half, delayed out-of-order D and A backpressure. Independent owner/byte oracle, not VMU/CPU timing.',
        excludes=['upstream CPU timing','TL fault handling','System/NoC/backing integration','native or executed-ELF qualification'],
        hardware_contacted=False,protected_performance_labels_consumed=False,timing_certified=False)
    if exe.exists():report['executable_sha256']=sha(exe)
    report['output_sha256']={str(x):sha(x)for x in out.iterdir()if x.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(pass_=passed,report_sha256=sha(out/'report.json'),host_seconds=report['host_seconds'])))
    return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
