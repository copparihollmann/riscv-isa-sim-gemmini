#!/usr/bin/env python3
"""Compile exact saved source StoreSequencer peers; never edit their RTL."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 out=R/'build/rvv-store-sequence-source-v1';out.mkdir(exist_ok=False);commands=[];inputs=[Path(__file__).resolve()]
 for kind,top,prefix in [('compute','StoreSequencer','VComputeStoreSeq'),('rocket','StoreSequencer_2','VRocketStoreSeq')]:
  d=out/kind;d.mkdir();src=R/'build/rtl-verilator/gen-collateral'/(top+'.sv');shutil.copy2(src,d/src.name);inputs.append(src);cmd=['/scratch/eygao/iris-cy/.conda-env/bin/perl','/scratch/eygao/iris-cy/.conda-env/bin/verilator','--cc','--build','-j','4','--top-module',top,'--prefix',prefix,'--assert','-Wno-fatal','--x-initial','unique','--x-assign','unique','--Mdir',str(d/'obj'),'+define+RANDOMIZE_MEM_INIT','+define+RANDOMIZE_REG_INIT',str(d/src.name),'-MAKEFLAGS','CXX=/usr/bin/g++ LINK=/usr/bin/g++ AR=/usr/bin/ar RANLIB=/usr/bin/ranlib OPT_FAST=-O3 OPT_SLOW=-O3'];commands.append(cmd)
  with(d/'stdout').open('w')as so,(d/'stderr').open('w')as se:p=subprocess.run(cmd,stdout=so,stderr=se,env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']))
  if p.returncode:raise ValueError('Source compile failed '+kind)
 r=dict(schema='iris.rvv_source_store_sequence_build.v1',pass_=True,argv=commands,source_RTL_modified=False,hardware_contacted=False,input_sha256={str(p):sha(p)for p in inputs});(out/'build.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(pass_=True,report_sha256=sha(out/'build.json'))))
if __name__=='__main__':main()
