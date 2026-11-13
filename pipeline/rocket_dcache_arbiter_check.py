#!/usr/bin/env python3
"""Build the exact source Rocket Dcache arbiter physical phase peer."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def fields(path):
    header=path.read_text().split(');',1)[0]
    return [(d,int(hi)+1 if hi else 1,n)for d,hi,n in re.findall(r'^\s*(input|output)\s*(?:\[(\d+):0\])?\s*(\w+)\b',header,re.M)if n!='clock']
def generate(items):
    ins=[(w,n)for d,w,n in items if d=='input'];outs=[(w,n)for d,w,n in items if d=='output'];text=[]
    for define,rows in [('INPUT_FIELDS',ins),('OUTPUT_FIELDS',outs)]:text+=['#ifdef '+define+'\n','static constexpr Field fields[]={'+','.join('{"'+n+'",'+str(w)+'}'for w,n in rows)+'};return fields;\n','#endif\n']
    text+=['#ifdef ZERO_INPUTS\n','dut->clock=0;\n']
    for width,name in ins:text.append(''.join('dut->'+name+'['+str(i)+']=0;\n'for i in range((width+31)//32))if width>64 else 'dut->'+name+'=0;\n')
    text+=['#endif\n','#ifdef SET_INPUTS\n']
    for index,(width,name)in enumerate(ins):
        if width>64:text.extend('dut->'+name+'['+str(i)+']=in['+str(index)+'].value.limbs['+str(i//2)+']>>'+str((i%2)*32)+';\n'for i in range((width+31)//32))
        else:text.append('dut->'+name+'=in['+str(index)+'].value.limbs[0];\n')
    text+=['#endif\n','#ifdef GET_OUTPUTS\n']
    for index,(width,name)in enumerate(outs):
        if width>64:text.extend('out['+str(index)+'].limbs['+str(i//2)+']|=uint64_t(dut->'+name+'['+str(i)+'])<<'+str((i%2)*32)+';\n'for i in range((width+31)//32))
        else:text.append('out['+str(index)+'].limbs[0]=dut->'+name+';\n')
    text+=['#endif\n'];return ''.join(text),ins,outs
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    gen=ROOT/'build/rtl-verilator/gen-collateral';source=gen/'HellaCacheArbiter_1.sv';pins,ins,outs=generate(fields(source));(out/'rocket_dcache_arbiter_pins.inc').write_text(pins)
    if 'HellaCacheArbiter_1 dcacheArb'not in(gen/'RocketTile.sv').read_text():raise ValueError('actual Rocket arbiter instance changed')
    sdk=ROOT/'build/memory-fabric-coupled-native-v4/sdk';obj=out/'obj';tool=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator');perl=tool.with_name('perl');compiler=Path(shutil.which('g++')).resolve();test=ROOT/'pipeline/test_rocket_dcache_arbiter.cpp';peer=ROOT/'pipeline/rocket_dcache_arbiter.cpp'
    commands=[[str(perl),str(tool),'--cc','--exe','-Wno-fatal','--top-module','HellaCacheArbiter_1','--Mdir',str(obj),str(source),str(test),str(peer),'-CFLAGS','-std=c++20 -O2 -I'+str(ROOT/'pipeline')+' -I'+str(out)+' -I'+str(sdk)],['make','-C',str(obj),'-f','VHellaCacheArbiter_1.mk','-j8','CXX='+str(compiler),'LINK='+str(compiler),'AR=ar']]
    for i,argv in enumerate(commands):
        r=subprocess.run(argv,text=True,capture_output=True);(out/f'build-{i}.log').write_text(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError('source arbiter build failed: '+r.stderr[-4500:])
    binary=obj/'VHellaCacheArbiter_1';r=subprocess.run([str(binary)],text=True,capture_output=True);(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode:raise RuntimeError('source arbiter semantic test failed: '+r.stderr)
    findings=json.loads(r.stdout);inputs=[Path(__file__).resolve(),source,gen/'RocketTile.sv',ROOT/'third_party/rocket-chip/src/main/scala/rocket/HellaCacheArbiter.scala',test,peer,ROOT/'pipeline/rocket_dcache_arbiter.hpp',out/'rocket_dcache_arbiter_pins.inc',sdk/'memory_fabric.hpp',sdk/'memory_fabric_adapters.hpp',tool,perl,compiler]
    archived=out/'inputs';archived.mkdir();hashes={str(p):sha(p)for p in inputs}
    for path in inputs:
        dst=archived/hashes[str(path)]
        if not dst.exists():shutil.copy2(path,dst)
    report=dict(schema='iris.rocket.source_dcache_arbiter.v1',status=findings['status'],findings=findings,input_sha256=hashes,commands=commands,binary_sha256=sha(binary),source_pin='fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0',input_fields=[dict(name=n,width=w)for w,n in ins],output_fields=[dict(name=n,width=w)for w,n in outs],source_state_injected=False,full_internal_knownness_certified=False,native_integration=False,timing_certified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(findings))
if __name__=='__main__':main()
