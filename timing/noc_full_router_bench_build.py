#!/usr/bin/env python3
"""Package the full-router static API and build the no-text-I/O benchmark."""
import argparse,hashlib,json,subprocess,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--model',type=Path,default=R/'build/noc-full-router-v2');p.add_argument('--output',type=Path,default=R/'build/noc-full-router-benchmark-v2');a=p.parse_args();b=a.model.resolve();o=a.output.resolve()
 if o.exists():raise ValueError('Refuse to overwrite benchmark/API package')
 o.mkdir();c=Path('/scratch/eygao/iris-cy/.conda-env/bin/x86_64-conda-linux-gnu-c++');ar=c.with_name('x86_64-conda-linux-gnu-ar');sdk=o/'sdk';sdk.mkdir();shutil.copyfile(R/'timing/noc_full_router.hpp',sdk/'noc_full_router.hpp')
 objects=sorted((b/'model').glob('VNode5*.o'))+[b/'model/noc_full_router.o']+sorted((b/'model').glob('verilated*.o'));archive=sdk/'libiris_node5.a';commands=[[str(ar),'rcs',str(archive)]+[str(x) for x in objects]]
 commands.append([str(c),'-O3','-std=c++20','-I'+str(sdk),str(R/'timing/noc_full_router_bench.cpp'),str(archive),'-pthread','-lpthread','-latomic','-o',str(o/'benchmark')])
 with (o/'build.log').open('w') as log:
  for argv in commands:subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,check=True)
 sources=objects+[c,ar,R/'timing/noc_full_router_bench.cpp',Path(__file__),b/'build.json',sdk/'noc_full_router.hpp']
 report={'argv':commands,'input_sha256':{str(x):sha(x) for x in sources},'binary_sha256':sha(o/'benchmark'),'archive_sha256':sha(archive),'model_native_sha256':sha(b/'noc-full-router'),'source_identity':json.loads((b/'build.json').read_text())['source_identity'],'timed_scope':'step()+output vector stores; parsing, digest and text I/O excluded','required_link_flags':['-pthread','-latomic'],'public_flat_state_exposure':False,'idle_skipping':False,'simulation_scope':'One complete configured Router_5, not SoC MIPS'}
 (o/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
