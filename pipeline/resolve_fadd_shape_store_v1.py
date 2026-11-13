#!/usr/bin/env python3
"""Explicit independent-feature merge resolutions; no parent source changes."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'pipeline/riscv-isa-sim-fadd-shape-store-v2'
OUT=ROOT/'build/fadd-shape-store-composition-v2'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def resolve(name,n,ours,base,theirs):
    if name=='iris_empirical_features.inc':
        assert n==1
        return ours.replace(' write_rocket_packet_json(out);',' empirical_store_write_totals(out);write_rocket_packet_json(out);',1)
    if name=='iris_timing_adapter.h':
        if n==1:return ours.replace('empirical_vme_shape_work=false;','empirical_vme_shape_work=false,empirical_store_front=false;')
        assert n==2
        return ours+theirs
    if name=='iris_timing_adapter.cc':
        if n==1:return ours+theirs
        if n==2:return ours.replace('p.empirical_vme_shape_work||','p.empirical_vme_shape_work||p.empirical_store_front||')
        assert n==3
        return theirs+ours  # Owned store blocks dispatch before any IRQ issue.
    assert name=='iris_shuttle_issue.cc'
    if n in (1,3,5):
        return ours.replace('bool scalar_fadd=false)','bool scalar_fadd=false,bool stores=false)').replace(',fadd,scalar_fadd)',',fadd,scalar_fadd,stores)')
    if n==2:
        return ours.replace('((expanded>>12)&7)<=6)) return {};','((expanded>>12)&7)<=6) && !(stores&&uop.has(iris::shuttle::MEM)&&(expanded&127)==0x23&&((expanded>>12)&7)<=3)) return {};')
    if n==4:return ours.replace('(uint64_t(scalar_fadd)<<6);','(uint64_t(scalar_fadd)<<6)|(uint64_t(stores)<<7);')
    if n in (6,7,8,9,13,15):
        result=ours.replace('profile_.empirical_scalar_fadd)','profile_.empirical_scalar_fadd,profile_.empirical_store_front)')
        if n==7:result=result.replace('!empirical_load_candidate(hart,*candidate))','!empirical_load_candidate(hart,*candidate)&&!empirical_store_candidate(hart,*candidate))')
        return result
    if n in (10,16):return ours.replace('stored.empirical_compute||scalar_fadd_candidate','stored.empirical_store||stored.empirical_compute||scalar_fadd_candidate')
    if n in (11,17):
        return ours.replace('} else if(row.empirical_compute)',
            '} else if(row.empirical_store){row.private_value=0;p.values->complete_external(id,0);row.private_value_ready=true;}\n    else if(row.empirical_compute)',1)
    if n==12:return ours+theirs
    assert n==14
    return ours.replace('||source_counter_read(*uop)','||empirical_store_candidate(hart,*uop)||source_counter_read(*uop)',1)


def main():
    records=[]
    for name,count in [('iris_empirical_features.inc',1),('iris_timing_adapter.h',2),('iris_timing_adapter.cc',3),('iris_shuttle_issue.cc',17)]:
        path=SOURCE/'riscv'/name;raw=path.read_text();lines=raw.splitlines(True);out=[];i=0;n=0
        (OUT/(name+'.unresolved')).write_text(raw)
        while i<len(lines):
            if not lines[i].startswith('<<<<<<<'):out.append(lines[i]);i+=1;continue
            a=i+1;j=a
            while not lines[j].startswith('|||||||'):j+=1
            k=j+1
            while not lines[k].startswith('======='):k+=1
            l=k+1
            while not lines[l].startswith('>>>>>>>'):l+=1
            n+=1;ours=''.join(lines[a:j]);base=''.join(lines[j+1:k]);theirs=''.join(lines[k+1:l])
            merged=resolve(name,n,ours,base,theirs)
            if merged==base:raise ValueError('Resolution lost both feature changes')
            out.append(merged);records.append({'file':name,'conflict':n,'ours':ours,'base':base,'theirs':theirs,'resolution':merged});i=l+1
        if n!=count:raise ValueError('Unexpected conflict set: '+name)
        path.write_text(''.join(out))
    report={'schema':'iris.fadd_shape_store_explicit_resolution.v1','pass':True,'resolutions':records,
        'decoder_argument_order':'vector_fadd,scalar_fadd,stores','memo_flag_bits':{'scalar_fadd':6,'stores':7},
        'commit_policy':'Store-before-COM gate may defer without stepping; after actual step run mutually exclusive scalarFADD/store publication hooks once.',
        'parent_sources_modified':False,'input_sha256':{str(Path(__file__).resolve()):sha(__file__)},
        'resolved_source_sha256':{str(SOURCE/'riscv'/name):sha(SOURCE/'riscv'/name)for name in
            ('iris_empirical_features.inc','iris_timing_adapter.h','iris_timing_adapter.cc','iris_shuttle_issue.cc')}}
    (OUT/'manual-resolutions.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'pass':True,'explicit_conflicts_resolved':len(records)}))


if __name__=='__main__':main()
