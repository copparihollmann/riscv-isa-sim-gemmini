#!/usr/bin/env python3
"""Validate the frozen independent batch; timing results never become fitting input."""
import argparse,hashlib,json,os,re,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'firesim'));sys.path.insert(0,str(ROOT/'zephyr'))
from spike.run_functional import command,symbols
from batch_runner import parse_regions
from compiler_pipeline import producer_golden
from freeze_heldouts import output_hash
from uart_profiles import check_report

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def validate(text,manifest,cases,goldens):
    lines=text.splitlines()
    if any(x.startswith(('IRIS_FATAL','IRIS_HELDOUT_FATAL')) for x in lines):raise ValueError('Guest fatal')
    if [json.loads(x.split(' ',1)[1]) for x in lines if x.startswith('IRIS_HELDOUT_PHASE ')]!=manifest['phases']:
        # The external phase manifest also carries parent_case_id; wire keeps only actual controls.
        want=[{k:p[k] for k in ('phase','op','workers','kind')} for p in manifest['phases']]
        got=[json.loads(x.split(' ',1)[1]) for x in lines if x.startswith('IRIS_HELDOUT_PHASE ')]
        if got!=want:raise ValueError('Missing/reordered phase identity')
    rows=parse_regions(text,cases,manifest['ELF_sha256'],None,True,True)
    expected={(x['id'],h):x for x in cases for h in x['active_harts']}
    for r in rows:
        spec=expected[(r['case_id'],r['hart'])]
        if r.get('parent_case_id')!=spec['parent_case_id'] or r['cycles']<=0 or r['instret_delta']<=0:raise ValueError('Region provenance/counters')
        if r['region']=='pipeline_end_to_end':
            if r.get('scope')!='producer_entry_to_all_outputs_consumed' or r.get('role')!='pipeline.end_to_end' or r['hart']!=2:raise ValueError('Producer interval scope')
        else:
            if any(type(r.get(k))is not int or r[k]!=spec[k] for k in ('trial_id','dataset_id')):raise ValueError('Trial/dataset identity')
            twin='.twin.' in r['case_id'];workers=2 if '.h2.' in r['case_id'] else 1
            if r.get('role')!=('scalar.compute' if twin else 'vme.compute') or r.get('hart_mask')!=(1<<workers)-1:raise ValueError('Compute role/placement')
    outputs=[json.loads(x.split(' ',1)[1]) for x in lines if x.startswith('IRIS_HELDOUT_RESULT ')]
    if len(outputs)!=120:raise ValueError('Missing/duplicate full output')
    for index,result in enumerate(outputs):
        phase,job=divmod(index,15);g=goldens[phase//4][job%3]
        if manifest.get('compact_output'):
            expected_result={'phase':phase,'job':job,'encoding':'checked-word-hashes-v1','word_count':4096,
                'accumulator_checksum':output_hash(g['accumulator_u32']),'w8a8_checksum':output_hash(g['w8a8_f32_words']),
                'mismatching_int32_words':0,'mismatching_w8a8_words':0}
        else:
            expected_result={'phase':phase,'job':job,'accumulator_u32':g['accumulator_u32'],'w8a8_f32_words':g['w8a8_f32_words']}
        if result!=expected_result:raise ValueError('Independent full INT32/W8A8 golden mismatch')
        if not manifest.get('compact_output'):
            for key in ('accumulator_u32','w8a8_f32_words'):
                if any(type(x)is not int or not 0<=x<1<<32 for x in result[key]):raise ValueError('Output word types')
        elif any(type(result[k])is not int for k in ('word_count','accumulator_checksum','w8a8_checksum','mismatching_int32_words','mismatching_w8a8_words')):raise ValueError('Compact numeric field types')
    producers=[json.loads(x.split(' ',1)[1]) for x in lines if x.startswith('IRIS_HELDOUT_PRODUCER ')]
    if len(producers)!=8:raise ValueError('Missing producer')
    for p,phase in zip(producers,manifest['phases']):
        if p.get('phase')!=phase['phase'] or p.get('hart')!=2 or p.get('jobs')!=15 or p.get('vector_checksum')!=producer_golden(5) or p.get('vme_refused')is not True:raise ValueError('Hart2 producer/refusal')
        masks=p.get('overlap_masks')
        if not isinstance(masks,list) or len(masks)!=15 or any(type(m)is not int or not 0<=m<1<<phase['workers'] for m in masks) or not any(masks[:2]):raise ValueError('Missing CPU/compute overlap')
    done=[json.loads(x.split(' ',1)[1]) for x in lines if x.startswith('IRIS_BATCH_DONE ')]
    if done!=[{'failed':0,'cases':128,'regions':188,'trials':5}]:raise ValueError('Successful completion missing')
    elapsed=[json.loads(x.split(' ',1)[1])for x in lines if x.startswith('IRIS_HELDOUT_ELAPSED ')]
    if manifest.get('global_elapsed_source'):
        if len(elapsed)!=8:raise ValueError('Missing global CLINT intervals')
        for phase,r in enumerate(elapsed):
            if r.get('phase')!=phase or r.get('hart')!=2 or r.get('source')!='CLINT.mtime.MMIO' or r.get('scope')!='producer_entry_to_all_outputs_consumed':raise ValueError('Global elapsed attribution')
            if any(type(r.get(k))is not int for k in ('start_mtime','end_mtime','timebase_hz','core_cycles_per_tick')) or r['start_mtime']<0 or r['end_mtime']<=r['start_mtime'] or r['timebase_hz']!=500000 or r['core_cycles_per_tick']!=1000:raise ValueError('Global timer values/source ratio')
            r['mtime_delta']=r['end_mtime']-r['start_mtime'];r['quantized_elapsed_core_cycles']=r['mtime_delta']*1000
            r['tick_quantization_error_bound_core_cycles']=1000
    uart=check_report(lines,'ethan-firesim')
    return {'functional_checks_passed':True,'regions':rows,'phases':8,'physical_harts':[0,1,2],
        'full_output_elements':491520,'full_INT32_and_W8A8_match':True,'producer':producers,'uart_readback':uart,'global_elapsed_windows':elapsed,
        'numeric_validation':'Target embedded independent per-word INT32/W8A8 checks plus host independently expected whole-output hashes'if manifest.get('compact_output')else'Host comparison of every actual INT32 andW8A8 output word'}

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--batch',type=Path,required=True);p.add_argument('--expected-manifest-sha256',required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--binary',type=Path);p.add_argument('--uart',type=Path)
    p.add_argument('--seed',type=int,default=0);p.add_argument('--timeout',type=int,default=300);p.add_argument('--engine-arg',action='append',default=[])
    p.add_argument('--timing-kind',choices=['functional','experimental-empirical'],default='functional');p.add_argument('--console',type=Path)
    a=p.parse_args();batch=a.batch.resolve();mp=batch/'manifest.json'
    if sha(mp)!=a.expected_manifest_sha256:raise ValueError('Frozen workload manifest changed')
    manifest=json.loads(mp.read_text())
    if manifest.get('fitting_allowed')is not False or manifest.get('negative_skip_kernel'):raise ValueError('Independent positive heldout required')
    for original,item in manifest['inputs'].items():
        saved=batch/item['object']
        if not saved.is_file() or sha(saved)!=item['sha256']:raise ValueError('Frozen input changed '+original)
    cases=json.loads((batch/'cases.json').read_text());goldens=json.loads((batch/'golden.json').read_text())
    if sha(batch/'cases.json')!=manifest['cases_sha256'] or sha(batch/'golden.json')!=manifest['golden_sha256']:raise ValueError('Cases/goldens changed')
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    inputs={str(mp):sha(mp),str(Path(__file__)):sha(Path(__file__))};elapsed=None;cmd=[];code=None;timed=False
    if a.console:
        text=a.console.read_text();shutil.copyfile(a.console,out/'stdout');inputs[str(a.console.resolve())]=sha(a.console)
    else:
        if not a.binary or not a.uart:p.error('Execution requires --binary and --uart')
        binary=a.binary.resolve();uart=a.uart.resolve();elf=out/'guest.elf'
        item=manifest['inputs'][manifest['ELF']];shutil.copyfile(batch/item['object'],elf)
        if sha(elf)!=manifest['ELF_sha256']:raise ValueError('Frozen ELF changed')
        rom=ROOT/'board/evidence/bootrom.rv64.img';dtb=ROOT/'board/build/iris.dtb'
        cmd=command(binary,elf);cmd=['--extlib='+str(uart) if x.startswith('--extlib=') else x for x in cmd]
        cmd[-1:-1]=['--iris-bootrom='+str(rom),'--dtb='+str(dtb),'--iris-schedule-seed='+str(a.seed),*a.engine_arg]
        env=dict(os.environ,IRIS_FATAL_PCS=','.join(hex(v) for k,v in symbols(elf).items() if k in ('z_fatal_error','z_riscv_fatal_error','k_sys_fatal_error_handler','arch_system_halt','abort')))
        for file in [binary,uart,rom,dtb]:inputs[str(file)]=sha(file)
        if a.timing_kind=='functional' and a.engine_arg:raise ValueError('Explicit timing kind required for engine options')
        started=time.perf_counter()
        with(out/'stdout').open('wb')as stdout,(out/'stderr').open('wb')as stderr:
            try:r=subprocess.run(cmd,env=env,stdout=stdout,stderr=stderr,timeout=a.timeout);code=r.returncode
            except subprocess.TimeoutExpired:timed=True
        elapsed=time.perf_counter()-started;text=(out/'stdout').read_text(errors='replace')
    errors=[];proof={}
    try:proof=validate(text,manifest,cases,goldens)
    except (ValueError,KeyError,TypeError)as e:errors.append(str(e))
    if not a.console and(code!=0 or timed):errors.append('Execution failed or hit explicit wall bound')
    if any(sha(name)!=h for name,h in inputs.items()):errors.append('Inputs changed during execution')
    result={'schema':'iris.independent_heldout_batch_validation.v1','pass':not errors,'errors':errors,
        'argv':cmd,'exit_status':code,'timed_out':timed,'host_seconds':elapsed,'seed':a.seed,
        'timing_kind':a.timing_kind,'ELF_sha256':manifest['ELF_sha256'],'workload_manifest_sha256':sha(mp),
        'input_sha256':inputs,'fitting_allowed':False,'timing_certified':False,'hardware_contacted':False,**proof}
    result['artifact_sha256']={x.name:sha(x)for x in out.iterdir()if x.is_file()}
    (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'pass':result['pass'],'errors':errors,'regions':len(proof.get('regions',[])),'host_seconds':elapsed,'report_sha256':sha(out/'report.json')}))
    if errors:raise SystemExit(1)

if __name__=='__main__':main()
