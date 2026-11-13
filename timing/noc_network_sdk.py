#!/usr/bin/env python3
"""Package the complete NoC Pimpl API and link its direct stepping benchmark."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--model',type=Path,default=R/'build/noc-network-native-v3');p.add_argument('--output',type=Path,default=R/'build/noc-network-sdk-v1');a=p.parse_args();b=a.model.resolve();o=a.output.resolve()
 if o.exists():raise ValueError('Fresh SDK output required')
 o.mkdir();sdk=o/'sdk';sdk.mkdir();c=Path('/scratch/eygao/iris-cy/.conda-env/bin/x86_64-conda-linux-gnu-c++');ar=c.with_name('x86_64-conda-linux-gnu-ar');objects=sorted((b/'model').glob('VNoCNetwork*.o'))+[b/'model/noc_network.o']+sorted((b/'model').glob('verilated*.o'))
 for name in ['noc_network.hpp','noc_network_schema.hpp']:shutil.copyfile(R/'timing'/name,sdk/name)
 commands=[[str(ar),'rcs',str(sdk/'libiris_noc.a')]+list(map(str,objects)),[str(c),'-O3','-std=c++20','-I'+str(sdk),str(R/'timing/noc_network_bench.cpp'),str(sdk/'libiris_noc.a'),'-pthread','-latomic','-o',str(o/'benchmark')]]
 with(o/'build.log').open('w')as log:
  for command in commands:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 inputs=objects+[Path(__file__),R/'timing/noc_network_bench.cpp',sdk/'noc_network.hpp',sdk/'noc_network_schema.hpp',b/'build.json',c,ar];report={'schema':'iris.complete_noc_sdk.v1','argv':commands,'input_sha256':{str(x):sha(x)for x in inputs},'library_sha256':sha(sdk/'libiris_noc.a'),'benchmark_sha256':sha(o/'benchmark'),'native_sha256':sha(b/'noc-network'),'source_identity':json.loads((b/'build.json').read_text())['source_identity'],'public_flat_state_exposed':False,'whole_NoC_external_boundary':'Actual endpoint TL, memory/cache/serial/tile CDCs external','inprocess_benchmark_excludes':['input parsing','output digest','text IO'],'idle_skipping':False,'hardware_contacted':False};(o/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'library_sha256':report['library_sha256'],'benchmark_sha256':report['benchmark_sha256']}))
if __name__=='__main__':main()
