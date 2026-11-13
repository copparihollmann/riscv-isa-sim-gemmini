#!/usr/bin/env python3
"""Compile one exact Saturn runtime cut; datapath duplication is reference scope."""
import argparse,hashlib,json,os,shutil,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--jobs',type=int,default=8);a=p.parse_args();source=a.source.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);profile=json.loads((source/'ports.json').read_text());shutil.copy2(source/'ports.json',out/'ports.json');shutil.copytree(source/'rtl',out/'rtl');prefix='VSaturnCompute'if profile['profile']=='compute'else'VSaturnRocket';tool=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator');model=out/'model'
 command=[str(tool.with_name('perl')),str(tool),'--cc','-O3','--top-module',profile['top_module'],'--prefix',prefix,'--assert','-Wno-fatal','--x-initial','unique','--x-assign','unique','--Mdir',str(model),'-I'+str(out/'rtl'),'-y',str(out/'rtl'),'+libext+.sv+.v','+define+RANDOMIZE_MEM_INIT','+define+RANDOMIZE_REG_INIT','+define+RANDOMIZE_GARBAGE_ASSIGN','+define+RANDOMIZE_INVALID_ASSIGN','-CFLAGS','-O3 -std=c++20','-MAKEFLAGS','OPT_FAST=-O3 OPT_SLOW=-O3',str(out/'rtl'/(profile['top_module']+'.sv'))];compile=['make','-j'+str(a.jobs),'-f',prefix+'.mk','CXX=g++','AR=ar','RANLIB=ranlib','PERL='+str(tool.with_name('perl')),prefix+'__ALL.a'];start=time.monotonic();env=dict(os.environ,PATH=str(tool.parent)+os.pathsep+os.environ['PATH']);(out/'verilate-command.json').write_text(json.dumps(command,indent=2)+'\n');(out/'compile-command.json').write_text(json.dumps(compile,indent=2)+'\n')
 with(out/'verilate.log').open('w')as log:q=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,env=env)
 if q.returncode:raise RuntimeError('Saturn Verilation failed; preserve log')
 with(out/'compile.log').open('w')as log:q=subprocess.run(compile,cwd=model,stdout=log,stderr=subprocess.STDOUT,env=env)
 inputs=[Path(__file__),source/'ports.json',source.parent/'extraction.json',tool,tool.with_name('verilator_bin'),Path('/usr/bin/g++')];report={'schema':'iris.saturn_runtime_reference_native.v1','profile':profile['profile'],'prefix':prefix,'verilate_argv':command,'compile_argv':compile,'exit_status':q.returncode,'host_seconds':time.monotonic()-start,'input_sha256':{str(p):sha(p)for p in inputs},'source_sha256':{str(p):sha(p)for p in(out/'rtl').iterdir()},'source_fir_sha256':profile['source_fir_sha256'],'source_clock_advanced_by_external_API_only':True,'datapath_work_included':True,'production_performance_architecture':False,'hardware_contacted':False,'timing_certified':False}
 if not q.returncode:report['model_archive_sha256']=sha(model/(prefix+'__ALL.a'))
 (out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'profile':profile['profile'],'exit_status':q.returncode,'host_seconds':report['host_seconds'],'archive_sha256':report.get('model_archive_sha256')}))
 if q.returncode:raise SystemExit(1)
if __name__=='__main__':main()
