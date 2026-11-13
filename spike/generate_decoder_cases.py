#!/usr/bin/env python3
"""Derive decoder predicates independently from pinned Saturn's Scala declarations."""
import argparse
import hashlib
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent

def derive(source):
    inst=source/'src/main/scala/insns/Instructions.scala'
    const=source/'src/main/scala/common/Consts.scala'
    text=inst.read_text();constants=const.read_text()
    enum_body=re.search(r'object OPMFunct6 extends ChiselEnum \{(.*?)\n\}',constants,re.S).group(1)
    enums={};index=0
    for names,explicit in re.findall(r'val ([\w, ]+) = Value(?:\((0x[0-9a-f]+|\d+)\.U\))?',enum_body):
        if explicit:index=int(explicit,0)
        for name in names.split(','):
            enums[name.strip()]=index;index+=1
    f3={name:int(bits,2) for name,bits in re.findall(r'def (OP\w+) = "b([01]+)"\.U',constants)}
    result=[]
    for name,body in re.findall(r'object (SF_\w+)\s+extends VectorInstruction \{ val props = Seq\((.*?)\) \}',text,re.S):
        match=0x77 if 'OPVE.Y' in body else 0x57;mask=0x7f
        bits=re.search(r'F6\(BitPat\("b([01?]+)"\)\)',body)
        if bits:
            pattern=bits.group(1)
            for i,bit in enumerate(reversed(pattern)):
                if bit!='?':mask|=1<<(26+i);match|=int(bit)<<(26+i)
        else:
            enum=re.search(r'F6\(OPMFunct6\.(\w+)\)',body).group(1)
            mask|=63<<26;match|=enums[enum]<<26
        group=re.search(r'F3\(VectorConsts\.(\w+)\)',body).group(1)
        mask|=7<<12;match|=f3[group]<<12
        for field,offset in [('RS1',15),('RS2',20)]:
            literal=re.search(field+r'\(\s*(\d+)\.U\(5.W\)\)',body)
            if literal:mask|=31<<offset;match|=int(literal.group(1))<<offset
        result.append({'name':name,'match':match,'mask':mask})
    if len(result)!=6:raise ValueError(f'Expected six Iris OPU groups, got {len(result)}')
    return result, {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [inst,const]}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    args=parser.parse_args();cases,digests=derive(args.source)
    header='// Generated from independently parsed Saturn Scala; do not edit.\nstruct DecoderCase { const char* name; uint32_t match, mask; };\nstatic const DecoderCase decoder_cases[] = {\n'
    header+=''.join(f'  {{"{case["name"]}", {case["match"]:#x}u, {case["mask"]:#x}u}},\n' for case in cases)+'};\n'
    (HERE/'decoder_cases.hpp').write_text(header)
    (HERE/'decoder_sources.json').write_text(json.dumps({'inputs':digests,'cases':cases},indent=2)+'\n')
if __name__=='__main__':main()
