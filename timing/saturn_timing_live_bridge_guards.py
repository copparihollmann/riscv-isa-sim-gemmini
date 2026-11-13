#!/usr/bin/env python3
"""Constructor/foreign-context/phase/unknown-input/capability native guards."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--bridge',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();bridge=a.bridge.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);source=R/'timing/saturn_timing_live_bridge_guards.cpp';shutil.copy2(source,out/source.name);shutil.copy2(Path(__file__),out/'runner.py');cmd=['/usr/bin/g++','-O3','-std=c++20','-pthread','-I'+str(bridge/'sdk'),'-I/scratch/eygao/iris-cy/.conda-env/share/verilator/include',str(out/source.name),str(bridge/'sdk/libiris_saturn_live_bridge.a'),'-latomic','-lz','-o',str(out/'guards')]
 with(out/'build.log').open('w')as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
 run=subprocess.run([str(out/'guards')],capture_output=True,text=True,timeout=60);(out/'stdout').write_text(run.stdout);(out/'stderr').write_text(run.stderr);result={'schema':'iris.saturn_live_bridge_guards.v1','argv':cmd,'exit_status':run.returncode,'input_sha256':{str(p):sha(p)for p in[Path(__file__),source,bridge/'build.json',bridge/'sdk/libiris_saturn_live_bridge.a',Path('/usr/bin/g++')]},'binary_sha256':sha(out/'guards'),'result':json.loads(run.stdout)if run.returncode==0 else None,'hardware_contacted':False};(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'report_sha256':sha(out/'report.json'),'result':result['result']}))
 if run.returncode:raise SystemExit(1)
if __name__=='__main__':main()
