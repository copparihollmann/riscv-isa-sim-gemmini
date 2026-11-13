#!/usr/bin/env python3
"""Build actual saved Rocket Frontend+IBuf with source CPU wiring."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def ports(path):
    header=path.read_text().split(');',1)[0]
    fields=re.findall(r'^\s*(input|output)\s*(\[[^]]+\]\s*)?(\w+)\b',header,re.M)
    if len(fields)<20:raise ValueError('source frontend port list incomplete')
    return [(direction,width.strip(),name)for direction,width,name in fields]
def wrapper(gen):
    frontend=ports(gen/'Frontend.sv');ibuf=ports(gen/'IBuf.sv');top=[];fmap=[];bmap=[]
    # RocketCore.scala324 connects the complete frontend response to IBuf;
    # line325 kills IBuf on the same take_pc driving frontend req.valid1101.
    for direction,width,name in frontend:
        if name=='io_cpu_resp_ready':fmap.append('.'+name+'(ibuf_imem_ready)');continue
        top.append(f'{direction} {width} {name}');fmap.append('.'+name+'('+name+')')
    top.append('input cpu_id_ready')
    for direction,width,name in ibuf:
        if name in ('clock','reset'):value=name
        elif name=='io_imem_ready':value='ibuf_imem_ready'
        elif name=='io_imem_valid':value='io_cpu_resp_valid'
        elif name.startswith('io_imem_bits_'):value=name.replace('io_imem_bits_','io_cpu_resp_bits_',1)
        elif name=='io_kill':value='io_cpu_req_valid'
        elif name=='io_inst_0_ready':value='cpu_id_ready'
        elif direction=='output':
            value='ibuf_'+name.removeprefix('io_');top.append(f'output {width} {value}')
        else:raise ValueError('unclassified source IBuf input: '+name)
        bmap.append('.'+name+'('+value+')')
    return 'module IrisRocketFrontendPeer('+','.join(top)+');\nwire ibuf_imem_ready;\nFrontend frontend('+','.join(fmap)+');\nIBuf ibuf('+','.join(bmap)+');\nendmodule\n'
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    gen=ROOT/'build/rtl-verilator/gen-collateral';top=out/'IrisRocketFrontendPeer.sv';top.write_text(wrapper(gen));obj=out/'obj';test=ROOT/'pipeline/test_rocket_frontend_unit.cpp';perl=Path('/scratch/eygao/iris-cy/.conda-env/bin/perl');tool=perl.with_name('verilator');compiler=Path(shutil.which('g++')).resolve()
    commands=[[str(perl),str(tool),'--cc','--exe','-Wno-fatal','--top-module','IrisRocketFrontendPeer','--Mdir',str(obj),'-y',str(gen),'+libext+.sv+.v',str(top),str(test),'-CFLAGS','-std=c++20 -O2 -I'+str(out)],['make','-C',str(obj),'-f','VIrisRocketFrontendPeer.mk','-j8','CXX='+str(compiler),'LINK='+str(compiler),'AR=ar']]
    for i,cmd in enumerate(commands):
        if i==1:
            header=(obj/'VIrisRocketFrontendPeer.h').read_text();inputs=re.findall(r'VL_IN(?:8|16|64|W)?\(&([A-Za-z0-9_]+),',header)
            if not inputs or 'io_ptw_status_prv'not in inputs:raise ValueError('actual Rocket frontend interface changed')
            (out/'zero_inputs.inc').write_text(''.join('dut.'+name+'=0;\n'for name in inputs))
        r=subprocess.run(cmd,text=True,capture_output=True);(out/f'build-{i}.log').write_text(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError('source Rocket frontend build failed: '+str(out/f'build-{i}.log'))
    binary=obj/'VIrisRocketFrontendPeer';r=subprocess.run([str(binary)],text=True,capture_output=True);(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode:raise RuntimeError('source Rocket frontend unit failed: '+r.stderr)
    findings=json.loads(r.stdout);actual=[]
    for line in(obj/'VIrisRocketFrontendPeer__verFiles.dat').read_text().splitlines():
        if line.startswith('S '):actual.append(Path(line.rsplit('"',2)[1]))
    actual += [Path(__file__).resolve(),test,perl,tool,compiler,out/'zero_inputs.inc',ROOT/'third_party/rocket-chip/src/main/scala/rocket/RocketCore.scala']
    report=dict(schema='iris.rocket.source_frontend_component.v1',status=findings['status'],findings=findings,input_sha256={str(p):sha(p)for p in actual},commands=commands,binary_sha256=sha(binary),
                source_wiring='Saved Frontend response directly to saved IBuf; same req.valid/take_pc kills IBuf, matching RocketCore324/325/1101; actual emitted clocks ungated in this configuration.',
                scope='M-mode VM-disabled, reset PMPentries inactive, explicit synthetic backend/readiness/ROM service. Native Rocket pipeline integration pending.',source_state_injected=False,native_integration=False,calibrated=False,rtl_certified=False,held_out_2pct=False,ethan_image_association_verified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(findings))
if __name__=='__main__':main()
