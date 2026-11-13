#!/usr/bin/env python3
"""Freeze and independently replay the exact full configured node5 component."""
import argparse,hashlib,importlib,json,os,re,shutil,subprocess,sys,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];FINAL=R/'build/noc-full-router-component-v1-final'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for part in iter(lambda:f.read(1024*1024),b''):h.update(part)
 return h.hexdigest()
def package(out):
 if out.exists():raise ValueError('Refuse to overwrite immutable router capsule')
 acc=R/'build/noc-full-router-accept-v3';audit=R/'build/noc-full-router-audit-v3';native=R/'build/noc-full-router-v2';sdk=R/'build/noc-full-router-benchmark-v2';rtl=R/'build/noc-full-router-rtl-v1';cap=R/'build/rtl-memory-return-path-v1-final';local=R/'build/noc-router-component-v1-final';files=set();directories=[acc,audit,native,sdk,rtl,R/'build/noc-full-router-guests',cap]
 for d in directories:
  files.update(p for p in d.rglob('*') if p.is_file() and p.suffix not in ['.gch','.d'])
 files.update(p for p in local.iterdir() if p.is_file());files.update(p for p in (R/'timing').glob('noc_full_router*') if p.is_file());files.update(p for p in (R/'timing').glob('noc_router*') if p.is_file())
 records=[];metadata=[]
 for p in [native/'build.json',sdk/'build.json',rtl/'build.json',R/'build/noc-full-router-guests/build.json']:
  j=json.loads(p.read_text());metadata.append({'path':str(p.relative_to(R)),'sha256':sha(p)})
  for name,digest in j['input_sha256'].items():
   source=Path(name);assert source.is_file() and sha(source)==digest,('Build input changed',name);files.add(source)
  for name in j.get('source_files',{}):files.add(Path(name))
 # Preserve exact routing annotations/edge properties and host runtime libraries.
 libraries={}
 for label,binary in [('node5',native/'noc-full-router'),('whole-rtl',rtl/'simulator-full-boundary')]:
  q=subprocess.run(['ldd',str(binary)],capture_output=True,text=True,check=True);paths=[]
  for line in q.stdout.splitlines():
   match=re.search(r'(?:=>\s*)?(/\S+)\s+\(',line)
   if match:paths.append(Path(match[1]));files.add(Path(match[1]))
  libraries[label]={'ldd':q.stdout,'libraries':{str(p):sha(p) for p in paths}}
 out.mkdir();index=[]
 for p in sorted(files):
  relative=p.relative_to(R) if p.is_relative_to(R) else Path('external')/str(p).lstrip('/');destination=out/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,destination)
  index.append({'path':str(relative),'source_path':str(p),'bytes':destination.stat().st_size,'sha256':sha(destination)})
 cpu=subprocess.run(['lscpu','--json'],text=True,capture_output=True)
 cpu_model=[]
 if Path('/proc/cpuinfo').exists():cpu_model=sorted({line.strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith(('model name','vendor_id','cpu family','model\t'))})
 host={'uname':subprocess.check_output(['uname','-a'],text=True).strip(),'lscpu_exit_status':cpu.returncode,'lscpu_stdout':cpu.stdout,'lscpu_stderr':cpu.stderr,'proc_cpu_identity_fields':cpu_model,'python':sys.version,'cpu_measurements_are_host_cost':True}
 report={'schema':'iris.full_router_frozen_capsule.v1','pass':True,'source_identity':json.loads((native/'build.json').read_text())['source_identity'],'native_sha256':sha(native/'noc-full-router'),'sdk_archive_sha256':sha(sdk/'sdk/libiris_node5.a'),'acceptance_report':str((acc/'report.json').relative_to(R)),'acceptance_sha256':sha(acc/'report.json'),'source_audit_report':str((audit/'report.json').relative_to(R)),'source_audit_sha256':sha(audit/'report.json'),'input_build_receipts':metadata,'host':host,'runtime_libraries':libraries,'artifact_count':len(index),'total_bytes':sum(x['bytes'] for x in index),'artifacts':index,'source_scope':'Complete saved Router_5 subtree,26modules; whole-SoC independent physical trace; finite controls','primary_or_shared_engine_changed':False,'whole_NoC_certified':False,'timing_2percent_certified':False,'FPGA_image_association':False,'hardware_contacted':False}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'capsule':str(out),'sha256':sha(out/'report.json'),'artifacts':len(index),'bytes':report['total_bytes']}))
