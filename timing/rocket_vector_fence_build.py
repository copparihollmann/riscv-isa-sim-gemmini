#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,os,re,shutil,subprocess
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 o=R/'build/rocket-vector-fence-source-v2';o.mkdir(exist_ok=False);g=R/'build/rtl-verilator/gen-collateral';todo=['Rocket'];seen=set()
 while todo:
  name=todo.pop()
  if name in seen:continue
  seen.add(name);p=g/(name+'.sv');s=p.read_text();shutil.copy2(p,o/p.name)
  for child in re.findall(r'\b(\w+)\s+\w+\s*\(',s):
   if(g/(child+'.sv')).exists()and child not in seen:todo.append(child)
 extra=next(g.rglob('plusarg_reader.v'),None)
 if extra is None:extra=R/'build/rtl-verilator/inline/plusarg_reader.v'
 cmd=['/scratch/eygao/iris-cy/.conda-env/bin/perl','/scratch/eygao/iris-cy/.conda-env/bin/verilator','--cc','--build','-j','4','--top-module','Rocket','--prefix','VRocketFence','--assert','--public-flat-rw','-Wno-fatal','--x-initial','unique','--x-assign','unique','--Mdir',str(o/'obj'),'+define+RANDOMIZE_MEM_INIT','+define+RANDOMIZE_REG_INIT',*[str(o/(n+'.sv'))for n in sorted(seen)],str(extra),'-MAKEFLAGS','CXX=/usr/bin/g++ LINK=/usr/bin/g++ AR=/usr/bin/ar RANLIB=/usr/bin/ranlib OPT_FAST=-O3 OPT_SLOW=-O3']
 with(o/'build.stdout').open('w')as so,(o/'build.stderr').open('w')as se:r=subprocess.run(cmd,stdout=so,stderr=se,env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']))
 if r.returncode:raise ValueError('Rocketreferencebuild failed')
 rep=dict(schema='iris.rocket_vector_fence_source.v1',status='built',argv=cmd,modules=sorted(seen),input_sha256={str(p):sha(p)for p in[Path(__file__),extra,*[g/(n+'.sv')for n in sorted(seen)],Path('/usr/bin/g++').resolve()]},hardware_contacted=False);(o/'build.json').write_text(json.dumps(rep,indent=2)+'\n');print(len(seen),sha(o/'build.json'))
if __name__=='__main__':main()
