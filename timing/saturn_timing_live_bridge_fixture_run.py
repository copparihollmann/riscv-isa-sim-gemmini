#!/usr/bin/env python3
"""Bounded positive source-ID-wrap proof; not actual guest/CPU execution."""
import argparse,hashlib,json,shutil,subprocess,time
from pathlib import Path
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--fixture',type=Path,required=True);p.add_argument('--rounds',type=int,default=65537);p.add_argument('--seed',type=int,default=17);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copy2(Path(__file__),out/'runner.py');fixture=a.fixture.resolve();rows=[]
 for profile in ['compute','rocket']:
  cmd=[str(fixture/'fixture'),profile,str(a.rounds),str(a.seed)];start=time.monotonic()
  with(out/(profile+'.stdout')).open('w')as stdout,(out/(profile+'.stderr')).open('w')as stderr:r=subprocess.run(cmd,stdout=stdout,stderr=stderr,timeout=600)
  row={'profile':profile,'argv':cmd,'exit_status':r.returncode,'host_seconds':time.monotonic()-start};result_lines=[line for line in(out/(profile+'.stdout')).read_text().splitlines()if line.startswith('RESULT ')];row['result']=json.loads(result_lines[-1][7:])if result_lines else None;rows.append(row)
 report={'schema':'iris.saturn_live_bridge_source_wrap_fixture.v1','runs':rows,'input_sha256':{str(p):sha(p)for p in [Path(__file__),fixture/'build.json',fixture/'fixture']},'actual_CPU_pipeline':False,'actual_guest_ELF_execution':False,'synthetic_EX_boundary_driver':True,'no_RTL_state_injected':True,'hardware_contacted':False};report['artifact_sha256']={p.name:sha(p)for p in out.iterdir()if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'report_sha256':sha(out/'report.json'),'runs':rows}))
 if any(x['exit_status']or x['result']is None for x in rows):raise SystemExit(1)
if __name__=='__main__':main()
