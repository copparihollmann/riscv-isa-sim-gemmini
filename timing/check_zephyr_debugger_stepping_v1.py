#!/usr/bin/env python3
"""Same preserved first-use ELF: normal execution versus debugger step(1).

No timing accuracy or universal SMP parity is implied by this finite check.
"""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from replay_zephyr_h2_pow2_prediction_v1 import ROOT,sha,need,verify


def main():
    old=ROOT/'build/zephyr-firstuse-f5d-35a-OS-model-v1'
    receipt=json.loads((old/'run.json').read_text())
    need(receipt['pass'] is True and receipt['exit_status']==0 and receipt['timed_out'] is False,
         'Actual normal baseline')
    out=ROOT/'build/zephyr-firstuse-35a-OS-debugger-stepping-v1';out.mkdir(exist_ok=False)
    # Use the exact same launcher and arguments; add only debugger stepping.
    (out/'commands.txt').write_text('rs\nquit\n')
    argv=[receipt['argv'][0],'-d','--debug-cmd='+str(out/'commands.txt')]
    for token in receipt['argv'][1:]:
        argv.append('--iris-timing-trace='+str(out/'native-summary.json') if token.startswith('--iris-timing-trace=') else token)
    paths=[Path(__file__),old/'run.json',old/'stdout',old/'stderr',old/'features.jsonl',
           Path(argv[0]),Path(argv[-1]),out/'commands.txt',ROOT/'spike/empirical_launch_v2.py']
    for token in argv:
        if token.startswith(('--iris-timing-fixture=','--extlib=','--iris-bootrom=','--dtb=')):
            paths.append(Path(token.split('=',1)[1]))
    bindings={str(p):sha(p) for p in paths}
    for p,d in receipt['output_sha256'].items():
        if Path(p).name in ('stdout','stderr','features.jsonl'):verify({p:d})
    env={k:v for k,v in os.environ.items() if not k.startswith('IRIS_EMPIRICAL_') and k!='IRIS_FATAL_PCS'}
    env['IRIS_EMPIRICAL_FEATURES']=str(out/'features.jsonl')
    spec=importlib.util.spec_from_file_location('fatal_stepping',ROOT/'spike/empirical_launch_v2.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    env['IRIS_FATAL_PCS']=','.join(hex(v) for v in sorted(set(helper.fatal_addresses(Path(argv[-1])).values())))
    report=dict(schema='iris.Zephyr_debugger_stepping_control.v1',status='running',argv=argv,
                input_sha256=bindings,hardware_contacted=False,timing_labels_consumed=False,
                universal_SMP_parity_claim=False)
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    save();begin=time.monotonic()
    with (out/'stdout').open('w') as stdout,(out/'stderr').open('w') as stderr:
        p=subprocess.Popen(argv,stdout=stdout,stderr=stderr,env=env,start_new_session=True)
        report['owned_process_group']=p.pid;save()
        try:report['exit_status']=p.wait(timeout=180);report['timed_out']=False
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGTERM)
            try:p.wait(timeout=2)
            except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
            report.update(exit_status=p.returncode,timed_out=True)
    report['host_seconds']=time.monotonic()-begin
    verify(bindings)
    if report['exit_status']==0 and not report['timed_out']:
        before=[json.loads(x) for x in (old/'features.jsonl').read_text().splitlines()]
        after=[json.loads(x) for x in (out/'features.jsonl').read_text().splitlines()]
        report.update(status='completed_finite_schedule_comparison',**{'pass':True},
                      stdout_bytes_equal=(old/'stdout').read_bytes()==(out/'stdout').read_bytes(),
                      prefix_dictionary_equal=before==after,normal_prefixes=len(before),debugger_prefixes=len(after),
                      equal_prefix_dictionaries=sum(a==b for a,b in zip(before,after)),
                      debugger_has_extra_or_missing_prefixes=len(before)!=len(after))
    else:report.update(status='debugger_control_incomplete',**{'pass':False})
    report['output_sha256']={str(p):sha(p) for p in out.iterdir() if p.name in
                            ('stdout','stderr','features.jsonl','native-summary.json')}
    save();print(json.dumps({k:report.get(k) for k in ('pass','status','host_seconds','prefix_dictionary_equal')}))


if __name__=='__main__':main()
