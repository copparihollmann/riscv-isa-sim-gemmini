#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,os,re,shutil,subprocess
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 out=R/'build/rvv-store-compactor-source-v1';out.mkdir(exist_ok=False);gen=R/'build/rtl-verilator/gen-collateral';commands=[];paths=[Path(__file__)]
 for kind,top,prefix in [('compute','Compactor_4','VComputeCompactor'),('rocket','Compactor_14','VRocketCompactor')]:
  d=out/kind;d.mkdir();width=16 if kind=='compute'else 32;closure=set();todo=[top]
  while todo:
   name=todo.pop()
   if name in closure:continue
   closure.add(name);src=gen/(name+'.sv');text=src.read_text();shutil.copy2(src,d/src.name);paths.append(src)
   for child in re.findall(r'\b(\w+)\s+\w+\s*\(',text):
    if(gen/(child+'.sv')).exists()and child not in closure:todo.append(child)
  text=(gen/(top+'.sv')).read_text();ports=re.findall(r'^\s*(input|output)\s*(?:\[([^]]+)\])?\s*(\w+)\s*[,)]',text,re.M);connections=[]
  mapping={'clock':'clock','reset':'reset','io_push_valid':'push_valid','io_push_ready':'push_ready','io_pop_valid':'pop_valid','io_pop_ready':'pop_ready','io_push_bits_head':"'0",'io_pop_bits_head':"'0",'io_push_bits_tail':f'push_bytes[{3 if width==16 else 4}:0]','io_pop_bits_tail':f'pop_bytes[{3 if width==16 else 4}:0]'}
  for direction,bits,name in ports:connections.append('.'+name+'('+mapping.get(name,"'0"if direction=='input'else'')+')')
  wrap=d/'IrisCompactorControl.sv';wrap.write_text('module IrisCompactorControl(input clock,reset,push_valid,pop_valid,input [5:0]push_bytes,pop_bytes,output push_ready,pop_ready);\n'+top+' cut('+',\n'.join(connections)+');\nendmodule\n');paths.append(wrap)
  cmd=['/scratch/eygao/iris-cy/.conda-env/bin/perl','/scratch/eygao/iris-cy/.conda-env/bin/verilator','--cc','--build','-j','4','--top-module','IrisCompactorControl','--prefix',prefix,'--assert','-Wno-fatal','--x-initial','unique','--x-assign','unique','--Mdir',str(d/'obj'),'+define+RANDOMIZE_MEM_INIT','+define+RANDOMIZE_REG_INIT',str(wrap),*[str(d/(n+'.sv'))for n in sorted(closure)],'-MAKEFLAGS','CXX=/usr/bin/g++ LINK=/usr/bin/g++ AR=/usr/bin/ar RANLIB=/usr/bin/ranlib OPT_FAST=-O3 OPT_SLOW=-O3'];commands.append(cmd)
  with(d/'stdout').open('w')as so,(d/'stderr').open('w')as se:r=subprocess.run(cmd,stdout=so,stderr=se,env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']))
  if r.returncode:raise ValueError('Configuredcompactorsourcebuild failed '+kind)
 paths +=[Path('/usr/bin/g++').resolve(),Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator').resolve()];rep=dict(schema='iris.configured_store_compactor_source.v1',status='built',argv=commands,control_only=True,numeric_outputs_qualified=False,input_sha256={str(p):sha(p)for p in paths});(out/'build.json').write_text(json.dumps(rep,indent=2)+'\n');print(sha(out/'build.json'))
if __name__=='__main__':main()
