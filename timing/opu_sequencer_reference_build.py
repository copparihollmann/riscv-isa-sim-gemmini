#!/usr/bin/env python3
"""Independent whole-SoC reference: read-only OPU sequencer physical data ports."""
import argparse,hashlib,json,shutil,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--jobs',type=int,default=20);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);src=out/'rtl';src.mkdir();original=R/'build/rtl-verilator';frozen=R/'build/noc-network-reference-v1/rtl';manifest=json.loads((original/'manifest.json').read_text());mapping={};sources=[]
 for name in (original/'sim_files.f').read_text().splitlines():
  originalfile=Path(name);file=frozen/originalfile.name;assert sha(file)==manifest['sim_source_sha256'][name];target=src/file.name;shutil.copyfile(file,target);mapping[str(file)]=sha(file);sources.append(target)
 for pattern in ['*.h','*.vh']:
  for file in frozen.glob(pattern):
   target=src/file.name
   if not target.exists():shutil.copyfile(file,target);mapping[str(file)]=sha(file)
 profile=json.loads((R/'build/opu-sequencer-native-v2/ports.json').read_text());ports=sorted({f['port']for fs in profile.values()for f in fs});config=out/'boundary-readonly.vlt';config.write_text('`verilator_config\n'+''.join('public_flat_rd -module "OuterProductSequencer" -var "'+n+'"\n'for n in ports));filelist=out/'sim_files.f';filelist.write_text('\n'.join(map(str,sources))+'\n');model=out/'model';command=manifest['verilator_argv'][:]
 replacements={str(original/'sim_files.f'):str(filelist),str(original/'gen-collateral'):str(src),str(original/'model'):str(model),str(original/'simulator-IrisConfig'):str(out/'simulator-generated-main')}
 for n,arg in enumerate(command):
  for old,new in replacements.items():arg=arg.replace(old,new)
  command[n]=arg
 command.insert(command.index('-f'),str(config));started=time.monotonic();(out/'verilate-command.json').write_text(json.dumps(command,indent=2)+'\n')
 with (out/'verilate.log').open('w')as log:q=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
 if q.returncode:raise RuntimeError('Whole-SoC OPU visibility Verilation failed')
 compile=['make','-j'+str(a.jobs),'VM_PARALLEL_BUILDS=1','CXX=g++','LINK=/scratch/eygao/iris-cy/.conda-env/bin/x86_64-conda-linux-gnu-c++','AR=ar','RANLIB=ranlib','PERL=/scratch/eygao/iris-cy/.conda-env/bin/perl','-f','VTestDriver.mk','VTestDriver__ALL.a'];(out/'compile-command.json').write_text(json.dumps(compile,indent=2)+'\n')
 with(out/'compile.log').open('w')as log:q=subprocess.run(compile,cwd=model,stdout=log,stderr=subprocess.STDOUT)
 report={'schema':'iris.whole_rtl_opu_sequencer_visibility.v1','verilate_argv':command,'compile_argv':compile,'exit_status':q.returncode,'host_seconds':time.monotonic()-started,'source_sha256':mapping,'public_control_sha256':sha(config),'no_RTL_logic_changes':True,'clock_not_exposed_by_config':True,'only_physical_data_ports_readonly':True,'port_profile_sha256':sha(R/'build/opu-sequencer-native-v2/ports.json'),'builder_sha256':sha(__file__),'hardware_contacted':False}
 if not q.returncode:report['model_archive_sha256']=sha(model/'VTestDriver__ALL.a')
 (out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'exit_status':q.returncode,'host_seconds':report['host_seconds'],'build_sha256':sha(out/'build.json')}))
 if q.returncode:raise SystemExit(1)
if __name__=='__main__':main()
