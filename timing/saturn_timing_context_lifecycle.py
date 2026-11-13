#!/usr/bin/env python3
"""Constructor/error/destructor/move ownership guards for both context SDKs."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);source=out/'test.cpp';shutil.copy2(R/'timing/saturn_timing_context_lifecycle.cpp',source);include=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include');inputs=[Path(__file__),source,R/'timing/saturn_timing_context_lifecycle.cpp',Path('/usr/bin/g++'),include/'verilated.h'];results=[]
 for variant in['fast','reference']:
  sdk=R/'build'/('saturn-timing-context-'+variant+'-v1');command=['/usr/bin/g++','-O3','-std=c++20','-I'+str(sdk/'sdk'),'-I'+str(include),'-I'+str(include/'vltstd'),str(source),str(sdk/'sdk/libiris_saturn_timing.a'),'-pthread','-latomic','-o',str(out/variant)]
  with(out/(variant+'.build.log')).open('w')as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
  q=subprocess.run([str(out/variant)],capture_output=True,text=True,timeout=30);(out/(variant+'.stdout')).write_text(q.stdout);(out/(variant+'.stderr')).write_text(q.stderr)
  if q.returncode:raise ValueError('Context lifecycle failed '+variant+' '+q.stderr)
  results.append({'variant':variant,'argv':command,'native_sha256':sha(out/variant),'result':json.loads(q.stdout)});inputs.extend([sdk/'build.json',sdk/'sdk/saturn_timing.hpp',sdk/'sdk/libiris_saturn_timing.a'])
 report={'schema':'iris.saturn_own_context_lifecycle_proof.v1','pass':True,'runs':results,'input_sha256':{str(p):sha(p)for p in inputs},'artifact_sha256':{str(p.relative_to(out)):sha(p)for p in out.iterdir()if p.is_file()},'source_RTL_or_model_objects_modified':False,'hardware_contacted':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'runs':results,'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
