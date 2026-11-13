#!/usr/bin/env python3
"""Independent whole saved RTL with read-only memory-fabric boundary visibility."""
import argparse,hashlib,json,shutil,subprocess,time,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];CAP=R/'build/rtl-memory-return-path-v1-final'
sys.path.insert(0,str(R/'timing'))
from memory_fabric_graph import Hierarchy

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--graph',type=Path,default=R/'build/memory-fabric-graph-v1/graph.json');p.add_argument('--output',type=Path,default=R/'build/memory-fabric-reference-v1');p.add_argument('--jobs',type=int,default=8);a=p.parse_args();out=a.output.resolve()
 if out.exists():raise ValueError('fresh independent reference required')
 g=json.loads(a.graph.read_text());h=Hierarchy();visible=set()
 def visit(e):
  if e['op']=='net':
   name=e['name'];assert name.startswith('DigitalTop/');path,sep,net=name[len('DigitalTop/'):].rpartition('/');h.at(path);visible.add((h.paths[path][0],net))
  elif e['op']=='slice':visit(e['value'])
  elif e['op']=='concat':
   for v in e['values']:visit(v)
 for c in g['components'].values():
  for f in c['physical_ports']:visit(f['global'])
 # These source outputs are physically present but unconnected above DCache.
 for f in g['components']['rocket_cache']['physical_ports']:
  if f['global']['op']=='unconnected':visible.add(('DCache',f['name']))
 original=R/'build/rtl-verilator';m=json.loads((original/'manifest.json').read_text());out.mkdir();src=out/'rtl';src.mkdir();mapping={};files=[]
 for line in (original/'sim_files.f').read_text().splitlines():
  original_path=Path(line);relative=original_path.relative_to(R);frozen=CAP/relative;path=frozen if frozen.exists()else original_path;expected=m['sim_source_sha256'][str(R/relative)];assert sha(path)==expected,str(path);dest=src/path.name;assert not dest.exists();shutil.copy2(path,dest);mapping[str(path)]=expected;files.append(dest)
 for pattern in ['*.h','*.vh']:
  for path in (original/'gen-collateral').glob(pattern):
   dest=src/path.name
   if not dest.exists():shutil.copy2(path,dest);mapping[str(path)]=sha(path)
 control=out/'memory-fabric-ports-readonly.vlt';control.write_text('`verilator_config\n'+''.join('public_flat_rd -module "'+mod+'" -var "'+net+'"\n'for mod,net in sorted(visible)))
 filelist=out/'sim_files.f';filelist.write_text('\n'.join(map(str,files))+'\n');model=out/'model';command=m['verilator_argv'][:]
 replacements={str(original/'sim_files.f'):str(filelist),str(original/'gen-collateral'):str(src),str(original/'model'):str(model),str(original/'simulator-IrisConfig'):str(out/'simulator-generated-main')}
 command=[next((arg.replace(old,new)for old,new in replacements.items()if old in arg),arg)for arg in command];command.insert(command.index('-f'),str(control));begin=time.monotonic()
 (out/'verilate-command.json').write_text(json.dumps(command,indent=2)+'\n')
 with(out/'verilate.log').open('w')as f:status=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT).returncode
 if status:raise ValueError('independent reference Verilation failed')
 compile=['make','-j'+str(a.jobs),'VM_PARALLEL_BUILDS=1','CXX=/usr/bin/g++','LINK=/scratch/eygao/iris-cy/.conda-env/bin/x86_64-conda-linux-gnu-c++','AR=/usr/bin/ar','RANLIB=/usr/bin/ranlib','PERL=/scratch/eygao/iris-cy/.conda-env/bin/perl','-f','VTestDriver.mk','VTestDriver__ALL.a'];(out/'compile-command.json').write_text(json.dumps(compile,indent=2)+'\n')
 with(out/'compile.log').open('w')as f:status=subprocess.run(compile,cwd=model,stdout=f,stderr=subprocess.STDOUT).returncode
 result={'schema':'iris.memory_fabric_independent_whole_rtl.v1','source_fir_sha256':'f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4','verilate_argv':command,'compile_argv':compile,'exit_status':status,'host_seconds':time.monotonic()-begin,'source_sha256':mapping,'read_only_visibility_fields':len(visible),'visibility_sha256':sha(control),'input_sha256':{str(p):sha(p)for p in [Path(__file__),R/'timing/memory_fabric_graph.py',a.graph,original/'manifest.json',original/'sim_files.f']},'RTL_logic_changed':False,'internal_state_injected':False,'hardware_contacted':False,'timing_certified':False,'loaded_image_association_verified':False}
 if not status:result['model_archive_sha256']=sha(model/'VTestDriver__ALL.a')
 (out/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'exit_status':status,'host_seconds':result['host_seconds'],'visibility_fields':len(visible),'report_sha256':sha(out/'build.json')}))
 if status:raise SystemExit(status)
if __name__=='__main__':main()
