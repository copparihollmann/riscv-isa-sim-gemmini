#!/usr/bin/env python3
"""Extract exact compute TLSplit/width/buffer source instances; no elaboration."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
RTL=ROOT/'build/saturn-timing-component-v1-final/build/saturn-timing-source-v1/compute/rtl'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ports(text):
    text=re.sub(r'//[^\n]*','',text)
    return [dict(direction=d,width=int(hi)+1 if hi else 1,name=n)for d,hi,n in re.findall(r'^\s*(input|output)\s+(?:\[(\d+):0\]\s+)?(\w+)\s*(?:[,)]|$)',text,re.M)]
def main():
    a=argparse.ArgumentParser(__doc__);a.add_argument('--output',type=Path,required=True);args=a.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    parent=RTL/'SaturnShuttleUnit.sv';text=parent.read_text();blocks=[];anchors=[]
    for module,name in [('TLSplitInterface','tl_if'),('TLWidthWidget16','widget'),('TLBuffer_a35d256s5k4z4u','buffer')]:
        pattern=rf'^  {module} {name} \(.*?^  \);[^\n]*'
        matches=list(re.finditer(pattern,text,re.S|re.M));assert len(matches)==1,(module,len(matches))
        m=matches[0];blocks.append(m.group());anchors.append(dict(module=module,instance=name,line=text.count('\n',0,m.start())+1,exact_block_sha256=hashlib.sha256(m.group().encode()).hexdigest()))
    parent_ports=ports(text[:text.index(');')+2]);split_ports=ports((RTL/'TLSplitInterface.sv').read_text().split(');',1)[0]+');')
    external=[p for p in parent_ports if p['name']in['clock','reset']or p['name'].startswith('auto_atl_out_')]+[p for p in split_ports if p['name'].startswith('io_vec_')or p['name']=='io_mem_busy']
    assert len(external)==38,len(external)
    names={p['name']for p in external};block_text='\n'.join(blocks)
    used=set(re.findall(r'\b\w+\b',block_text));wires=[]
    for line in text.splitlines():
        m=re.match(r'^  wire\s+(?:\[\d+:0\]\s+)?(\w+)\s*;',line)
        if m and m[1]in used:wires.append(line)
    conns=dict(re.findall(r'\.(io_vec_\w+|io_mem_busy)\s*\(\s*(\w+)\s*\)',blocks[0]));assert len(conns)==len(external)-22,len(conns)
    aliases=[]
    for p in external:
        if p['name']not in conns:continue
        endpoint=conns[p['name']]
        aliases.append('  assign '+(endpoint+' = '+p['name']if p['direction']=='input'else p['name']+' = '+endpoint)+';')
    declarations=[f"  {p['direction']} "+(f"[{p['width']-1}:0] "if p['width']>1 else'')+p['name']for p in external]
    wrapper='// Exact three-instance projection of saved SaturnShuttleUnit.\nmodule IrisComputeStorefront(\n'+',\n'.join(declarations)+'\n);\n'+'\n'.join(wires)+'\n'+block_text+'\n'+'\n'.join(aliases)+'\nendmodule\n'
    copied=out/'rtl';copied.mkdir();(copied/'IrisComputeStorefront.sv').write_text(wrapper)
    wanted=['TLSplitInterface','TLWidthWidget16','TLBuffer_a35d256s5k4z4u'];seen=set();inputs=[Path(__file__).resolve(),parent]
    while wanted:
        name=wanted.pop()
        if name in seen:continue
        seen.add(name);path=RTL/(name+'.sv');assert path.exists(),name
        source=path.read_text();shutil.copy2(path,copied/path.name);inputs.append(path)
        for module,instance in re.findall(r'^\s*(\w+)\s+(\w+)\s*\(',source,re.M):
            if module not in ['module','if','else','assert','assume','cover']and(RTL/(module+'.sv')).exists():wanted.append(module)
    extraction=dict(schema='iris.compute_Saturn_storefront_extraction.v1',**{'pass':True},parent_sha256=sha(parent),source_instances=anchors,ports=external,modules=sorted(seen),wrapper_sha256=sha(copied/'IrisComputeStorefront.sv'),
       no_separate_compute_SaturnDCache=True,scalar_L1D_bypassed=True,excludes=['VMU/AddrGen/SIQ/SIFQ/ROB ownership','VRF/sequencers/CPU','tile/System/NoC/L2/FASED'],input_sha256={str(p):sha(p)for p in inputs})
    (out/'extraction.json').write_text(json.dumps(extraction,indent=2)+'\n')
    tool=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator');perl=tool.with_name('perl');started=time.monotonic()
    cmd=[str(perl),str(tool),'--cc','--build','-j','4','--top-module','IrisComputeStorefront','--prefix','VComputeStorefront','--assert','-Wno-fatal','--x-initial','unique','--x-assign','unique','--Mdir',str(out/'model'),'+define+RANDOMIZE_MEM_INIT','+define+RANDOMIZE_REG_INIT',*[str(p)for p in sorted(copied.glob('*.sv'))],'-MAKEFLAGS','CXX=/usr/bin/g++ LINK=/usr/bin/g++ AR=/usr/bin/ar RANLIB=/usr/bin/ranlib OPT_FAST=-O3 OPT_SLOW=-O3']
    with(out/'stdout').open('wb')as so,(out/'stderr').open('wb')as se:
        result=subprocess.run(cmd,stdout=so,stderr=se,timeout=180,env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']))
    report=dict(schema='iris.compute_Saturn_storefront_build.v1',**{'pass':result.returncode==0},argv=cmd,exit_status=result.returncode,host_seconds=time.monotonic()-started,extraction_sha256=sha(out/'extraction.json'),input_sha256={str(p):sha(p)for p in inputs+[tool,perl]},source_RTL_modules_modified=False,source_instances_modified=False,hardware_contacted=False,full_SoC_or_native_qualification=False)
    if result.returncode==0:report['library_sha256']=sha(out/'model/VComputeStorefront__ALL.a')
    (out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(pass_=report['pass'],modules=len(seen),ports=len(external),report_sha256=sha(out/'build.json'))))
    return result.returncode
if __name__=='__main__':raise SystemExit(main())
