#!/usr/bin/env python3
"""Extract exact Boolean PLA terms for Rocket's elaborated FPU read controls."""
from functools import lru_cache
import os
from pathlib import Path
import hashlib,json,re

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
MODULE=os.environ.get('IRIS_FPU_DECODER','FPUDecoder_4')
FIR=Path('/scratch/eygao/iris-cy/sims/firesim-staging/generated-src/firechip.chip.FireSim.IrisFiresimNOCflushCombinedConfig/firechip.chip.FireSim.IrisFiresimNOCflushCombinedConfig.fir')

def args(text):
    result=[];start=depth=0
    for i,c in enumerate(text):
        if c=='(':depth+=1
        elif c==')':depth-=1
        elif c==',' and depth==0:result.append(text[start:i].strip());start=i+1
    return result+[text[start:].strip()]

def main():
    manifest=json.loads((ROOT/'hardware/manifest.json').read_text())
    expected=manifest['sources']['firesim-fir']['sha256']
    digest=hashlib.sha256()
    with FIR.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    if digest.hexdigest()!=expected:raise ValueError('Elaborated FIR digest differs from audited input')
    rows=[];first=None
    for no,line in enumerate(FIR.open(),1):
        if line.startswith('  module '+MODULE+' '):first=no
        elif first and line.startswith('  module '):break
        if first:rows.append(line)
    if not first:raise ValueError('Expected Rocket FPUDecoder_4 module absent')
    snapshot=''.join(rows);out=HERE/'fpcomp-evidence';out.mkdir(exist_ok=True)
    (out/(MODULE+'.fir')).write_text(snapshot)
    definitions={}
    for line in rows:
        line=line.split(' @[')[0].strip()
        if line.startswith('node '):name,expression=line[5:].split(' = ',1);definitions[name]=expression
        elif line.startswith('connect '):name,expression=line[8:].split(', ',1);definitions[name]=expression
    # Every bit is a DNF set of (mask, value) conjunctions. This supports only
    # the audited combinational PLA operations and rejects other FIR syntax.
    def conjunction(a,b):
        return frozenset((ma|mb,va|vb) for ma,va in a for mb,vb in b if not((va^vb)&ma&mb))
    def invert(terms):
        result=frozenset({(0,0)})
        for mask,value in terms:
            negated=frozenset((1<<bit,(~value)&(1<<bit)) for bit in range(32) if mask&(1<<bit))
            result=conjunction(result,negated)
        return result
    @lru_cache(None)
    def expression(text):
        if text=='io.inst':return tuple(frozenset({(1<<bit,1<<bit)}) for bit in range(32))
        if text in definitions:return expression(definitions[text])
        literal=re.fullmatch(r'UInt<(\d+)>\(0h([0-9a-f]+)\)',text)
        if literal:
            width,value=int(literal[1]),int(literal[2],16)
            return tuple(frozenset({(0,0)}) if value&(1<<bit) else frozenset() for bit in range(width))
        operation,rest=text.split('(',1);values=args(rest[:-1])
        if operation=='bits':return expression(values[0])[int(values[2]):int(values[1])+1]
        operands=[expression(value) for value in values]
        if operation=='cat':return operands[1]+operands[0]
        if operation=='not':return tuple(invert(bit) for bit in operands[0])
        if operation=='orr':return (frozenset().union(*operands[0]),)
        if operation=='andr':
            product=frozenset({(0,0)})
            for bit in operands[0]:product=conjunction(product,bit)
            return (product,)
        if operation=='or':return tuple(a|b for a,b in zip(*operands))
        if operation=='and':return tuple(conjunction(a,b) for a,b in zip(*operands))
        raise ValueError('Unverified decoder FIR operation: '+operation)
    terms=expression('io.sigs.wflags')[0]
    from generate_fpcomp_cases import NAMES
    encoding=(HERE/'source/riscv/encoding.h').read_text()
    cases=[]
    for name in NAMES:
        if not name.endswith(('.vf','.wf')):continue
        value=int(re.search(r'#define MATCH_'+name.replace('.','_').upper()+r' (0x[0-9a-f]+)',encoding)[1],16)
        mask=0xfc00707f
        intersections=[{'mask':hex(m),'value':hex(v)} for m,v in terms if not((value^v)&mask&m)]
        cases.append({'instruction':name,'match':hex(value),'mask':hex(mask),'wflags_true_terms':intersections})
    result={'module':MODULE,'module_first_line':first,'module_lines':len(rows),'fir_sha256':expected,
            'snapshot_sha256':hashlib.sha256(snapshot.encode()).hexdigest(),
            'wflags_pla_terms':[{'mask':hex(m),'value':hex(v)} for m,v in sorted(terms)],'cases':cases,
            'source_image_association_verified':False,'rtl_executed':False}
    (HERE/('fpcomp-'+MODULE+'-proof.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'cases':len(cases),'intersections':sum(bool(row['wflags_true_terms']) for row in cases),'terms':len(terms)}))

if __name__=='__main__':main()
