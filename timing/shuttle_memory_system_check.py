#!/usr/bin/env python3
"""Run source-coupled physical-client tests, with explicit source LP fixture."""
import argparse,hashlib,json,shlex,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--system',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--case',choices=['functional','context','guards'],default='functional');a=p.parse_args();out=a.output.resolve()
 if out.exists():raise ValueError('fresh check required')
 out.mkdir();build=json.loads((a.system/'build.json').read_text());assert build['exit_status']==0
 v=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include');lp=R/'build/serial-memory-context-sdk-v2/fased';sdk=lp/'sdk';cpp=R/('timing/shuttle_memory_system_context_check.cpp'if a.case=='context'else'timing/shuttle_memory_system_guards.cpp'if a.case=='guards'else'timing/shuttle_memory_system_check.cpp');includes=[*map(Path,build['required_include_directories']),sdk,v];libs=[*map(Path,build['required_static_libraries_in_link_order']),sdk/'libiris_fased_service.a'];exe=out/'check'
 cmd=['/usr/bin/g++','-O2','-std=c++20','-MD','-MF',str(out/'check.d'),*['-I'+str(x)for x in includes],str(cpp),'-Wl,--start-group',*map(str,libs),'-Wl,--end-group','-pthread','-o',str(exe)];begin=time.monotonic();commands=[cmd]
 with(out/'compile.stdout').open('w')as stdout,(out/'compile.stderr').open('w')as stderr:status=subprocess.run(cmd,stdout=stdout,stderr=stderr).returncode
 if not status:
  cmd=[str(exe)];commands.append(cmd)
  with(out/'check.stdout').open('w')as stdout,(out/'check.stderr').open('w')as stderr:status=subprocess.run(cmd,stdout=stdout,stderr=stderr,timeout=180).returncode
 controls=[]
 if not status and a.case=='functional':
  for mode,expected in [('--wrong-data','Shuttle warmup data wrong'),('--cold-store','IRIS_SHUTTLE_INVALID_REPLAY_COMMAND_UNDEFINED')]:
   cmd=[str(exe),mode];commands.append(cmd);name=mode[2:]
   with(out/(name+'.stdout')).open('w')as stdout,(out/(name+'.stderr')).open('w')as stderr:rc=subprocess.run(cmd,stdout=stdout,stderr=stderr,timeout=60).returncode
   message=(out/(name+'.stderr')).read_text();passed=rc!=0 and expected in message;controls.append({'mode':mode,'exit_status':rc,'required_error':expected,'passed':passed})
   if not passed:status=1
 inputs=[Path(__file__),cpp,a.system/'build.json',lp/'build.json',*libs];deps={Path(x)for x in shlex.split((out/'check.d').read_text().replace('\\\n',' ').split(':',1)[1])}if(out/'check.d').exists()else set()
 report={'schema':'iris.shuttle_memory_system_check.v1','exit_status':status,'case':a.case,'negative_controls':controls,'argv':commands,'input_sha256':{str(p):sha(p)for p in inputs},'compiled_dependency_sha256':{str(p):sha(p)for p in deps if p.is_file()},'host_seconds':time.monotonic()-begin,'fixture_LP_parameters':{'readLatency':30,'writeLatency':30,'readMaxReqs':16,'writeMaxReqs':16},'fixture_scope':'explicit ideal-host functional backing and caller LP parameters; no admitted hardware timing defaults; reset-only diagnostics suppression explicitly selected','hardware_contacted':False,'full_timing_certified':False,'calibration_usable':False}
 if exe.exists():report['executable_sha256']=sha(exe)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'exit_status':status,'host_seconds':report['host_seconds']}));raise SystemExit(status)
if __name__=='__main__':main()
