#!/usr/bin/env python3
"""Build an isolated source-unit/live-ownership bridge; never edits native Spike."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--sdk',type=Path,required=True);p.add_argument('--ownership-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();sdk=a.sdk.resolve();ownership=a.ownership_build.resolve();out.mkdir(parents=True,exist_ok=False);(out/'sdk').mkdir();shutil.copy2(Path(__file__),out/'builder.py')
 sources=[]
 for name in ['saturn_timing_ownership.hpp','saturn_timing_ownership.cpp','saturn_ownership_source_config.hpp']:
  shutil.copy2(ownership/name,out/name);sources.append(out/name)
 for name in ['saturn_timing_live_bridge.hpp','saturn_timing_live_bridge.cpp']:
  shutil.copy2(R/'timing'/name,out/name);sources.append(out/name)
 for name in ['saturn_timing.hpp','saturn_timing_ownership.hpp','saturn_timing_live_bridge.hpp']:
  shutil.copy2((sdk/'sdk'/name if name=='saturn_timing.hpp'else out/name),out/'sdk'/name)
 commands=[]
 with(out/'build.log').open('w')as log:
  for stem in ['saturn_timing_ownership','saturn_timing_live_bridge']:
   cmd=['/usr/bin/g++','-O3','-std=c++20','-pthread','-I'+str(out),'-I'+str(sdk/'sdk'),'-c',str(out/(stem+'.cpp')),'-o',str(out/(stem+'.o'))];commands.append(cmd);subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
  archive=out/'sdk/libiris_saturn_live_bridge.a';script='CREATE '+str(archive)+'\nADDLIB '+str(sdk/'sdk/libiris_saturn_timing.a')+'\nADDMOD '+str(out/'saturn_timing_ownership.o')+'\nADDMOD '+str(out/'saturn_timing_live_bridge.o')+'\nSAVE\nEND\n';(out/'archive.mri').write_text(script);subprocess.run(['/usr/bin/ar','-M'],input=script,text=True,stdout=log,stderr=subprocess.STDOUT,check=True)
 result={'schema':'iris.saturn_live_bridge_build.v1','argv':commands,'input_sha256':{str(x):sha(x)for x in [Path(__file__),sdk/'build.json',sdk/'sdk/libiris_saturn_timing.a',ownership/'build.json',*sources,Path('/usr/bin/g++'),Path('/usr/bin/ar')]},'library_sha256':sha(archive),'source_RTL_objects_modified':False,'native_Spike_edited':False,'guest_functional_execution':False,'hardware_contacted':False};(out/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'library_sha256':result['library_sha256']}))
if __name__=='__main__':main()
