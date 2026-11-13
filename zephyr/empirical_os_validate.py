#!/usr/bin/env python3
"""Actual three-hart OS gates for an explicitly experimental timing successor."""
import argparse,hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'zephyr'))
from spike.run_functional import command,symbols
from context_run import oracle as rvv_oracle
from vme_context_run import oracle as vme_oracle,producer_oracle
from uart_profiles import check_report

CASES=['scalar6','mixed9','rvv6','rvv6-vme-aware','vme4']
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def validate(name,text):
    lines=text.splitlines()
    if any('FATAL' in x for x in lines):raise ValueError('Guest fatal')
    if name in ('scalar6','mixed9'):
        rows=[json.loads(x.split(' ',1)[1]) for x in lines if x.startswith('IRIS_REGION ')]
        expected={}
        for h in range(3):
            expected[('zephyr.gemm16',h)]=len(range(h,16,3))*16*16
            expected[('zephyr.conv2d8',h)]=len(range(h,6,3))*6*9
            if name=='mixed9':expected[('zephyr.vme.yield',h)]=1024
        if len(rows)!=len(expected) or {(r['case_id'],r['hart'])for r in rows}!=set(expected):raise ValueError('Missing/duplicate measured hart/region')
        for r in rows:
            role='scalar.compute' if r['case_id']!='zephyr.vme.yield' else 'vme.compute' if r['hart']<2 else 'vector.copy'
            if r['checksum']!=expected[(r['case_id'],r['hart'])] or r.get('role')!=role or r.get('hart_mask')!=7:raise ValueError('Independent scalar/vector/matrix checksum or placement')
            if r['end_cycle']<=r['start_cycle'] or r['instret_delta']<=0:raise ValueError('Program-visible counter interval')
        if [json.loads(x.split(' ',1)[1])for x in lines if x.startswith('IRIS_BATCH_DONE ')]!=[{'failed':0}]:raise ValueError('Terminal marker')
        return {'regions':rows,'all_independent_checksums_match':True}
    if name.startswith('rvv6'):
        rows=[json.loads(x.split(' ',1)[1])for x in lines if x.startswith('IRIS_CONTEXT ')]
        if len(rows)!=6 or {x['thread']for x in rows}!=set(range(6)) or 'PASSED six competing RVV/IEEE contexts'not in lines:raise ValueError('Actual six-task terminal contract')
        for r in rows:
            if r['hart']!=r['thread']//2 or r['rounds']!=12 or r['timer_ticks']<=0 or r['checksum']!=rvv_oracle(r['thread']) or r['end_cycle']<=r['start_cycle']:raise ValueError('FP/RVV state, hart placement or timer preemption')
        return {'rows':rows,'all_independent_checksums_match':True,'actual_competing_contexts':6,'timer_preemption_all_three_harts':True}
    rows=[json.loads(x.split(' ',1)[1])for x in lines if x.startswith('IRIS_VME_CONTEXT ')]
    producer=[json.loads(x.split(' ',1)[1])for x in lines if x.startswith('IRIS_VME_PRODUCER ')]
    if len(rows)!=4 or {x['thread']for x in rows}!=set(range(4)) or 'PASSED explicit VME ownership' not in text:raise ValueError('Actual four VME task terminal contract')
    for r in rows:
        if r['hart_mask']!=3 or r['rounds']!=8 or r['timer_ticks']<=0 or r['saves']<=0 or r['restores']<=0 or r['checksum']!=vme_oracle(r['thread']):raise ValueError('VME context/migration/timer state')
    if producer!=[{'hart':2,'rounds':8,'checksum':producer_oracle(),'vme_refused':True}]:raise ValueError('Hart2 positive producer plus VME refusal')
    return {'rows':rows,'producer':producer,'all_independent_checksums_match':True,'automatic_unregistered_VME_context':False}

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--uart',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,default=0);p.add_argument('--timeout',type=int,default=120)
    p.add_argument('--engine-arg',action='append',default=[],help='Literal engine options; {graph} expands to this gate graph path')
    p.add_argument('--input',type=Path,action='append',default=[]);p.add_argument('--case',choices=CASES,action='append')
    p.add_argument('--timing-kind',choices=['functional','experimental-empirical'],default='experimental-empirical');a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);binary=a.binary.resolve();uart=a.uart.resolve()
    sourcefiles=[Path(__file__),ROOT/'zephyr/context_run.py',ROOT/'zephyr/vme_context_run.py',ROOT/'spike/run_functional.py',ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb',binary,uart,*a.input]
    inputhashes={str(x.resolve()):sha(x)for x in sourcefiles};runs=[]
    for name in a.case or CASES:
        directory=out/name;directory.mkdir();prior=ROOT/'build'/('combined-os-'+name)/'results.json'
        prior_data=json.loads(prior.read_text());elf=Path(prior_data['argv'][-1]);build=elf.parents[1]/'build.json';b=json.loads(build.read_text())
        if b['status']!='built' or sha(elf)!=b.get('elf_sha256',b.get('artifact_sha256',{}).get('zephyr/zephyr.elf')):raise ValueError('Actual successful source build required')
        for path,h in b['input_sha256'].items():
            if sha(ROOT/path)!=h:raise ValueError('Current build guard mismatch; explicitly rebuild '+path)
        for path in [elf,build,prior]:inputhashes[str(path)]=sha(path)
        cmd=command(binary,elf);cmd=['--extlib='+str(uart)if x.startswith('--extlib=')else x for x in cmd]
        cmd[-1:-1]=['--iris-bootrom='+str(ROOT/'board/evidence/bootrom.rv64.img'),'--dtb='+str(ROOT/'board/build/iris.dtb'),
            '--iris-schedule-seed='+str(a.seed),*[x.replace('{graph}',str(directory/'graph.json'))for x in a.engine_arg]]
        env=dict(os.environ,IRIS_FATAL_PCS=','.join(hex(v)for k,v in symbols(elf).items()if k in ('z_fatal_error','z_riscv_fatal_error','k_sys_fatal_error_handler','arch_system_halt','abort')))
        start=time.perf_counter();timed=False;code=None
        with(directory/'stdout').open('wb')as stdout,(directory/'stderr').open('wb')as stderr:
            try:r=subprocess.run(cmd,env=env,stdout=stdout,stderr=stderr,timeout=a.timeout);code=r.returncode
            except subprocess.TimeoutExpired:timed=True
        seconds=time.perf_counter()-start;text=(directory/'stdout').read_text(errors='replace');errors=[];proof={}
        try:
            proof=validate(name,text)
            if b.get('uart_profile') and name in ('scalar6','mixed9'):
                proof['uart_readback']=check_report(text.splitlines(),b['uart_profile']['name'])
            else:
                proof['uart_readback']=None
                proof['uart_readback_scope']='This legacy context app has no DIV report; successful console observed, no deployment-profile readback certification.'
        except (ValueError,TypeError,KeyError,RuntimeError)as e:errors.append(str(e))
        if code!=0 or timed:errors.append('Execution failure or explicit wall bound')
        if b'FATAL'in(directory/'stderr').read_bytes():errors.append('Native fatal')
        row={'name':name,'pass':not errors,'errors':errors,'argv':cmd,'exit_status':code,'timed_out':timed,'host_seconds':seconds,
            'ELF_sha256':sha(elf),'build_receipt_sha256':sha(build),'stdout_sha256':sha(directory/'stdout'),'stderr_sha256':sha(directory/'stderr'),**proof}
        (directory/'report.json').write_text(json.dumps(row,indent=2)+'\n');runs.append(row)
    if any(sha(path)!=h for path,h in inputhashes.items()):raise ValueError('Validation inputs changed')
    report={'schema':'iris.fast_model_actual_Zephyr_SMP_validation.v1','pass':all(x['pass']for x in runs),'runs':runs,'seed':a.seed,
        'timing_kind':a.timing_kind,'native_sha256':sha(binary),'UART_sha256':sha(uart),'input_sha256':inputhashes,
        'hardware_contacted':False,'timing_certified':False,'all_dtype_operations_certified':False,
        'known_hardware_divergences':['Exact original uninstrumented Zephyr/hart2 context ELF stalls after25 correct regions on tested FPGA; layout-sensitive controls do not establish a fix.',
            'Exact unfenced hart2 page-cross store probe repeats1174 correct regions then watchdog; model functional pass does not certify that path.'],
        'scope':'Actual three-hart OS functional gates and raw program-visible counters under selected experimental model; no timing goldens in these gates.'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':report['pass'],'gates':len(runs),'report_sha256':sha(out/'report.json')}))
    if not report['pass']:raise SystemExit(1)

if __name__=='__main__':main()
