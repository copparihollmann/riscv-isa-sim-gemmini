#!/usr/bin/env python3
"""Host-only single-thread derivatives and identity-rebound frozen parent SDKs."""
import argparse,hashlib,json,re,shutil,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];V=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
 if out.exists():raise ValueError('fresh derivative required')
 out.mkdir();commands=[];reports={};start=time.monotonic()
 plans={'cache':('libiris_cache_hierarchy.a','cache_hierarchy_identity.hpp','IRIS_CACHE_HIERARCHY_SOURCE_ID'),'adapters':('libiris_memory_adapters.a','memory_fabric_identity.hpp','IRIS_MEMORY_FABRIC_SOURCE_ID')}
 for name,(libname,identity_header,macro)in plans.items():
  old=R/'build/memory-fabric-context-sdk-v2'/name;prior=json.loads((old/'build.json').read_text());lib=old/'sdk'/libname;assert sha(lib)==prior['library_sha256'];cpp=old/'context-wrapper.cpp';assert sha(cpp)==prior['context_wrapper_sha256'];code=cpp.read_text();assert code.count('context->randReset(2);')==1;code=code.replace('context->randReset(2);','context->threads(1);context->randReset(2);');base=Path(prior['base_wrapper']).parent;single={}
  for q in base.iterdir():
   if not q.is_dir()or q.name in ['rtl','sdk']:continue
   for f in q.glob('V*.cpp'):
    matches=re.findall(r'unsigned (\w+)::threads\(\) const \{ return (\d+); \}',f.read_text())
    for model,count in matches:assert count=='1';single[str(f)]=sha(f)
  assert len(single)==(3 if name=='cache'else 4)
  dest=out/name;dest.mkdir();shutil.copytree(old/'sdk',dest/'sdk');(dest/'objects').mkdir();newcpp=dest/'host-single-thread.cpp';newcpp.write_text(code)
  identity=hashlib.sha256(json.dumps({'base_library_sha256':sha(lib),'base_wrapper_sha256':sha(cpp),'new_wrapper_sha256':sha(newcpp),'generator_sha256':sha(__file__),'compiled_single_thread_models':single,'policy':'explicit context threads1, matching unchanged compiled model threads1; no targetRTL/state/timing edits'},sort_keys=True).encode()).hexdigest();(dest/'sdk'/identity_header).write_text('#pragma once\n#define '+macro+' "'+identity+'"\n')
  cmd=['/usr/bin/ar','x',str(lib)];commands.append(cmd);subprocess.run(cmd,cwd=dest/'objects',check=True);before={x.name:sha(x)for x in(dest/'objects').iterdir()};obj=prior['only_replaced_object'];inc=[dest/'sdk',V,*[x for x in base.iterdir()if x.is_dir()and x.name not in ['rtl','sdk']]]
  cmd=['/usr/bin/g++','-O3','-std=c++20',*['-I'+str(x)for x in inc],'-c',str(newcpp),'-o',str(dest/'objects'/obj)];commands.append(cmd)
  with(dest/'compile.stdout').open('w')as stdout,(dest/'compile.stderr').open('w')as stderr:subprocess.run(cmd,stdout=stdout,stderr=stderr,check=True)
  changed=[x.name for x in(dest/'objects').iterdir()if sha(x)!=before[x.name]];assert changed==[obj]
  cmd=['/usr/bin/ar','rcs',str(dest/'sdk'/libname),*map(str,sorted((dest/'objects').iterdir()))];commands.append(cmd);subprocess.run(cmd,check=True)
  report={'schema':'iris.shuttle_parent_host_single_thread.v1','source_identity':identity,'base_library':str(lib),'base_library_sha256':sha(lib),'base_build_sha256':sha(old/'build.json'),'base_wrapper_sha256':sha(cpp),'new_wrapper_sha256':sha(newcpp),'library_sha256':sha(dest/'sdk'/libname),'only_replaced_object':obj,'unchanged_object_sha256':{n:h for n,h in before.items()if n!=obj},'compiled_model_single_thread_evidence':single,'RTL_model_objects_unchanged':True,'host_policy_only':True,'hardware_contacted':False,'timing_certified':False};(dest/'build.json').write_text(json.dumps(report,indent=2)+'\n');reports[name]=report
 mf=out/'fabric';cmd=['python3',str(R/'timing/memory_fabric_compose.py'),'--graph',str(R/'build/memory-fabric-graph-v1/graph.json'),'--cache',str(out/'cache'),'--adapters',str(out/'adapters'),'--noc',str(R/'build/memory-fabric-context-sdk-v2/noc'),'--output',str(mf)];commands.append(cmd)
 with(out/'fabric.stdout').open('w')as stdout,(out/'fabric.stderr').open('w')as stderr:subprocess.run(cmd,stdout=stdout,stderr=stderr,check=True)
 # Rebuild the unchanged physical System host body against the new identities.
 old=R/'build/serial-memory-system-native-v2';oldr=json.loads((old/'build.json').read_text());system=out/'system';system.mkdir();(system/'sdk').mkdir();source=R/'timing/serial_memory_system.cpp';assert sha(source)==oldr['input_sha256'][str(source)];header=R/'timing/serial_memory_system.hpp';assert sha(header)==oldr['input_sha256'][str(header)];shutil.copy2(header,system/'sdk'/header.name)
 serial=R/'build/serial-memory-context-sdk-v2/serial/sdk';noc=R/'build/memory-fabric-context-sdk-v2/noc/sdk';includes=[mf/'sdk',serial,out/'cache/sdk',noc,out/'adapters/sdk'];libs=[mf/'sdk/libiris_memory_fabric.a',out/'cache/sdk/libiris_cache_hierarchy.a',noc/'libiris_noc.a',out/'adapters/sdk/libiris_memory_adapters.a',serial/'libiris_serial_memory.a'];inputs=[Path(__file__),old/'build.json',source,header,mf/'build.json',*[x for q in includes for x in q.glob('*.hpp')],*libs];identity=hashlib.sha256(json.dumps({str(x):sha(x)for x in inputs},sort_keys=True).encode()).hexdigest();(system/'sdk/serial_memory_system_identity.hpp').write_text('#pragma once\n#define IRIS_SERIAL_MEMORY_SYSTEM_SOURCE_ID "'+identity+'"\n')
 cmd=['/usr/bin/g++','-O3','-std=c++20','-I'+str(system/'sdk'),*['-I'+str(x)for x in includes],'-c',str(source),'-o',str(system/'wrapper.o')];commands.append(cmd)
 with(system/'compile.stdout').open('w')as stdout,(system/'compile.stderr').open('w')as stderr:subprocess.run(cmd,stdout=stdout,stderr=stderr,check=True)
 cmd=['/usr/bin/ar','rcs',str(system/'sdk/libiris_serial_memory_system.a'),str(system/'wrapper.o')];commands.append(cmd);subprocess.run(cmd,check=True)
 report={'schema':'iris.shuttle_parent_identity_rebind.v1','exit_status':0,'source_identity':identity,'source_body_unchanged':True,'library_sha256':sha(system/'sdk/libiris_serial_memory_system.a'),'input_sha256':{str(x):sha(x)for x in inputs},'required_include_directories':list(map(str,includes)),'required_static_libraries_in_link_order':list(map(str,libs)),'hardware_contacted':False,'timing_certified':False};(system/'build.json').write_text(json.dumps(report,indent=2)+'\n');reports['system']=report
 (out/'report.json').write_text(json.dumps({'schema':'iris.shuttle_parent_derivatives.v1','reports':reports,'argv':commands,'host_seconds':time.monotonic()-start,'hardware_contacted':False,'timing_certified':False},indent=2)+'\n');print(json.dumps({'report_sha256':sha(out/'report.json'),'source_identity':identity}))
if __name__=='__main__':main()
