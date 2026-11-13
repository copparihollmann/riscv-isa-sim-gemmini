#!/usr/bin/env python3
import argparse,hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);sdk=R/'build/saturn-timing-sdk-v1';source=R/'timing/saturn_timing_bench.cpp';command=['/usr/bin/g++','-O3','-std=c++20','-I'+str(sdk/'sdk'),str(source),str(sdk/'sdk/libiris_saturn_timing.a'),'-pthread','-latomic','-o',str(out/'benchmark')]
 with(out/'build.log').open('w')as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 report={'schema':'iris.saturn_runtime_active_benchmark_build.v1','argv':command,'input_sha256':{str(p):sha(p)for p in[Path(__file__),source,sdk/'sdk/saturn_timing.hpp',sdk/'sdk/libiris_saturn_timing.a',sdk/'build.json',Path('/usr/bin/g++')]},'native_sha256':sha(out/'benchmark'),'hardware_contacted':False};(out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'native_sha256':report['native_sha256']}))
if __name__=='__main__':main()
