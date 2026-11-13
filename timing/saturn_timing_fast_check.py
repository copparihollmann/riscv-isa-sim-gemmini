#!/usr/bin/env python3
"""Qualify the numeric substitution with the frozen independent cell/array corpora."""
import argparse,hashlib,json,os,shutil,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def archived(receipt,path):
 j=json.loads((receipt/'results.json').read_text());digest=j['input_sha256'][str(path)];f=receipt/'inputs'/digest;assert sha(f)==digest;return f
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();candidate=a.candidate.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);native=json.loads((candidate/'build.json').read_text());assert sha(candidate/'sdk/saturn-timing')==native['native_sha256'];numeric=candidate/'numeric';rtl=candidate/'source/compute/rtl';tool=Path('/scratch/eygao/iris-cy/.conda-env');env=dict(os.environ,VERILATOR_ROOT=str(tool/'share/verilator'));reports=[];inputs=[Path(__file__),candidate/'build.json',rtl/'OuterProductCell.sv',numeric/'saturn_timing_fast_numeric.cpp',numeric/'iris_fp8.hpp',numeric/'libsoftfloat.a',tool/'bin/perl',tool/'bin/verilator',tool/'bin/verilator_bin',Path('/usr/bin/g++')]
 for kind in['cell','array','timing-mutant']:
  folder=out/kind;folder.mkdir();cell=kind!='array';old=R/'build'/('opu-cell-rtl-proof-v2'if cell else'opu-array-rtl-proof-v2-pipelined');frozen=json.loads((old/'results.json').read_text());top='OuterProductCell'if cell else'OuterProductUnit';prefix='VOuterCell'if cell else'VOuterArray';src=R/'hardware'/('opu_cell'if cell else'opu_array')/'driver.cc';driver=folder/'driver.cc';shutil.copy2(archived(old,src),driver);inputs.extend([old/'results.json',archived(old,src)]);sources=[rtl/(top+'.sv')]
  if cell:
   header=archived(old,R/'spike/fp8_cases.hpp');shutil.copy2(header,folder/'fp8_cases.hpp');inputs.append(header);corpus=old/'fp8-exhaustive.bin'
  else:
   binding=archived(old,old/'port_bindings.inc');shutil.copy2(binding,folder/'port_bindings.inc');inputs.append(binding);corpus=old/'fp8-cases.txt'
  inputs.append(corpus);shutil.copy2(corpus,folder/corpus.name)
  if kind=='timing-mutant':
   text=(rtl/'OuterProductCell.sv').read_text();assert text.count('wire _fma_io_validout=fast_valid_stage1;')==1;(folder/'OuterProductCell.sv').write_text(text.replace('wire _fma_io_validout=fast_valid_stage1;','wire _fma_io_validout=fast_valid_stage0;'));sources=[folder/'OuterProductCell.sv']
  model=folder/'model';common='-O3 -std=c++20 -I'+str(folder)+' -I'+str(numeric)+' -I'+str(numeric/'softfloat');command=[str(tool/'bin/perl'),str(tool/'bin/verilator'),'--cc','--exe','--build','-j','4','--top-module',top,'--prefix',prefix,'-O3','-Wno-fatal','--Mdir',str(model),'-I'+str(rtl),'-y',str(rtl),'+libext+.sv+.v','-CFLAGS',common,'-LDFLAGS',str(numeric/'libsoftfloat.a'),'-MAKEFLAGS','CXX=/usr/bin/g++ LINK=/usr/bin/g++ AR=ar RANLIB=ranlib',*map(str,sources),str(driver),str(numeric/'saturn_timing_fast_numeric.cpp')];start=time.monotonic()
  with(folder/'build.log').open('w')as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,env=env,check=True,timeout=300)
  command_run=[str(model/prefix),str(folder/corpus.name)];runstart=time.monotonic();q=subprocess.run(command_run,capture_output=True,text=True,timeout=120);seconds=time.monotonic()-runstart;(folder/'stdout').write_text(q.stdout);(folder/'stderr').write_text(q.stderr)
  if kind=='timing-mutant':
   if q.returncode==0 or 'FP8'not in q.stderr:raise ValueError('Independent cell checker missed numeric-pipeline mutation')
   reports.append({'kind':kind,'build_argv':command,'argv':command_run,'exit_status':q.returncode,'diagnostic':q.stderr,'native_sha256':sha(model/prefix)});continue
  if q.returncode:raise ValueError('Independent numeric oracle mismatch '+kind+' '+q.stderr)
  result=json.loads(q.stdout)
  if result!=frozen['checks']:raise ValueError('Oracle coverage changed '+kind)
  negatives=[]
  for name in(['wrong-golden.bin','truncated-record.bin']if cell else['wrong-golden.txt','truncated.txt']):
   oldpath=old/name;assert sha(oldpath)==frozen['artifact_sha256'][name];shutil.copy2(oldpath,folder/name);bad=subprocess.run([str(model/prefix),str(folder/name)],capture_output=True,text=True,timeout=120);(folder/(name+'.stderr')).write_text(bad.stderr)
   if not bad.returncode:raise ValueError('Independent corpus corruption accepted')
   negatives.append({'name':name,'exit_status':bad.returncode,'diagnostic':bad.stderr});inputs.append(oldpath)
  reports.append({'kind':kind,'checks':result,'build_argv':command,'argv':command_run,'exit_status':q.returncode,'host_run_seconds':seconds,'host_build_and_run_seconds':time.monotonic()-start,'native_sha256':sha(model/prefix),'negative_controls':negatives})
 report={'schema':'iris.saturn_numeric_substitution_independent_proof.v1','pass':True,'candidate_source_identity':native['source_identity'],'runs':reports,'input_sha256':{str(p):sha(p)for p in inputs},'pure_numeric_cone_only':True,'source_control_state_preserved':True,'hardware_contacted':False,'whole_SoC_or_2percent_certified':False};report['artifact_sha256']={str(p.relative_to(out)):sha(p)for p in out.rglob('*')if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'checks':[r.get('checks',r.get('diagnostic'))for r in reports],'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
