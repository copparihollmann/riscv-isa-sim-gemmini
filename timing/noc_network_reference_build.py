#!/usr/bin/env python3
"""Build a separate whole-SoC reference exposing physical NoC data ports read-only."""
import argparse,hashlib,json,os,shutil,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];CAP=R/'build/rtl-memory-return-path-v1-final'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=R/'build/noc-network-reference-v1');p.add_argument('--jobs',type=int,default=24);a=p.parse_args();out=a.output.resolve()
 if out.exists():raise ValueError('Fresh reference build output required')
 out.mkdir();src=out/'rtl';src.mkdir();original=R/'build/rtl-verilator';manifest=json.loads((original/'manifest.json').read_text());mapping={};sources=[]
 for line in (original/'sim_files.f').read_text().splitlines():
  file=Path(line);relative=file.relative_to(R);frozen=CAP/relative;file=frozen if frozen.exists()else file
  expected=manifest['sim_source_sha256'][str(R/relative)];assert sha(file)==expected,('Changed saved whole-RTL input',str(file));target=src/file.name;assert not target.exists();shutil.copyfile(file,target);mapping[str(file)]=expected;sources.append(target)
 # Runtime headers are included by listed DPI C++ sources but not file-list
 # entries. Snapshot the frozen/verified original support headers as well.
 for pattern in ['*.h','*.vh']:
  for file in (original/'gen-collateral').glob(pattern):
   target=src/file.name
   if not target.exists():shutil.copyfile(file,target);mapping[str(file)]=sha(file)
 config=out/'boundary-readonly.vlt';extraction=json.loads((R/'build/noc-network-source-v1/extraction.json').read_text());config.write_text('`verilator_config\n'+''.join('public_flat_rd -module "DigitalTop" -var "'+x['name']+'"\n'for x in extraction['physical_ports']));filelist=out/'sim_files.f';filelist.write_text('\n'.join(map(str,sources))+'\n');model=out/'model';command=manifest['verilator_argv'][:]
 replacements={str(original/'sim_files.f'):str(filelist),str(original/'gen-collateral'):str(src),str(original/'model'):str(model),str(original/'simulator-IrisConfig'):str(out/'simulator-generated-main')}
 for n,arg in enumerate(command):
  for old,new in replacements.items():arg=arg.replace(old,new)
  command[n]=arg
 command.insert(command.index('-f'),str(config));started=time.monotonic()
 with (out/'verilate.log').open('w')as log:q=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
 (out/'verilate-command.json').write_text(json.dumps(command,indent=2)+'\n')
 if q.returncode:raise RuntimeError('Reference Verilation failed; see verilate.log')
 compile=['make','-j'+str(a.jobs),'VM_PARALLEL_BUILDS=1','CXX=g++','LINK=/scratch/eygao/iris-cy/.conda-env/bin/x86_64-conda-linux-gnu-c++','AR=ar','RANLIB=ranlib','PERL=/scratch/eygao/iris-cy/.conda-env/bin/perl','-f','VTestDriver.mk','VTestDriver__ALL.a']
 (out/'compile-command.json').write_text(json.dumps(compile,indent=2)+'\n')
 with(out/'compile.log').open('w')as log:q=subprocess.run(compile,cwd=model,stdout=log,stderr=subprocess.STDOUT)
 report={'schema':'iris.whole_rtl_noc_physical_visibility.v1','verilate_argv':command,'compile_argv':compile,'exit_status':q.returncode,'host_seconds':time.monotonic()-started,'source_sha256':mapping,'public_control_sha256':sha(config),'extraction_sha256':sha(R/'build/noc-network-source-v1/extraction.json'),'no_RTL_logic_changes':True,'clock_not_exposed_by_config':True,'only_physical_data_ports_readonly':True,'hardware_contacted':False}
 if not q.returncode:report['model_archive_sha256']=sha(model/'VTestDriver__ALL.a')
 (out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'exit_status':q.returncode,'host_seconds':report['host_seconds'],'build_sha256':sha(out/'build.json')}))
 if q.returncode:raise SystemExit(1)
if __name__=='__main__':main()
