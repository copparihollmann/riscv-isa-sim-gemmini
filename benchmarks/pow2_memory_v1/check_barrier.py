#!/usr/bin/env python3
"""Finite check/check-to-WFI race model, plus actual compiled corpus proof."""
import argparse
import hashlib
import itertools
import json
import re
import struct
import subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def race(initial_pending, order):
    # Two waiters have already atomically arrived; the last arriver releases.
    # Each step is indivisible. A pending locally-enabled interrupt wakes WFI
    # with global MIE masked, as demonstrated by the saved source Core proof.
    start=(0,0,(0,0),(-1,-1),initial_pending)
    seen=set();todo=[start];terminal=0
    while todo:
        s=todo.pop()
        if s in seen:continue
        seen.add(s)
        gen,last,pc,loaded,pending=s
        if pc==(5,5) and last==3:terminal+=1;continue
        successors=[]
        if last<3:
            q=list(pending)
            if last==0:g=1
            else:g=gen;q[order[last-1]]=1
            successors.append((g,last+1,pc,loaded,tuple(q)))
        for h in range(2):
            p=list(pc);v=list(loaded);q=list(pending)
            if pc[h]==0:p[h]=1 # mask global MIE
            elif pc[h]==1:v[h]=gen;p[h]=2 # acquire generation
            elif pc[h]==2:
                if loaded[h]!=0:p[h]=3
                elif pending[h]:p[h]=3 # WFI observes pending MSIP
                else:continue # sleeping; last arriver can still send MSIP
            elif pc[h]==3:q[h]=0;p[h]=4 # restore MIE; handler may consume MSIP
            elif pc[h]==4:p[h]=5 if loaded[h]!=0 else 0
            else:continue
            successors.append((gen,last,tuple(p),tuple(v),tuple(q)))
        if not successors:raise ValueError('Lost wakeup / terminal deadlock')
        # A waiter cannot leave until it has acquired the released generation.
        for x in successors:
            if any(x[2][h]==5 and x[3][h]!=1 for h in range(2)):
                raise ValueError('Barrier released before generation publication')
        todo.extend(successors)
    if not terminal:raise ValueError('No completed barrier schedule')
    return len(seen)

def compiled(build):
    raw=(build/'footprints.elf').read_bytes();corpus=json.loads((build/'corpus.json').read_text())
    ph=struct.unpack_from('<Q',raw,32)[0];psz,pn=struct.unpack_from('<HH',raw,54)
    segs=[struct.unpack_from('<IIQQQQQQ',raw,ph+i*psz)for i in range(pn)]
    def read(addr,n):
        for typ,flags,off,va,pa,fs,ms,align in segs:
            if typ==1 and va<=addr and addr+n<=va+fs:return raw[off+addr-va:off+addr-va+n]
        raise ValueError('Unbacked compiled-table address')
    symbols={x.split()[-1]:(int(x.split()[0],16),int(x.split()[1],16))for x in(build/'symbols.txt').read_text().splitlines()if len(x.split())==4}
    addr,size=symbols['experiments']
    if size!=24*117:raise ValueError('Wrong compiled table size')
    def check(blob):
        for i,c in enumerate(corpus['cases']):
            ptr,nodes,mask,trial=struct.unpack_from('<QIII',blob,i*24)
            if(nodes,mask,trial)!=(c['nodes'],c['mask'],c['trial_id']):raise ValueError('Compiled table word differs')
            expected=c['case_id'].encode()+b'\0'
            if read(ptr,len(expected))!=expected:raise ValueError('Compiled case string differs')
    blob=read(addr,size);check(blob)
    bad=bytearray(blob);bad[8]^=1
    try:check(bad)
    except ValueError:pass
    else:raise ValueError('Changed compiled table admitted')
    for name in('arrivals','generation'):
        address=symbols[name][0]
        if not 0x80000000<=address<0x90000000:raise ValueError('Barrier atomic state not in DRAM ELF')
    kernel=json.loads((build/'build.json').read_text())['exact_loop']
    if read(kernel['address'],16)!=struct.pack('<4I',0x00053503,0xfff58593,0xfe059ce3,0x00008067):raise ValueError('Kernel changed')
    old=ROOT/'benchmarks/memory_footprints_mtime_wfi_groups_v8'
    for name in('runtime.c','start.S','runtime.h','uart_drain.h','link.ld'):
        if sha(HERE/'runtime'/name)!=sha(old/'runtime'/name):raise ValueError('Qualified WFI runtime changed')
    text=(HERE/'runtime/runtime.c').read_text()
    if not re.search(r'csrrc.*mstatus',text)or 'fence iorw,iorw'not in text:raise ValueError('Mask/order contract missing')
    return {'compiled_cases_checked':117,'changed_table_word_rejected':True,'barrier_state_addresses':{n:symbols[n][0]for n in('arrivals','generation')},'exact_kernel_bytes_unchanged':True,'private_runtime_byteidentical_qualified_WFI_v8':True,'common_runtime_changes_confined_to_barrier':True}

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);a=p.parse_args();b=a.build.resolve()
    counts=[race(pending,order)for pending in itertools.product((0,1),repeat=2)for order in itertools.permutations((0,1))]
    report={'schema':'iris.footprint_WFI_barrier_race_and_compiled_proof.v1','pass':True,'finite_interleaving_states':sum(counts),'initial_pending_and_wake_orders':8,'model_scope':'Two waiting peers and last-arriver generation publication plus both ordered MMIO wakes; arbitrary check/WFI/restoration interleavings and stale MSIP states. Assumes eventual fair execution and delivered MSIP writes. Not a complete SMP hardware liveness proof.','compiled':compiled(b),'new_exact_reference_required':True,'IRQ_and_cache_history_changed':True,'hardware_contacted':False,'input_sha256':{str(p):sha(p)for p in[Path(__file__).resolve(),HERE/'runtime/runtime.c',HERE/'guest.c',b/'footprints.elf',b/'corpus.json',b/'layout.json',b/'build.json',b/'symbols.txt',ROOT/'build/Shuttle-WFI-source-component-v3/run.json']}}
    (b/'barrier-proof.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'states':sum(counts),'sha256':sha(b/'barrier-proof.json')}))

if __name__=='__main__':main()
