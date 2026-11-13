#!/usr/bin/env python3
"""Freeze/independently verify the bounded saved-RTL memory frontier controls."""
import argparse,difflib,hashlib,json,re,shutil
from pathlib import Path
from certify import load_image

ROOT=Path(__file__).resolve().parents[2]
D=ROOT/'build/rtl-loader-diag'
FIELDS=['stage','actual','expected','cause','pc','tval','checks','done']

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def mailbox(path,count):
    lines=path.read_text().splitlines()
    if len(lines)!=28 or any(not re.fullmatch('[0-9a-f]{16}',x) for x in lines):raise ValueError('Invalid coherent signature')
    values=[int(x,16) for x in lines]
    if values[:4]!=[0x4952495350524f42,1,4,0]:raise ValueError('Failed/wrong memory probe mailbox')
    rows=[dict(zip(FIELDS,values[4+8*h:12+8*h]),hart=h) for h in range(3)]
    for row in rows:
        if row['done']!=1 or row['checks']!=(count*8 if row['hart']==2 else 0) or row['actual']!=row['expected']:raise ValueError('Incomplete/mismatching memory result')
    return rows

def state(path):
    lines=path.read_text().splitlines();sets={prefix:[json.loads(x.split(' ',1)[1]) for x in lines if x.startswith(prefix+' ')] for prefix in ['RTL_GPR','RTL_STATE','RTL_DEEP']}
    if not all(sets.values()) or len({len(x) for x in sets.values()})!=1:raise ValueError('Missing aligned state observations')
    samples=list(zip(sets['RTL_GPR'],sets['RTL_STATE'],sets['RTL_DEEP']))
    for row in samples:
        if len({x['tb'] for x in row})!=1:raise ValueError('Mismatching observation time')
    last=samples[-1]
    def key(row):
        control=dict(row[1]['fields'])
        # This TL buffer's data wire is irrelevant when its D.valid is low;
        # its raw value can follow unrelated arbitration while no beat fires.
        if not control['vector_unit__DOT___buffer_auto_in_d_valid']:
            control['vector_unit__DOT___buffer_auto_in_d_bits_data']=None
        return [{k:v for k,v in row[0].items() if k!='tb'},control,row[2]['fields']]
    start=len(samples)-1
    while start and key(samples[start-1])==key(last):start-=1
    f=last[2]['fields'];p='vector_unit__DOT__vmu__DOT__lifq__DOT__';q='vector_unit__DOT__'
    head=f[p+'deq_ptr_value']
    return {'first_stationary_tb':samples[start][0]['tb'],'last_tb':last[0]['tb'],'stationary_samples':len(samples)-start,'sample_period_tb_cycles':10000,'observed_scalar_fields':len(last[1]['fields'])+len(f),'stationary_comparison':'GPRs and sampled scalar fields, masking the TL buffer D.data only when its D.valid is0','last_stage_argument_a1':last[0]['x11'],'tl_reader_inflights':f[q+'tl_if__DOT__reader__DOT__inflights'],'tl_writer_inflights':f[q+'tl_if__DOT__writer__DOT__inflights'],'load_compactor_bytes':f[q+'vmu__DOT__lcu__DOT__count'],'lifq_head':head,'lifq_enqueue':f[p+'enq_ptr_value'],'lifq_head_has_response':bool(f[p+'valids_'+str(head)]),'load_rob_full':bool(f[p+'rob_full']),'load_rob_slots_valid':[f[p+'rob_valids_'+str(i)] for i in range(4)],'must_replay_tags':[i for i in range(32) if f[p+'must_replay_'+str(i)]],'vstart':f['core__DOT__csr__DOT__reg_vstart']}

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=ROOT/'build/rtl-memory-frontier-v1');p.add_argument('--verify',action='store_true');a=p.parse_args();out=a.output.resolve()
    if a.verify:
        j=json.loads((out/'report.json').read_text())
        for name,digest in j['artifact_sha256'].items():
            if sha(out/name)!=digest:raise ValueError('Frozen memory frontier input changed: '+name)
        for name,count in [('baseline8',8),('backoff9',9)]:
            if mailbox(out/j['controls'][name]['signature'],count)!=j['controls'][name]['harts']:raise ValueError('Signature decoder changed')
        if state(out/j['controls']['baseline9']['stderr'])!=j['controls']['baseline9']['observed_frontier']:raise ValueError('Raw state disagrees with frontier')
        print(json.dumps({'pass':True,'scope':'bounded traffic-sensitive saved-RTL observation','cause_identified':False,'matches_ethan_firesim_image':False}));return
    if out.exists():raise ValueError('Refuse to overwrite frozen frontier capsule')
    out.mkdir(parents=True);origins={}
    def save(path):
        path=Path(path).resolve()
        try:rel=path.relative_to(ROOT)
        except ValueError:rel=Path('external')/path.relative_to('/')
        target=out/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target);origins[str(rel)]={'path':str(path),'sha256':sha(path)};return str(rel)
    controls={}
    for label,name,count in [('baseline8','vector-memory-h2-8',8),('baseline9','vector-memory-h2-9',9),('backoff9','vector-memory-h2-9-backoff',9)]:
        run=D/(name+'.json');r=json.loads(run.read_text());elf=Path(r['argv'][-1]);binary=Path(r['argv'][0])
        if sha(elf)!=r['elf_sha256'] or sha(binary)!=r['binary_sha256']:raise ValueError('Executed identity changed')
        item={'receipt':save(run),'stderr':save(D/(name+'.stderr')),'stdout':save(D/(name+'.stdout')),'elf':save(elf),'binary':save(binary),'elf_sha256':r['elf_sha256'],'binary_sha256':r['binary_sha256'],'host_seconds':r['host_seconds'],'exit_status':r['exit_status'],'host_timed_out':r['timed_out'],'host_env_overrides':r.get('env_overrides',{})}
        if label=='baseline9':
            if r['exit_status']!=1 or r['timed_out'] or '(timeout)' not in (D/(name+'.stderr')).read_text():raise ValueError('Expected a bounded RTL cycle timeout')
            item['observed_frontier']=state(D/(name+'.stderr'))
            f=item['observed_frontier']
            if f['stationary_samples']<4 or f['tl_reader_inflights']!=17 or f['lifq_head_has_response'] or not f['load_rob_full'] or f['must_replay_tags']:raise ValueError('Expected stationary read-response frontier absent')
        else:
            if r['exit_status'] or r['timed_out']:raise ValueError('Positive memory control failed')
            item['signature']=save(D/(name+'.signature'));item['harts']=mailbox(D/(name+'.signature'),count)
        controls[label]=item
    if controls['baseline9']['elf_sha256']!=controls['backoff9']['elf_sha256']:raise ValueError('Backoff did not use exactly the same guest ELF')
    img8=load_image(D/'vector-memory-h2-8.elf');img9=load_image(D/'vector-memory-h2-9.elf');changes=[]
    if img8['entry']!=img9['entry'] or len(img8['segments'])!=len(img9['segments']):raise ValueError('Count controls changed memory layout')
    for x,y in zip(img8['segments'],img9['segments']):
        if {k:v for k,v in x.items() if k!='bytes'}!={k:v for k,v in y.items() if k!='bytes'}:raise ValueError('Count controls changed memory layout')
        aa,bb=bytes.fromhex(x['bytes']),bytes.fromhex(y['bytes']);changes += [{'address':hex(x['paddr']+i),'before':a,'after':b} for i,(a,b) in enumerate(zip(aa,bb)) if a!=b]
    names=['deep-state-build.json','poll-backoff-build.json','vector-memory-build.json','vector-memory-counted-build.json','state-diag-build.json','loader-build.json']
    for name in names:save(D/name)
    for rec in ['deep-state-build.json','loader-build.json']:
        for name,digest in json.loads((D/rec).read_text())['input_sha256'].items():
            if sha(name)!=digest:raise ValueError('Native diagnostic input changed: '+name)
            save(name)
    for rec in ['deep-state-build.json','poll-backoff-build.json']:
        for name in json.loads((D/rec).read_text())['link_argv']:
            if name.endswith('.o') or name.endswith('.a'):save(Path(name) if Path(name).is_absolute() else ROOT/'build/rtl-verilator/model'/name)
    for path in (ROOT/'board/rtl-loader').rglob('*'):
        if path.is_file() and '__pycache__' not in str(path):save(path)
    for name in ['VectorMemUnit_2.sv','LoadOrderBuffer_2.sv','LoadSegmenter_2.sv','Compactor_13.sv','TLInterface_4.sv','TLSplitInterface_2.sv','LoadSequencer_2.sv','SaturnRocketUnit.sv','VectorBackend_2.sv','CSRFile_2.sv']:
        save(ROOT/'build/rtl-verilator/gen-collateral'/name)
    for name in ['probe_runtime.c','probe_runtime.h']:save(ROOT/'build/definedness-dev/rtl-probes'/name)
    for path in [ROOT/'benchmarks/runtime.h',ROOT/'benchmarks/link.ld',ROOT/'build/rtl-verilator/manifest.json',ROOT/'hardware/manifest.json',ROOT/'hardware/memory-paths.json',ROOT/'build/rtl-reference-hpm-rdtime-final/reference.json']:save(path)
    diff=''.join(difflib.unified_diff((ROOT/'board/rtl-loader/SimTSI.cc').read_text().splitlines(True),(ROOT/'board/rtl-loader/poll_SimTSI.cc').read_text().splitlines(True),fromfile='baseline-SimTSI.cc',tofile='explicit-host-poll-backoff-SimTSI.cc'))
    (out/'host-adapter.diff').write_text(diff)
    j={'schema':'iris.saved_rtl_memory_frontier.v1','controls':controls,'count8_vs9_load_image_byte_changes':changes,'guest_fp_arithmetic_instructions':False,'guest_mask_and_data_memory_operations':True,'explicit_guest_type_checks':['VL256, VTYPE0xc3, VSTART0','VL1,VTYPE0x1d8,VSTART0'],'physical_harts':[0,1,2],'vector_work_harts':[2],'source_fir_sha256':'f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4','source_design':'chipyard.harness.TestHarness.IrisConfig','memory_lowering':'native FIRRTL memories; not original macrocompiler substitutions','preload':'explicit FESVR virtual native-RAM hooks and PT_LOAD BSS zero fill; versioned compact CRT','seed':1,'backoff_target_tsi_ticks':4096,'backoff_changes_host_coherent_memory_traffic':True,'host_adapter_diff':'host-adapter.diff','cause_identified':False,'global_deadlock_proven':False,'four_state_definedness_available':False,'unknown_reset_behavior_proven_irrelevant':False,'source_build_association_verified':False,'matches_ethan_firesim_image':False,'timing_calibrated':False,'hardware_contacted':False,'full_rtl_certified':False,'conclusion':'For this saved-RTL/native-memory/seed/preload harness, 8 baseline iterations complete; 9 stalls at a bounded read-response frontier; exactly the same 9-iteration guest completes with explicit host HTIF poll backoff. This does not identify the faulty gate or establish any deployed FPGA fault.','origins':origins,'artifact_sha256':{str(x.relative_to(out)):sha(x) for x in sorted(out.rglob('*')) if x.is_file()}}
    (out/'report.json').write_text(json.dumps(j,indent=2)+'\n');print(out/'report.json')

if __name__=='__main__':main()
