#!/usr/bin/env python3
"""Explicit ownership getter/constructor/move/destructor foreign-context gate."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--sdk',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);sdk=a.sdk.resolve();source=out/'lifecycle.cpp';shutil.copy2(R/'timing/saturn_timing_ownership_lifecycle.cpp',source);command=['/usr/bin/g++','-O3','-std=c++20','-pthread','-I'+str(sdk/'sdk'),'-I/scratch/eygao/iris-cy/.conda-env/share/verilator/include',str(source),str(sdk/'sdk/libiris_saturn_timing.a'),'-latomic','-o',str(out/'lifecycle')]
 with(out/'build.log').open('w')as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 q=subprocess.run([str(out/'lifecycle')],capture_output=True,text=True,timeout=30);(out/'stdout').write_text(q.stdout);(out/'stderr').write_text(q.stderr)
 if q.returncode:raise ValueError('Ownership lifecycle failure '+q.stderr)
 inputs=[Path(__file__),R/'timing/saturn_timing_ownership_lifecycle.cpp',sdk/'build.json',sdk/'sdk/libiris_saturn_timing.a',source,Path('/usr/bin/g++')];report={'schema':'iris.saturn_ownership_lifecycle.v1','pass':True,'argv':command,'result':json.loads(q.stdout),'input_sha256':{str(p):sha(p)for p in inputs},'binary_sha256':sha(out/'lifecycle'),'no_RTL_state_initialization_claim':True,'hardware_contacted':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'report_sha256':sha(out/'report.json'),'result':report['result']}))
if __name__=='__main__':main()