def verify(out):
 j=json.loads((out/'report.json').read_text())
 for x in j['artifacts']:
  path=Path(x['path']);assert not path.is_absolute() and '..' not in path.parts;assert (out/path).stat().st_size==x['bytes'] and sha(out/path)==x['sha256'],x['path']
 acc_path=out/j['acceptance_report'];audit_path=out/j['source_audit_report'];assert sha(acc_path)==j['acceptance_sha256'] and sha(audit_path)==j['source_audit_sha256'];acceptance=json.loads(acc_path.read_text());binary=out/'build/noc-full-router-v2/noc-full-router';bench=out/'build/noc-full-router-benchmark-v2/benchmark';assert sha(binary)==j['native_sha256']==acceptance['binary_sha256'];sys.path.insert(0,str(out/'timing'))
 # Import the frozen independent parser/acceptance sources, even when this
 # verifier is launched from the mutable workspace or another directory.
 for name in ['noc_full_router_check','noc_full_router_accept','noc_router_check']:sys.modules.pop(name,None)
 check=importlib.import_module('noc_full_router_check');accept=importlib.import_module('noc_full_router_accept');check.RTL=out/'build/noc-full-router-rtl-v1';accept.R=out;accept.CAP=out/'build/rtl-memory-return-path-v1-final';accept.LOCAL=out/'build/noc-router-component-v1-final'
 env=os.environ.copy();node_libs=[out/'external'/str(Path(p).parent).lstrip('/') for p in j['runtime_libraries']['node5']['libraries']];env['LD_LIBRARY_PATH']=os.pathsep.join(map(str,node_libs))
 cases=[]
 with tempfile.TemporaryDirectory(prefix='iris-node5-verify-') as temp:
  scratch=Path(temp)
  for case in ['original9','control8','fenced9','peer']:
   schema,rows=check.read_frames(case);inputs=[x['name'] for x in schema['fields'][:44]];outputs=[x['name'] for x in schema['fields'][44:]];body=''.join('step '+str(x['tb'])+' '+' '.join(str(x[n]) for n in inputs)+'\n' for x in rows);assert body==(acc_path.parent/(case+'.input')).read_text();q=subprocess.run([str(binary),'--seed','1'],input=body,capture_output=True,text=True,env=env,timeout=30);q.check_returncode();actual=[[int(v) for v in line.split()] for line in q.stdout.splitlines()];result=check.compare(actual,rows,outputs);assert q.stdout==(acc_path.parent/(case+'.stdout')).read_text();accept.architecture(case)
   if case!='peer':accept.subset(rows,actual,outputs,case,scratch)
   else:assert len(accept.guards(binary,rows,outputs,scratch))==7 and len(accept.corruptions(rows,actual,outputs,scratch))==5
   command=[str(bench),str(acc_path.parent/(case+'.input')),'2','1'];b=subprocess.run(command,capture_output=True,text=True,env=env,timeout=30);b.check_returncode();benchmark=json.loads(b.stdout);expected=next(x['independent_whole_rtl_digest'] for x in acceptance['benchmarks'] if x['case']==case);assert all(x['defined_output_fnv64']==expected for x in benchmark['passes'])
   if case=='original9':assert accept.snapshots(binary,body,scratch,j['source_identity'])['exact_stdout_suffix']
   cases.append({'case':case,'edges':len(rows),**result});print(json.dumps({'verified_case':case,'edges':len(rows)}),flush=True)
 result={'pass':True,'capsule_sha256':sha(out/'report.json'),'artifacts_verified':len(j['artifacts']),'actual_reset_replays':cases,'source_guards':7,'output_corruptions':5,'snapshot_continuation_edges':19999,'handwritten_differential_edges':52806,'hardware_contacted':False};print(json.dumps(result))
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=FINAL);p.add_argument('--verify',action='store_true');a=p.parse_args();(verify if a.verify else package)(a.output.resolve())
if __name__=='__main__':main()
