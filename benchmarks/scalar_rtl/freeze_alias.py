#!/usr/bin/env python3
"""Freeze the whole-CPU writable-vs-read-only counter-address control."""
import argparse
import json
from pathlib import Path
import shutil
from build import ROOT,sha


def checked(directory):
    run=json.loads((directory/'results.json').read_text())
    if run['exit_status']!=0 or run['timed_out'] is not False:raise ValueError('failed alias-control process')
    for name,digest in run['artifact_sha256'].items():
        if sha(directory/name)!=digest:raise ValueError('changed raw alias-control artifact '+name)
    for path,digest in run['input_sha256'].items():
        if sha(directory/'inputs'/digest)!=digest:raise ValueError('changed archived alias-control input '+path)
    elf=directory/'inputs'/run['input_sha256'][run['argv'][-1]]
    words=[int(line,16) for line in (directory/'signature').read_text().splitlines()]
    if len(words)!=56 or words[:8]!=[0x495249535343414c,1,0,1,1,1,0,0]:raise ValueError('failed/incomplete coherent alias control')
    return run,elf.read_bytes(),words


def compare(before,after):
    old,oldelf,ow=checked(before);new,newelf,nw=checked(after)
    if old['status']!='failed' or old.get('error')!='counter/checksum mismatch' or new['status']!='passed_scalar_reference_regions':
        raise ValueError('preserve the original strict failure and successful alias control')
    differences=[i for i,(a,b) in enumerate(zip(oldelf,newelf)) if a!=b]
    if len(oldelf)!=len(newelf) or len(differences)!=8:raise ValueError('exactly eight code bytes must differ')
    for off in differences:
        if oldelf[off]!=0xB0 or newelf[off]!=0xC0:raise ValueError('changed a byte other than the counter CSR address')
        old_word=int.from_bytes(oldelf[off-3:off+1],'little');new_word=int.from_bytes(newelf[off-3:off+1],'little')
        if (old_word&127!=0x73 or old_word>>20 not in (0xB00,0xB02) or (old_word>>12)&7!=2 or
                (old_word>>15)&31 or new_word!=old_word+(0x100<<20)):
            raise ValueError('changed bytes are not the intended CSRRS x0 counter instructions')
    table=[]
    for h in range(3):
        for k in range(2):
            index=8+h*16+k*8;oa=ow[index:index+8];na=nw[index:index+8]
            oc,oi=oa[1]-oa[0],oa[3]-oa[2];nc,ni=na[1]-na[0],na[3]-na[2]
            if oa[4:]!=[257 if k==0 else 292,256,0,0] or na[4:]!=oa[4:] or min(oc,nc)<=0:
                raise ValueError('counter address change altered body/checksum')
            if oi!=(256 if h<2 else 257) or ni!=257 or nc-oc!=(1 if h<2 else 0):
                raise ValueError('whole-CPU alias result contradicts independently proved source policy')
            table.append({'hart':h,'kernel':'dependent256' if k==0 else 'independent256',
                          'writable_counter_cycles':oc,'readonly_alias_cycles':nc,
                          'writable_counter_instret_delta':oi,'readonly_alias_instret_delta':ni})
    return {'elf_file_byte_changes':differences,'counter_address_control_table':table,
            'original_strict_collector_unchanged':True,'body_and_all_other_elf_bytes_identical':True}


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--verify',action='store_true')
    a=p.parse_args();out=a.output.resolve()
    if a.verify:
        r=json.loads((out/'report.json').read_text())
        for name,digest in r['artifact_sha256'].items():
            if sha(out/name)!=digest:raise ValueError('changed frozen alias control '+name)
        if compare(out/'writable',out/'readonly')!=r['analysis']:raise ValueError('alias analysis differs')
        print(json.dumps({'verified':True,'regions':6,'hardware_contacted':False}));return
    before=ROOT/'build/scalar-rtl-reference-v1';after=ROOT/'build/scalar-rtl-alias-reference-v1'
    analysis=compare(before,after);out.mkdir(parents=True,exist_ok=False)
    shutil.copytree(before,out/'writable');shutil.copytree(after,out/'readonly');(out/'source').mkdir()
    sources=[Path(__file__),ROOT/'benchmarks/scalar_rtl/derive_alias.py',ROOT/'build/scalar-rtl-alias-probe-v1/build.json',
             ROOT/'build/csr-phase-proof-v2/report.json',ROOT/'build/pipeline-csr-proof-closed/manifest.json']
    origins={}
    for path in sources:
        digest=sha(path);(out/'source'/digest).write_bytes(path.read_bytes());origins[str(path)]=digest
    r={'schema':'iris.scalar_counter_alias_control.v1','analysis':analysis,'source_input_sha256':origins,
       'hardware_contacted':False,'timing_calibrated':False,'ethan_image_association_verified':False,
       'full_rtl_certified':False,'model_policy_corrected':False}
    r['artifact_sha256']={str(path.relative_to(out)):sha(path) for path in out.rglob('*') if path.is_file()}
    (out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(out/'report.json')


if __name__=='__main__':main()
