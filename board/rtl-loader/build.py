#!/usr/bin/env python3
"""Relink the existing, byte-identified Verilator model with explicit loadmem hooks."""
import argparse, hashlib, json, shlex, subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'build/rtl-loader-diag')
    p.add_argument('--tools',type=Path,default=Path('/scratch/eygao/iris-cy/.conda-env'))
    a=p.parse_args(); out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    model=ROOT/'build/rtl-verilator/model';gen=model.parent/'gen-collateral';tools=a.tools.resolve()
    includes=['-I'+str(x) for x in [tools/'riscv-tools/include',gen,model,tools/'share/verilator/include',tools/'share/verilator/include/vltstd']]
    commands=[]
    for name in ['main.cc','SimTSI.cc']:
        cmd=['/usr/bin/g++','-O3','-std=c++20',*includes,'-c',str(Path(__file__).parent/name),'-o',str(out/('preload-'+name+'.o'))]
        subprocess.run(cmd,check=True);commands.append(cmd)
    # -n prints the existing link contract without changing original objects.
    query=['make','-n','-W','SimTSI.o','-f','VTestDriver.mk','CXX=g++','LINK='+str(tools/'bin/x86_64-conda-linux-gnu-c++'),'LDFLAGS=-no-pie -Wl,-rpath,'+str(tools/'lib')]
    lines=subprocess.check_output(query,cwd=model,text=True).splitlines()
    link=[shlex.split(x) for x in lines if 'VTestDriver__ALL.a' in x and ' -o ' in x]
    if len(link)!=1:raise RuntimeError('Ambiguous model link command')
    cmd=link[0];cmd[cmd.index('SimTSI.o')]=str(out/'preload-SimTSI.cc.o');cmd.insert(1,str(out/'preload-main.cc.o'));cmd[cmd.index('-o')+1]=str(out/'simulator-preload')
    subprocess.run(cmd,cwd=model,check=True);commands.append(cmd)
    inputs=[Path(__file__),Path(__file__).with_name('main.cc'),Path(__file__).with_name('SimTSI.cc'),model/'VTestDriver___024root.h',model/'VTestDriver.h',model/'VTestDriver__ALL.a',model/'VTestDriver.mk',model.parent/'manifest.json',tools/'riscv-tools/lib/libriscv.so',tools/'riscv-tools/lib/libfesvr.a']
    inputs += [gen/x for x in ['testchip_tsi.h','testchip_tsi.cc','testchip_htif.h','testchip_htif.cc']]
    inputs += [model/x for x in cmd if x.endswith('.o') and not Path(x).is_absolute()]
    proof={'schema':'iris.rtl_loader_build.v1','commands':commands,'query_argv':query,'query_cwd':str(model),'input_sha256':{str(x):sha(x) for x in inputs},'binary':str(out/'simulator-preload'),'binary_sha256':sha(out/'simulator-preload'),'rtl_design_changed':False,'explicit_native_ram_preload':True,'full_rtl_certified':False,'timing_calibrated':False,'loaded_fpga_image_association_verified':False}
    (out/'loader-build.json').write_text(json.dumps(proof,indent=2)+'\n');print(out/'loader-build.json')

if __name__=='__main__':main()
