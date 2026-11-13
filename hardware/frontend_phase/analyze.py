#!/usr/bin/env python3
"""Independently audit unchanged512 execution, refill state and frontend stalls."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from iris_model.guest_regions import Instructions
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda:f.read(1048576),b''):h.update(data)
    return h.hexdigest()
def lfsr_next(state):return ((state<<1)&65535)|(((state>>10)^(state>>12)^(state>>13)^(state>>15))&1)


def audit(run,probe,reference,baseline):
    record=json.loads((run/'results.json').read_text());build=json.loads(probe.read_text());ref=json.loads((reference/'results.json').read_text())
    if record['status']!='passed_readonly_frontend_signature_requires_analysis' or not record['full448B_signature_matches_unobserved'] or sha(run/'signature')!=sha(reference/'signature'):
        raise ValueError('read-only observer changed coherent output')
    elf=Path(build['elf']);image=Instructions(elf);count=build['alu_operations'];bounds=[x['counter_pcs'] for x in build['compiled_body_validation']]
    if count!=512 or sha(elf)!=record['elf_sha256'] or record['elf_sha256']!=ref['elf_sha256']:raise ValueError('same512ELF proof identity mismatch')
    expected={}
    for kind,pc in enumerate(bounds):
        expected[kind]=list(range(pc[1]+4,pc[2],4))
        if len(expected[kind])!=count:raise ValueError('compiled512 body count differs')
        for address in expected[kind]:
            word=image.read(address);rd=(word>>7)&31
            if word&0x707f!=0x13 or word>>20!=1 or not rd or (word>>15)&31!=rd:raise ValueError('body is not pure self-increment ADDI')
    groups={};fills=[];inflight={};states={0:1,1:1};rows=0;counter_checks=0;projection_checks=0;anchors={};unqualified=0
    original=(baseline/'phase.jsonl').open() if baseline else None
    pending=json.loads(original.readline()) if original else None
    first_fields=None
    try:
        for line in (run/'phase.jsonl').open():
            row=json.loads(line);rows+=1;h=row['hart'];b=row['before'];a=row['after'];stamp=row['time_ps']
            if original:
                key=(stamp,h)
                while pending is not None and (pending['time_ps'],pending['hart'])<key:
                    if pending['time_ps']!=0:raise ValueError('actual-clock observer omitted a prior counter-sampled edge')
                    line=original.readline();pending=json.loads(line) if line else None
                if pending is not None and (pending['time_ps'],pending['hart'])==key:
                    old=pending
                    if {k:row[k] for k in old if k not in ('edge','before','after')}!={k:v for k,v in old.items() if k not in ('edge','before','after')} or any({k:row[phase][k] for k in old[phase]}!=old[phase] for phase in ('before','after')):
                        raise ValueError('read-only tag observer changed original frontend/counter fields')
                    projection_checks+=1;line=original.readline();pending=json.loads(line) if line else None
            if h not in anchors:
                # Verilator evaluates randomized initial state before reset.
                # Require the full observed reset image before assigning any
                # architectural meaning or checking the source LFSR sequence.
                reset_image=a.get('global_reset')==1 and a['mc']==a['ir']==0 and a['cache_replacement_state']==1 and not a['cache_refill_valid'] and a['fb_deq_ptr']==1 and not any(a['fb_valid'+str(i)] for i in range(7))
                if reset_image:anchors[h]=dict(time_ps=stamp,edge=row['edge'],MC=0,IR=0,LFSR=1,FB_valid_slots=0)
                unqualified+=1
                continue
            starting=not b['cache_refill_valid'] and bool(a['cache_refill_valid'])
            if starting:
                if h in inflight or not b['cache_refill_request']:raise ValueError('overlapping/unrequested Icache refill')
                if b['cache_replacement_state']!=states[h] or a['cache_replacement_state']!=lfsr_next(states[h]):raise ValueError('source LFSR step mismatch')
                states[h]=lfsr_next(states[h]);way=states[h]&1
                if way!=a['cache_replacement_way']:raise ValueError('source victim differs from actual LFSR output')
                address=a['cache_refill_address'];oldtag=b['cache_index_tag'+str(way)];oldvalid=b['cache_index_valid'+str(way)]
                inflight[h]=dict(hart=h,start=stamp,address=address,line=address&~63,index=(address>>6)&63,way=way,
                                 victim_valid=bool(oldvalid),victim_tag=oldtag if oldvalid else None,
                                 evicted_line=((oldtag<<12)|(address&0xfc0)) if oldvalid else None,
                                 lfsr_before=b['cache_replacement_state'],lfsr_after=states[h],beats=0,
                                 episode_kind=row['kind'],invocation=row['invocation'])
            if b['cache_replacement_state']!=a['cache_replacement_state'] and not starting:raise ValueError('unexplained replacement-state change')
            if h in inflight and b['cache_refill_beat']:inflight[h]['beats']+=1
            if b['cache_refill_done']:
                if h not in inflight:raise ValueError('refill completed without captured request')
                fill=inflight.pop(h);way=fill['way'];other=1-way
                if fill['beats']!=8 or not b['cache_refill_beat'] or a['cache_refill_valid']:raise ValueError('source64B/eight-beat refill did not complete')
                if a['cache_index_tag'+str(way)]!=fill['address']>>12 or not a['cache_index_valid'+str(way)]:raise ValueError('refill did not install actual physical tag')
                if a['cache_index_tag'+str(other)]!=b['cache_index_tag'+str(other)] or a['cache_index_valid'+str(other)]!=b['cache_index_valid'+str(other)]:raise ValueError('unselected cache way changed')
                fill.update(end=stamp,cycles=(stamp-fill['start'])//2000);fills.append(fill)
            kind=row['kind']
            if kind<0:continue
            key=(h,kind,row['invocation']);group=groups.setdefault(key,dict(hart=h,kind=kind,invocation=row['invocation'],first=stamp,last=None,rows=0,
                        opening_mc=b['mc'],closing_mc=None,counts=Counter(),body_retired=[],body_issued=[],counter_reads={}))
            if group['last'] is not None and stamp-group['last']!=2000:raise ValueError('missing source500MHz core edge in selected episode')
            group['last']=stamp;group['rows']+=1
            for name in ('ex_stall','deq0_valid','deq1_valid','rrd0_stall','rrd1_stall','cache_s2_miss','cache_refill_valid','cache_refill_beat','fetch2_tlb_miss','fetch2_redirect','flush_rrd'):
                group['counts'][name]+=b[name]
            group['counts']['frontend_empty']+=not b['deq0_valid']
            group['counts']['frontend_empty_during_refill']+=not b['deq0_valid'] and bool(b['cache_refill_valid'])
            group['counts']['frontend_empty_without_refill']+=not b['deq0_valid'] and not b['cache_refill_valid']
            group['counts']['architectural_retirements']+=b['retire0']+b['retire1']
            pointer=b['fb_deq_ptr']
            if pointer<=0 or pointer&(pointer-1) or pointer>=128:raise ValueError('fetch-buffer pointer is not onehot7')
            head=pointer.bit_length()-1
            for lane in (0,1):
                valid=b['deq'+str(lane)+'_valid'];slot=(head+lane)%7
                if valid!=b['fb_valid'+str(slot)]:raise ValueError('SV-derived dequeue-valid mapping changed')
                pc=b['fb_pc'+str(slot)]
                if valid and not b['rrd'+str(lane)+'_stall'] and bounds[kind][1]<pc<bounds[kind][2]:group['body_issued'].append(pc)
                if b['retire'+str(lane)]:
                    pc=b['com'+str(lane)+'_pc'];word=b['com'+str(lane)+'_raw']
                    if bounds[kind][1]<pc<bounds[kind][2]:
                        if word!=image.read(pc):raise ValueError('retired body instruction differs from actual ELF')
                        group['body_retired'].append(pc)
                    if lane==0 and pc in bounds[kind]:group['counter_reads'][str(bounds[kind].index(pc))]=dict(pc=pc,mc=b['mc'],ir=b['ir'],time_ps=stamp)
            csr=b['com0_raw']>>20;source_write=b['com0_valid'] and b['retire0'] and b['com0_raw']&127==0x73 and (b['com0_raw']>>15)&31==0 and (b['com0_raw']>>12)&7 in (2,3,6,7)
            expected_mc=b['mc']+int(not(source_write and csr==0xb00));expected_ir=b['ir']+(0 if source_write and csr==0xb02 else b['retire0']+b['retire1'])
            if (a['mc'],a['ir'])!=(expected_mc,expected_ir):raise ValueError('source counter edge rule disagrees with actual CPU')
            counter_checks+=2
            if row['closing']>=0:group['closing_mc']=b['mc']
        if pending is not None:raise ValueError('actual-clock observer omitted trailing original counter-sampled rows')
    finally:
        if original:original.close()
    if set(anchors)!={0,1} or len(groups)!=8:raise ValueError('source reset/warm/measured episode coverage changed')
    summary=[]
    for key,g in sorted(groups.items()):
        kind=g['kind']
        if g['body_retired']!=expected[kind] or g['body_issued']!=expected[kind]:raise ValueError('actual RRD/COM did not issue/retire each512body exactly once')
        if set(g['counter_reads'])!={'0','1','2','3'}:raise ValueError('actual source counter read coverage missing')
        span=(g['last']-g['first'])//2000;visible=g['closing_mc']-g['opening_mc']
        if visible!=span-1:raise ValueError('visible cycle interval differs from source pre-edge pause')
        if g['invocation']==2:
            row=next(r for r in ref['reference_rows'] if r['hart']==g['hart'] and r['kind']==kind)
            if visible!=row['cycles'] or g['opening_mc']!=row['start_cycle'] or g['closing_mc']!=row['end_cycle'] or g['counter_reads']['2']['ir']-g['counter_reads']['1']['ir']!=row['instret_delta']:
                raise ValueError('measured source reads differ from unchanged coherent signature')
        overlaps=[f for f in fills if f['hart']==g['hart'] and f['start']<=g['last'] and f['end']>=g['first']]
        summary.append(dict(hart=g['hart'],kind=kind,invocation=g['invocation'],physical_edges=span,visible_cycles=visible,
                            first_time_ps=g['first'],last_time_ps=g['last'],decoded_body_operations=count,body_issued=count,body_retired=count,
                            counts=dict(g['counts']),counter_reads=g['counter_reads'],refills=overlaps))
    histories=[]
    for fill in fills:
        if fill['episode_kind']<0 or fill['invocation']!=2:continue
        old=[f for f in fills if f['hart']==fill['hart'] and f['line']==fill['line'] and f['end']<fill['start']]
        if not old:raise ValueError('measured miss lacks retained warmup history')
        prior=old[-1];evictions=[f for f in fills if f['hart']==fill['hart'] and f['evicted_line']==fill['line'] and prior['end']<f['start']<fill['start']]
        if not evictions:raise ValueError('measured warm-line miss has no directly observed eviction')
        histories.append(dict(hart=fill['hart'],line=fill['line'],measured_refill=fill,warm_refill=prior,intervening_evictions=evictions))
    return dict(rows=rows,projection_checks=projection_checks,counter_transition_checks=counter_checks,reset_state_anchors=anchors,unqualified_pre_reset_rows=unqualified,completed_refills=len(fills),
                incomplete_refills=len(inflight),episodes=summary,measured_miss_eviction_histories=histories,fills=fills)


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--run',type=Path,default=ROOT/'build/frontend-phase-clock512-v3')
    p.add_argument('--baseline',type=Path,default=ROOT/'build/frontend-phase-cache512-v2');p.add_argument('--probe',type=Path,default=ROOT/'build/scalar-component-validation-plan-v2/alu512/build.json')
    p.add_argument('--reference',type=Path,default=ROOT/'build/scalar-component-validation-e060-v1/alu512');p.add_argument('--output',type=Path,default=ROOT/'build/frontend-phase-proof-512-v1')
    p.add_argument('--verify',action='store_true');a=p.parse_args();out=a.output.resolve()
    if a.verify:
        d=json.loads((out/'report.json').read_text())
        for name,h in d['artifact_sha256'].items():
            if sha(out/name)!=h:raise ValueError('closed observer artifact changed: '+name)
        for name,h in d['input_sha256'].items():
            if sha(out/'inputs'/h)!=h:raise ValueError('closed observer input changed: '+name)
        print(json.dumps(dict(status='verified_closed_frontend_proof',inputs=len(d['input_sha256']),rows=d['analysis']['rows'])));return
    out.mkdir(exist_ok=False,parents=True);(out/'inputs').mkdir();analysis=audit(a.run,a.probe,a.reference,a.baseline)
    inputs={str(Path(__file__).resolve()):sha(__file__),str(a.probe.resolve()):sha(a.probe),str(a.reference.resolve()/'results.json'):sha(a.reference/'results.json')}
    for source in (a.run,a.baseline):
        r=json.loads((source/'results.json').read_text());inputs.update(r['input_sha256']);inputs[str((source/'results.json').resolve())]=sha(source/'results.json')
    inputs[str(ROOT/'iris_model/guest_regions.py')]=sha(ROOT/'iris_model/guest_regions.py')
    for path,digest in inputs.items():
        target=out/'inputs'/digest
        if target.exists():continue
        candidates=[Path(path),a.run/'inputs'/digest,a.baseline/'inputs'/digest]
        match=next((p for p in candidates if p.is_file() and sha(p)==digest),None)
        if match is None:raise ValueError('source input changed or unavailable: '+path)
        shutil.copy2(match,target)
    for name,source in [('observer',a.run),('original-observer',a.baseline),('unobserved',a.reference)]:
        dest=out/name;dest.mkdir()
        for path in source.iterdir():
            if not path.is_file():continue
            if path.stat().st_size>1048576:
                with path.open('rb') as src,gzip.open(dest/(path.name+'.gz'),'wb',compresslevel=1) as target:shutil.copyfileobj(src,target,1048576)
            else:shutil.copy2(path,dest/path.name)
    report=dict(schema='iris.frontend_observer.proof.v1',status='passed_readonly_frontend_cache_diagnosis',analysis=analysis,input_sha256=inputs,
                source_geometry=dict(sets=64,ways=2,line_bytes=64,physical_tag_bits=23,replacement='16bitFibonacciLFSR; increment atrefillAfire; currentpostincrementLSB selectsfillway'),
                full448B_signature_matches_unobserved=True,original_observer_projection_identical=True,hardware_contacted=False,rtl_design_changed=False,
                calibrated=False,ethan_image_association_verified=False,full_timing_certified=False,held_out_2pct=False,
                limitations=['Saved standalone Iris reference; no image attestation.','Counts can overlap and are not additive causal stall categories.','Observed refills are evidence, not hardcoded timing parameters.'])
    report['artifact_sha256']={str(path.relative_to(out)):sha(path) for path in out.rglob('*') if path.is_file() and not path.is_relative_to(out/'inputs')}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],rows=analysis['rows'],refills=analysis['completed_refills'],histories=len(analysis['measured_miss_eviction_histories']))))


if __name__=='__main__':main()
