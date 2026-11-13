#!/usr/bin/env python3
"""Recoverable same-edge API and concurrent FP-environment isolation checks."""
import argparse,hashlib,json,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();candidate=a.candidate.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);sdk=candidate/'sdk/sdk';numeric=candidate/'numeric';source=R/'build/saturn-timing-component-v1-final/timing/saturn_timing_guards.cpp';scope=R/'timing/saturn_timing_fast_numeric_scope.cpp';common=['/usr/bin/g++','-O3','-std=c++20','-pthread'];commands=[common+['-I'+str(sdk),str(source),str(sdk/'libiris_saturn_timing.a'),'-latomic','-o',str(out/'phase-guards')],common+['-I'+str(numeric),'-I'+str(numeric/'softfloat'),str(scope),str(numeric/'saturn_timing_fast_numeric.cpp'),str(numeric/'libsoftfloat.a'),'-o',str(out/'numeric-scope')]];inputs=[Path(__file__),source,scope,sdk/'saturn_timing.hpp',sdk/'libiris_saturn_timing.a',numeric/'saturn_timing_fast_numeric.cpp',numeric/'libsoftfloat.a',candidate/'build.json',Path('/usr/bin/g++')];results=[]
 with(out/'build.log').open('w')as log:
  for command in commands:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 for profile in['compute','rocket']:
  ports=R/'build/saturn-timing-component-v1-final/build/saturn-timing-guards-v2'/(profile+'.input');inputs.append(ports);command=[str(out/'phase-guards'),profile,str(ports)]
  with(out/(profile+'.stdout')).open('w')as stdout,(out/(profile+'.stderr')).open('w')as stderr:q=subprocess.run(command,stdout=stdout,stderr=stderr,timeout=90)
  if q.returncode:raise ValueError('Fast phase guard failed '+profile)
  result=next(json.loads(x.split(' ',1)[1])for x in(out/(profile+'.stderr')).read_text().splitlines()if x.startswith('SATURN_GUARDS '));results.append({'profile':profile,'argv':command,**result})
 q=subprocess.run([str(out/'numeric-scope')],capture_output=True,text=True,timeout=30);(out/'numeric-scope.stdout').write_text(q.stdout);(out/'numeric-scope.stderr').write_text(q.stderr)
 if q.returncode:raise ValueError('FP context isolation failed')
 report={'schema':'iris.saturn_numeric_substitution_guard.v1','pass':True,'phase_checks':results,'numeric_context':json.loads(q.stdout),'argv':commands,'input_sha256':{str(p):sha(p)for p in inputs},'artifact_sha256':{str(p.relative_to(out)):sha(p)for p in out.iterdir()if p.is_file()},'hardware_contacted':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'phase_checks':results,'numeric_context':report['numeric_context'],'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
