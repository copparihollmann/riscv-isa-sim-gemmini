#!/usr/bin/env python3
"""Separate-agent exact-ELF/golden review; no packet validator imports or HW labels."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import struct

from fp8_format_functional_audit_v1 import Elf

ROOT=Path(__file__).resolve().parents[1]
BUILD=ROOT/'build/rvv-compute-heldout2-asm-v1'
ELF_SHA='e4a4f194d78e5a02191dc99d07a03d47e9e69bf1b263d0b420870954b6c0fa07'
READY_SHA='7c64d37bcb5a8b2eab476bf49fbb8f861c1acb75272f0ef1914e2806a891a45d'
KINDS=['integer','fp','load','store','load_use','load_independent','store_compute','rowmove','matrix_int','matrix_fp8']
MASK64=(1<<64)-1


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,why):
    if not ok:raise ValueError(why)
def symbol(e,name):
    rows=e.symbols[name];need(len(rows)==1,'Unique ELF symbol '+name);return rows[0]
def instructions(e,name):
    start,size=symbol(e,name);out=[];at=start
    while at<start+size:
        low=int.from_bytes(e.read(at,2),'little');n=4 if low&3==3 else 2
        out.append((at,n,int.from_bytes(e.read(at,n),'little')));at+=n
    need(at==start+size,'Instruction boundary');return out
def vop(vd,vs2,vs1,form=0):return (1<<25)|(vs2<<20)|(vs1<<15)|(form<<12)|(vd<<7)|0x57
def cbranch(w):
    n=((w>>12)&1)<<8|((w>>10)&3)<<3|((w>>5)&3)<<6|((w>>3)&3)<<1|((w>>2)&1)<<5
    return n-512 if n&256 else n
def jal_target(pc,w):
    n=((w>>31)&1)<<20|((w>>21)&1023)<<1|((w>>20)&1)<<11|((w>>12)&255)<<12
    return pc+(n-(1<<21)if n&(1<<20)else n)


def body_check(e):
    bodies={}
    ops={
        'integer0':[vop(8,8,16)],'integer1':[vop(8,8,16),vop(24,24,16)],'integer2':[vop(8,8,16),vop(24,8,16)],
        'fp0':[vop(8,8,16,1)],'fp1':[vop(8,8,16,1),vop(24,24,16,1)],'fp2':[vop(8,8,16,1),vop(24,8,16,1)],
        'load':[0x0205e407],'store':[0x02066427],
        'load_use':[0x0205e407,vop(24,8,16)],'load_independent':[0x0205e407,vop(24,24,1,3)],
        'store_compute':[0x02066427,vop(24,24,1,3)],
        'matrix_int':[(0x79<<25)|(8<<20)|(16<<15)|0x77],
        'matrix_fp8':[(0x79<<25)|(8<<20)|(16<<15)|(1<<12)|0x77]}
    for name,inner in ops.items():
        key='asm_'+name;rows=instructions(e,key);wanted=inner*16;tail=rows[len(wanted):]
        need([(n,w)for _,n,w in rows[:len(wanted)]]==[(4,w)for w in wanted],'Actual target-only body '+key)
        need(len(tail)==3 and tail[0][1:]==(2,0x157d) and tail[2][1:]==(2,0x8082),'Minimal loop counter/return '+key)
        pc,n,w=tail[1];need(n==2 and w&3==1 and w>>13==7 and(w>>7)&7==2 and pc+cbranch(w)==rows[0][0],'Exact counter branch '+key)
        bodies[key]={'address':rows[0][0],'target_static_instructions':len(wanted),'ops_per_repetition':len(inner),
                     'loop_repetitions_per_block':16,'scalar_loop_instructions_per_block':2,
                     'raw_bytes_sha256':hashlib.sha256(e.read(*symbol(e,key))).hexdigest()}
    for count in (3,12,48,192):
        key='asm_row'+str(count);rows=instructions(e,key);want=[]
        for index in range(count):want.extend([(2,0x4001|(28<<7)|((index%32)<<2)),(4,(0x21<<25)|(31<<20)|(28<<15)|(6<<12)|(24<<7)|0x57)])
        want.append((2,0x8082));need([(n,w)for _,n,w in rows]==want,'Exact row indices and target opcodes '+key)
        bodies[key]={'address':rows[0][0],'target_static_instructions':count,'scalar_TSS_index_instructions':count,
                     'row_indices_mod32_verified':True,'raw_bytes_sha256':hashlib.sha256(e.read(*symbol(e,key))).hexdigest()}
    need(len(bodies)==17,'All17 kernels');return bodies


def golden_words(c):
    k=c['kind'];n=c['n'];sew=c['sew'];vl=c['vl']
    def bits(x,b):return int.from_bytes(struct.pack({16:'<e',32:'<f',64:'<d'}[b],float(x)),'little')
    if k in ('matrix_int','matrix_fp8'):
        # Independent reduction over repeated, exactly representable uniform products.
        value=sum((2*3 if k=='matrix_int'else 1)for _ in range(n*c['mode']))
        value=bits(value,32)if k=='matrix_fp8'else value
        return [value if i<vl and j<vl else 0 for i in range(32)for j in range(32)]
    out=[]
    for stream in range(c['streams']):
        for lane in range(vl):
            if k=='integer':
                x=0
                for _ in range(n):x=(x+1)&((1<<sew)-1)
                if stream and c['mode']==2:x=(x+1)&((1<<sew)-1)
            elif k=='fp':x=bits(n+int(stream==1 and c['mode']==2),sew)
            elif k=='load':x=3+lane
            elif k=='store':x=3
            elif k=='load_use':x=3+lane+stream
            elif k=='load_independent':x=n if stream else 3+lane
            elif k=='store_compute':x=n if stream else 3
            elif k=='rowmove':x=2*3
            else:raise ValueError('Unknown operation')
            out.append(x)
    return out
def checksum(words):
    x=14695981039346656037
    for w in words:x=((x^w)*1099511628211)&MASK64
    return x


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
    need(not out.exists(),'Fresh review output only');need(sha(BUILD/'ready.json')==READY_SHA and sha(BUILD/'guest.elf')==ELF_SHA,'Exact requested ready/ELF')
    ready=json.loads((BUILD/'ready.json').read_text());built=json.loads((BUILD/'build.json').read_text());c=json.loads((BUILD/'corpus.json').read_text());cases=c['cases'];q=json.loads((BUILD/'qualification.json').read_text())
    inputs={str(Path(__file__).resolve()):sha(Path(__file__)),str(ROOT/'timing/fp8_format_functional_audit_v1.py'):sha(ROOT/'timing/fp8_format_functional_audit_v1.py')}
    for name,h in ready['artifact_sha256'].items():need(sha(BUILD/name)==h,'Ready artifact '+name);inputs[str(BUILD/name)]=h
    for name,h in built['input_sha256'].items():need(sha(name)==h and sha(BUILD/'inputs'/h)==h,'Exact snapshotted build input');inputs[name]=h
    need(c['train_regions']==0 and c['reserved_regions']==1320 and c['protected_validation_only']is True and c['skip_kernel']is False and len(cases)==1320,'All1320 protected positive cases')
    splitpath=ROOT/'benchmarks/rvv_compute_heldout2_asm_v1/split.json';split=json.loads(splitpath.read_text())
    need(split['train_case_ids']==[] and split['protected_case_ids']==[x['case_id']for x in cases] and sha(splitpath)==c['frozen_split_sha256'],'Frozen all-protected split')
    parent=json.loads((ROOT/'build/rvv-compute-asm-v5/corpus.json').read_text())['cases'];need(len(parent)==len(cases),'Same data geometry population')
    e=Elf(BUILD/'guest.elf');bodies=body_check(e);table,size=symbol(e,'experiments');need(size==1320*48,'Compiled48B table')
    groups=collections.defaultdict(list);want={};word_count=0;wrap_cases=0
    for i,(x,old)in enumerate(zip(cases,parent)):
        for k in ('kind_id','sew','lmul','mode','n','bytes','vl','streams','hart','trial_id'):need(type(x[k])is int,'Typed geometry')
        for k in ('kind','kind_id','sew','lmul','mode','bytes','vl','streams','hart','trial_id'):need(x[k]==old[k],'Unchanged DATA geometry '+k)
        n={1:3,4:12,16:48,64:192}[old['n']]if x['kind']=='rowmove'else{16:96,64:384}[old['n']]
        need(x['n']==n and x['source_case_id']==old['case_id'] and x['kind_id']==KINDS.index(x['kind']),'Fresh repetition lineage')
        need(x['hart']in(0,1) and x['internal_split']=='reserved_holdout' and x['validation_role']=='protected_validation_only','No train/hart2 region')
        for key in('bytes','lmul','sew','vl'):need(x[key]>0 and x[key]&(x[key]-1)==0,'Power-of-two DATA geometry')
        ptr,*fields=struct.unpack('<Q10I',e.read(table+48*i,48))
        need(e.string(ptr)==x['case_id'] and fields==[x[k]for k in('kind_id','sew','lmul','mode','n','bytes','hart','trial_id','vl','streams')],'Actual compiled table identity/fields')
        words=golden_words(x);h=checksum(words);need(h==x['expected_checksum'],'Independent word-value/checksum golden')
        want[x['case_id']]=(x,h,len(words));word_count+=len(words);groups[x['parent_case_id']].append(x['trial_id'])
        if x['kind']=='integer'and x['sew']==8 and n==384:
            need(words[0]==128 and(words[x['vl']]==(129 if x['mode']==2 else 128)if x['streams']==2 else True),'SEW8 wrapping primary/secondary');wrap_cases+=1
    need(word_count==184128 and len(groups)==440 and all(v==[0,1,2]for v in groups.values()),'Complete words/trial groups')
    need([x['hart']for x in cases]==[0]*660+[1]*660,'Hart0then1 order')
    wrapper=instructions(e,'asm_measure');mc=[pc for pc,n,w in wrapper if n==4 and w>>20==0xb00 and w&0x707f==0x2073]
    need(len(mc)==3,'Three real mcycle reads')
    roi=[w for pc,n,w in wrapper if mc[0]<=pc<=mc[2]]
    need(roi==[0xb0002af3,0xb0202b73,0x480e7,0xb0202bf3,0xb0002c73,0x0330000f,0xb0202cf3,0xb0002d73],'Exact call/CSR/fence-only measured wrapper')
    mainrows=instructions(e,'benchmark_main');emitrows=instructions(e,'emit');setup=symbol(e,'setup')[0];measure=symbol(e,'asm_measure')[0];emit=symbol(e,'emit')[0]
    calls=[(pc,jal_target(pc,w))for pc,n,w in mainrows if n==4 and w&127==0x6f and(w>>7)&31==1]
    need([pc for pc,target in calls if target==measure]==[0x80000b70,0x80000e12,0x8000100c],'Actual three compiled measured-call paths')
    need([pc for pc,target in calls if target==setup]==[0x80000aea,0x80000b60,0x80000e04,0x80000ff8],'Compiled full reset call paths')
    need((0x80000b5a,2,0x9482)in mainrows and(0x80000dfe,2,0x9482)in mainrows and(0x80000ff0,symbol(e,'asm_row192')[0])in calls,'All selected body preexecution paths')
    need([pc for pc,target in calls if target==emit]==[0x800010e8],'Sole final emit call')
    need(e.read(0x800010d8,20).hex()=='0f0030039727030023b207b20f003003eff0afb2','Actual count fence / sentinel SDzero / fence / emit bytes')
    need((0x80000c32,4,0x0ff87593)in mainrows,'Compiled C e8 expected-word zext.b')
    need(not any(n==4 and(w&127==0x57 or(w&127 in(7,39)and(w>>12)&7 in(0,5,6,7)))for _,n,w in emitrows),'Scalar-only final emitter')
    # Cross-check every printed raw instruction in the actual disassembly against ELF.
    disasm=(BUILD/'disassembly.txt').read_text();disasm_checks=0
    for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4}|[0-9a-f]{8})\s',disasm,re.M):
        address=int(m[1],16);need(e.read(address,len(m[2])//2)==int(m[2],16).to_bytes(len(m[2])//2,'little'),'Disassembly bytes');disasm_checks+=1
    normal=[]
    for row in q['functional']:
        rp=Path(row['report']);r=json.loads(rp.read_text());need(sha(rp)==row['report_sha256'] and r['pass']is True and r['exit_status']==0 and r['normal_guest_exit_verified']is True and r['timed_out']is False and r['elf_sha256']==ELF_SHA,'Real normal functional proof')
        need(sha(rp.parent/'stdout')==r['stdout_sha256'] and sha(rp.parent/'stderr')==r['stderr_sha256'],'Functional raw hashes')
        rows=[json.loads(s.split(' ',1)[1])for s in(rp.parent/'stdout').read_text().splitlines()if s.startswith('IRIS_REGION ')]
        need(len(rows)==1320,'Functional all1320 rows')
        for actual,x in zip(rows,cases):
            _,h,words=want[x['case_id']];need(actual['case_id']==x['case_id']and actual['hart']==x['hart']and actual['checksum']==actual['expected_checksum']==h and actual['checked_words']==words and actual['mismatch_or']==0 and actual['pass']is True,'Actual source fullword checks + independent checksum')
        normal.append({'seed':r['seed'],'run_sha256':sha(rp),'rows':len(rows),'independent_expected_words':word_count});inputs[str(rp)]=sha(rp);inputs[str(rp.parent/'stdout')]=r['stdout_sha256'];inputs[str(rp.parent/'stderr')]=r['stderr_sha256']
    need({x['seed']for x in normal}=={0,17},'Both functional schedules')
    nr=Path(q['actual_omitted_kernel']['report']);negative=json.loads(nr.read_text());need(sha(nr)==q['actual_omitted_kernel']['report_sha256']and negative['pass']is True and negative['expect_negative']is True and negative['exit_status']!=0 and negative['timed_out']is False,'Actual measured omission proof')
    negrows=[json.loads(s.split(' ',1)[1])for s in(nr.parent/'stdout').read_text().splitlines()if s.startswith('IRIS_REGION ')]
    need(len(negrows)==1320 and all(x['pass']is False and x['mismatch_or']!=0 for x in negrows),'All1320 omission results really differ despite warm execution')
    need(all(x['rejected']is True for x in q['corruption_controls'])and len(q['corruption_controls'])==43,'Existing43 controls retained')
    inputs[str(nr)]=sha(nr);inputs[str(nr.parent/'stdout')]=sha(nr.parent/'stdout');inputs[str(BUILD/'ready.json')]=READY_SHA
    inputs.update({str(ROOT/'firesim'/n):sha(ROOT/'firesim'/n)for n in('prepare_rvv_compute_heldout2_asm.py','analyze_rvv_compute_heldout2_asm.py','rvv_compute_heldout2_asm_review.py','test_rvv_compute_heldout2_asm.py')})
    out.mkdir(parents=True);report={'schema':'iris.heldout2_ASM_separate_agent_review.v1','pass':True,'findings':[],
        'ready_sha256':READY_SHA,'ELF_sha256':ELF_SHA,'compiled_table_rows':1320,'compiled_table_stride':48,'bodies':bodies,
        'actual_disassembly_instruction_crosschecks':disasm_checks,'protected_regions':1320,'TRAIN_regions':0,
        'complete_three_trial_groups':440,'independent_expected_words_per_schedule':word_count,'SEW8_n384_wrap_cases':wrap_cases,
        'functional':normal,'omitted_measured_call_actual_failed_regions':1320,'existing_rejected_controls':43,
        'sentinel_store_PC':0x800010e0,'following_fence_PC':0x800010e4,'sole_emit_call_PC':0x800010e8,
        'warm_setup_measured_path_compiled':True,'UART_between_hart_phases':False,
        'scope':'Source/ELF and independent expected-word math + target per-word mismatch checks and independently recomputed checksum; raw per-word results are not individually exported',
        'measured_fixed_overheads':['JALR/RET','counter reads','two loop instructions per16 repetitions','LI per rowmove'],
        'physical_cache_hit_guaranteed':False,'FP8_format':'E4M3xE4M3 only','hardware_or_network_contacted':False,
        'hardware_timing_labels_consumed':False,'prediction_or_fit_performed':False,'packet_bytes_modified':False,'input_sha256':inputs}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'report_sha256':sha(out/'report.json'),'regions':1320,'words':word_count,'bodies':17}))


if __name__=='__main__':main()
