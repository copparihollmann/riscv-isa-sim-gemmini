#!/usr/bin/env python3
"""Compiled-body, real omitted-kernel and parser controls for the frozen batch."""
import argparse,hashlib,json,os,re,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'zephyr'))
from heldout_batch_run import validate
from spike.run_functional import command,symbols
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--batch',type=Path,required=True);p.add_argument('--positive',type=Path,required=True)
    p.add_argument('--negative',type=Path,required=True);p.add_argument('--binary',type=Path,required=True);p.add_argument('--uart',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);batch=a.batch.resolve();negative=a.negative.resolve()
    manifest=json.loads((batch/'manifest.json').read_text());cases=json.loads((batch/'cases.json').read_text());goldens=json.loads((batch/'golden.json').read_text())
    positive=a.positive.resolve();text=positive.read_text();proof=validate(text,manifest,cases,goldens)
    tools=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin');objdump=tools/'riscv64-unknown-elf-objdump'
    elf=Path(manifest['ELF']);listing=subprocess.check_output([str(objdump),'-d',str(elf)],text=True);(out/'disassembly').write_text(listing)
    hits={};expected={}
    for op in ['gemm','conv2d']:
        for kind in ['shipped','twin']:
            stem='batch_'+op+'_'+kind
            d=json.loads((batch/'generated'/(stem+'-encodings.json')).read_text());expected[stem]=d['encodings'];hits[stem]={k:0 for k in ['SF_MM_INT','SF_VTZERO_T','SF_VTMV_V_T','SF_VTDISCARD']}
    function=''
    for line in listing.splitlines():
        m=re.match(r'^[0-9a-f]+ <([^>]+)>:',line)
        if m:function=m[1]
        fields=line.split()
        if len(fields)<2 or not re.fullmatch('[0-9a-f]{8}',fields[1]):continue
        word=int(fields[1],16)
        for stem,counts in hits.items():
            if not function.startswith(stem):continue
            for name in counts:
                enc=expected[stem][name]
                mask=int(enc['mask'],0) if isinstance(enc['mask'],str)else enc['mask']
                match=int(enc['match'],0)if isinstance(enc['match'],str)else enc['match']
                if word&mask==match:counts[name]+=1
    for stem,counts in hits.items():
        if (stem.endswith('shipped')and any(n==0 for n in counts.values()))or(stem.endswith('twin')and any(counts.values())):raise ValueError('Compiled emitted-kernel mode wrong '+stem+str(counts))
    lines=text.splitlines()
    def change(prefix,key,value):
        copy=list(lines)
        for i,line in enumerate(copy):
            if line.startswith(prefix):
                d=json.loads(line[len(prefix):]);d[key]=value(d[key]);copy[i]=prefix+json.dumps(d);return '\n'.join(copy)
        raise ValueError('Missing test target')
    damaged={
        'checksum':lambda:change('IRIS_REGION ','checksum',lambda x:x^1),
        'counter_reversed':lambda:change('IRIS_REGION ','end_cycle',lambda x:0),
        'no_retire':lambda:change('IRIS_REGION ','instret_delta',lambda x:0),
        'parent_identity':lambda:change('IRIS_REGION ','parent_case_id',lambda x:x+'.wrong'),
        'phase_identity':lambda:change('IRIS_HELDOUT_PHASE ','kind',lambda x:'wrong'),
        'missing_phase':lambda:'\n'.join(x for x in lines if not x.startswith('IRIS_HELDOUT_PHASE ')),
        'missing_end_to_end':lambda:'\n'.join(x for x in lines if not(x.startswith('IRIS_REGION ')and json.loads(x.split(' ',1)[1])['region']=='pipeline_end_to_end')),
        'missing_output':lambda:'\n'.join(x for x in lines if not x.startswith('IRIS_HELDOUT_RESULT ')),
        'INT32_word_or_hash':lambda:change('IRIS_HELDOUT_RESULT ','accumulator_checksum'if manifest.get('compact_output')else'accumulator_u32',(lambda x:x^1)if manifest.get('compact_output')else(lambda x:[x[0]^1,*x[1:]])),
        'W8A8_word_or_hash':lambda:change('IRIS_HELDOUT_RESULT ','w8a8_checksum'if manifest.get('compact_output')else'w8a8_f32_words',(lambda x:x^1)if manifest.get('compact_output')else(lambda x:[x[0]^1,*x[1:]])),
        'producer_VME_refusal':lambda:change('IRIS_HELDOUT_PRODUCER ','vme_refused',lambda x:False),
        'producer_hart':lambda:change('IRIS_HELDOUT_PRODUCER ','hart',lambda x:1),
        'completion':lambda:change('IRIS_BATCH_DONE ','failed',lambda x:1),
        'duplicate_region':lambda:text+'\n'+next(x for x in lines if x.startswith('IRIS_REGION ')),
    }
    if manifest.get('global_elapsed_source'):
        damaged['missing_global_elapsed']=lambda:'\n'.join(x for x in lines if not x.startswith('IRIS_HELDOUT_ELAPSED '))
        damaged['global_timer_ratio']=lambda:change('IRIS_HELDOUT_ELAPSED ','core_cycles_per_tick',lambda x:x+1)
    controls=[]
    for name,make in damaged.items():
        value=make();reason=None
        try:validate(value,manifest,cases,goldens)
        except (ValueError,KeyError,TypeError,RuntimeError)as error:reason=str(error)
        if reason is None:raise ValueError('Corruption accepted '+name)
        controls.append({'name':name,'rejected':True,'reason':reason,'corrupted_console_sha256':hashlib.sha256(value.encode()).hexdigest()})
    n=json.loads((negative/'manifest.json').read_text());nelf=Path(n['ELF'])
    if n.get('negative_skip_kernel')is not True or sha(nelf)!=n['ELF_sha256']:raise ValueError('Explicit real omitted-kernel ELF required')
    binary=a.binary.resolve();uart=a.uart.resolve();cmd=command(binary,nelf);cmd=['--extlib='+str(uart)if x.startswith('--extlib=')else x for x in cmd]
    cmd[-1:-1]=['--iris-bootrom='+str(ROOT/'board/evidence/bootrom.rv64.img'),'--dtb='+str(ROOT/'board/build/iris.dtb')]
    env=dict(os.environ,IRIS_FATAL_PCS=','.join(hex(v)for k,v in symbols(nelf).items()if k in ('z_fatal_error','z_riscv_fatal_error')))
    start=time.monotonic();r=subprocess.run(cmd,capture_output=True,env=env,timeout=30)
    (out/'negative.stdout').write_bytes(r.stdout);(out/'negative.stderr').write_bytes(r.stderr)
    if r.returncode==0 or b'IRIS_HELDOUT_FATAL'not in r.stdout:raise ValueError('Missing computation not caught')
    # Default fatal recognition correctly exits before queued UART necessarily
    # drains. A separate bounded diagnostic disables only that host PC hook,
    # allowing the target panic's full reason to emerge; never deploy this mode.
    diagnostic_timeout=False;diagnostic_code=None
    try:
        diagnostic=subprocess.run(cmd,capture_output=True,env=dict(env,IRIS_FATAL_PCS=''),timeout=2)
        diagnostic_stdout,diagnostic_stderr=diagnostic.stdout,diagnostic.stderr;diagnostic_code=diagnostic.returncode
    except subprocess.TimeoutExpired as e:
        diagnostic_timeout=True;diagnostic_stdout=e.stdout or b'';diagnostic_stderr=e.stderr or b''
    (out/'negative-diagnostic.stdout').write_bytes(diagnostic_stdout);(out/'negative-diagnostic.stderr').write_bytes(diagnostic_stderr)
    if b'"reason":12'not in diagnostic_stdout:raise ValueError('Independent per-word numerical failure reason not observed')
    sources=[Path(__file__),ROOT/'zephyr/heldout_batch_run.py',batch/'manifest.json',batch/'cases.json',batch/'golden.json',positive,negative/'manifest.json',nelf,elf,binary,uart,objdump]
    report={'schema':'iris.heldout_batch_independent_acceptance_controls.v1','pass':True,'compiled_shipped_twin_body_audit':hits,
        'parser_corruption_controls':controls,'real_omitted_kernel':{'rejected':True,'exit_status':r.returncode,'argv':cmd,'host_seconds':time.monotonic()-start,'reason':'Outside-ROI golden-XOR poison remains; actual target reason12 independent per-word check observed in separate bounded diagnostic; negative-only overlap assertion bypass prevents scheduling check hiding numeric failure',
            'default_fatal_hook_fails_fast':True,'diagnostic_only_fatal_PC_hook_disabled':True,'diagnostic_timed_out':diagnostic_timeout,'diagnostic_exit_status':diagnostic_code},
        'all_output_elements_compared':proof['full_output_elements'],'fitting_allowed':False,'timing_certified':False,'hardware_contacted':False,
        'input_sha256':{str(x):sha(x)for x in sources},'artifact_sha256':{x.name:sha(x)for x in out.iterdir()if x.is_file()}}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'parser_controls':len(controls),'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
