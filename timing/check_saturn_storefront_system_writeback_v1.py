#!/usr/bin/env python3
"""NEW finite Systemv6 physical fixture; no native CPU, hardware or timing fit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
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
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);start=time.monotonic();commands=[]
    system=ROOT/'build/shuttle-memory-system-native-v6';lp=ROOT/'build/serial-memory-context-sdk-v2/fased'
    build=json.loads((system/'build.json').read_text());assert build['exit_status']==0
    cpp=ROOT/'timing/saturn_storefront_system_writeback_v1.cpp'
    typed=ROOT/'build/saturn-storefront-typed-component-v1'
    includes=[str(typed/'sdk'),*build['required_include_directories'],str(lp/'sdk'),str(ROOT/'timing')]
    libs=[*build['required_static_libraries_in_link_order'],str(lp/'sdk/libiris_fased_service.a'),str(typed/'sdk/libiris_saturn_storefront.a')]
    bound=[Path(__file__).resolve(),cpp,ROOT/'timing/shuttle_memory_system_write_v1.cpp',ROOT/'timing/rvv_memory_fabric_boundary_v1.hpp',typed/'manifest.json',typed/'sdk/saturn_storefront_v1.hpp',ROOT/'timing/fased_backing_ledger_v1.hpp',ROOT/'timing/fased_backing_service_v2.hpp',system/'build.json',lp/'build.json',Path('/usr/bin/g++').resolve(),*map(Path,libs)]
    initial={str(x):sha(x)for x in bound}
    def run(name,argv,timeout=180):
        with(out/(name+'.stdout')).open('wb')as so,(out/(name+'.stderr')).open('wb')as se:
            proc=subprocess.Popen(argv,stdout=so,stderr=se,start_new_session=True)
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
        row=dict(name=name,argv=argv,exit_status=rc,timed_out=timed);commands.append(row);return row
    exe=out/'check';deps=out/'check.d'
    argv=['/usr/bin/g++','-O2','-std=c++20','-MD','-MF',str(deps),*['-I'+x for x in includes],'-isystem','/scratch/eygao/iris-cy/.conda-env/share/verilator/include',str(cpp),'-Wl,--start-group',*libs,'-Wl,--end-group','-pthread','-latomic','-o',str(exe)]
    compilation=run('compile',argv);passed=compilation['exit_status']==0 and not compilation['timed_out']
    controls=[]
    if passed:
        positive=run('positive',[str(exe)],180);passed=positive['exit_status']==0 and not positive['timed_out']
    if passed:
        seed17=run('seed17',[str(exe),'--seed17'],180);passed=seed17['exit_status']==0 and not seed17['timed_out']
    if passed:
        for flag,error in [('--wrong-write-data','actual vector-induced B-published backing byte golden'),('--wrong-D-source','IRIS_STOREFRONT_D_WITHOUT_OWNER'),('--undefined-backing','IRIS_FASED_BACKING_UNDEFINED_READ_BYTES')]:
            row=run(flag[2:],[str(exe),flag],180);row['required_error']=error;row['refused_as_expected']=row['exit_status']!=0 and not row['timed_out'] and error in (out/(flag[2:]+'.stderr')).read_text();controls.append(row);passed &= row['refused_as_expected']
    dependencies={}
    if deps.exists():
        for x in shlex.split(deps.read_text().replace('\\\n',' ').split(':',1)[1]):
            q=Path(x)
            if q.is_file():dependencies[str(q)]=sha(q)
    unchanged=all(sha(x)==h for x,h in initial.items());passed &= unchanged
    result=dict(schema='iris.compute_storefront_System_writeback_check.v1',**{'pass':bool(passed)},commands=commands,negative_controls=controls,input_sha256=initial,compiled_dependency_sha256=dependencies,inputs_unchanged=unchanged,
                host_seconds=time.monotonic()-start,scope='source typed vector storefront; external physical source prep and circularROB plus bounded client queue, no fullVMU; actual System/serial/FASED; declared backing bytes; finite quiescent checkpoint',
                normal_CPU_or_native_ELF_execution=False,full_FASED_host_token_bridge=False,source_LP_control_changed=False,clock_periods=dict(uncore=2,bringup_and_FASED=1,serial=10),
                caller_LP_parameters=dict(readLatency=30,writeLatency=30,readMaxReqs=16,writeMaxReqs=16),observed_parameters_admitted_as_default=False,
                hardware_contacted=False,network_contacted=False,protected_performance_labels_consumed=False,model_or_provider_modified=False,calibration_usable=False,timing_certified=False)
    if exe.exists():result['executable_sha256']=sha(exe)
    result['output_sha256']={str(q):sha(q)for q in out.iterdir()if q.is_file()}
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(pass_=passed,report_sha256=sha(out/'report.json'),host_seconds=result['host_seconds'])))
    return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
