#!/usr/bin/env python3
"""Fork only host wrappers to select each Verilator owner context; keep RTL bytes."""
import argparse,hashlib,json,re,shutil,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];V=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=R/'build/memory-fabric-context-sdk-v1');a=p.parse_args();out=a.output.resolve()
 if out.exists():raise ValueError('fresh host-wrapper epoch required')
 plans={
 'cache':{'old':R/'build/cache-hierarchy-native-v5','cpp':R/'build/cache-hierarchy-native-v5/cache_hierarchy.generated.cpp','object':'cache_hierarchy.o','library':'libiris_cache_hierarchy.a','identity':'cache_hierarchy_identity.hpp','macro':'IRIS_CACHE_HIERARCHY_SOURCE_ID','class':'Model','include':[R/'build/cache-hierarchy-native-v5'/x for x in ['shuttle','rocket','l2']]},
 'noc':{'old':R/'build/noc-network-sdk-v1','cpp':R/'timing/noc_network.cpp','object':'noc_network.o','library':'libiris_noc.a','identity':'noc_network_identity.hpp','macro':'IRIS_NETWORK_SOURCE_ID','class':'IrisNoCNetwork','include':[R/'build/noc-network-native-v3/model']},
 'adapters':{'old':R/'build/memory-fabric-adapters-native-v2','cpp':R/'build/memory-fabric-adapters-native-v2/memory_fabric_adapters.generated.cpp','object':'adapters.o','library':'libiris_memory_adapters.a','identity':'memory_fabric_identity.hpp','macro':'IRIS_MEMORY_FABRIC_SOURCE_ID','class':'Adapters','include':[R/'build/memory-fabric-adapters-native-v2'/x for x in ['rocket_tile','rocket_source','rocket_sink','manager']]}}
 out.mkdir();reports={};commands=[];start=time.monotonic()
 # NoC source must still be exactly the frozen wrapper; never bind later edits.
 frozen=json.loads((R/'build/noc-network-native-v3/build.json').read_text())['input_sha256'];assert sha(plans['noc']['cpp'])==frozen[str(plans['noc']['cpp'])]
 for name,q in plans.items():
  dest=out/name;dest.mkdir();(dest/'sdk').mkdir();(dest/'objects').mkdir();old=q['old'];lib=old/'sdk'/q['library'];code=q['cpp'].read_text();cls=q['class'];edits={}
  for method in ['evaluate','sample','commit']+(['save','restore']if name=='noc'else[]):
   pattern=r'('+re.escape(cls)+r'::'+method+r'\([^\n{]*\)(?:const)?\{)';matches=list(re.finditer(pattern,code));assert len(matches)==1,(name,method,len(matches));code=re.sub(pattern,lambda m:m[0]+'Verilated::threadContextp(impl_->context.get());',code,count=1);edits[method]=1
  # The constructor itself already creates a context and sets it via the
  # VerilatedContext constructor; explicitly select it before model creation.
  needle='context->randReset(2);'if name in ['cache','adapters']else'context->threads(1);';assert needle in code
  code=code.replace(needle,'Verilated::threadContextp(context.get());'+needle,1)
  identity=hashlib.sha256(json.dumps({'base_library_sha256':sha(lib),'base_wrapper_sha256':sha(q['cpp']),'new_wrapper_body_sha256':hashlib.sha256(code.encode()).hexdigest(),'generator_sha256':sha(__file__),'compiler_sha256':sha('/usr/bin/g++'),'verilated_h_sha256':sha(V/'verilated.h'),'policy':'select owning context for every evaluation/commit/sample and snapshot; RTL objects unchanged'},sort_keys=True).encode()).hexdigest()
  for h in (old/'sdk').glob('*.hpp'):shutil.copy2(h,dest/'sdk'/h.name)
  if not (dest/'sdk'/q['identity']).exists():shutil.copy2(R/'timing'/q['identity'],dest/'sdk'/q['identity'])
  (dest/'sdk'/q['identity']).write_text('#pragma once\n#define '+q['macro']+' "'+identity+'"\n')
  cpp=dest/'context-wrapper.cpp';cpp.write_text(code)
  cmd=['/usr/bin/ar','x',str(lib)];commands.append(cmd);subprocess.run(cmd,cwd=dest/'objects',check=True)
  prior={p.name:sha(p)for p in (dest/'objects').iterdir()};assert q['object']in prior
  cmd=['/usr/bin/g++','-O3','-std=c++20','-I'+str(dest/'sdk'),'-I'+str(V),*['-I'+str(z)for z in q['include']],'-c',str(cpp),'-o',str(dest/'objects'/q['object'])];commands.append(cmd)
  with(dest/'compile.log').open('w')as f:status=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT).returncode
  if status:raise ValueError('context wrapper compile failed '+name)
  changed=[p.name for p in (dest/'objects').iterdir()if sha(p)!=prior[p.name]];assert changed==[q['object']],(name,changed)
  cmd=['/usr/bin/ar','rcs',str(dest/'sdk'/q['library']),*map(str,sorted((dest/'objects').iterdir()))];commands.append(cmd);subprocess.run(cmd,check=True)
  rep={'schema':'iris.memory_fabric_owner_context_sdk.v1','source_identity':identity,'base_library':str(lib),'base_library_sha256':sha(lib),'base_wrapper':str(q['cpp']),'base_wrapper_sha256':sha(q['cpp']),'context_wrapper_sha256':sha(cpp),'library_sha256':sha(dest/'sdk'/q['library']),'selected_methods':edits,'RTL_model_objects_unchanged':True,'unchanged_object_sha256':{n:h for n,h in prior.items()if n!=q['object']},'only_replaced_object':q['object'],'host_policy_only':True,'hardware_contacted':False,'timing_certified':False}
  (dest/'build.json').write_text(json.dumps(rep,indent=2)+'\n');reports[name]=rep
 result={'schema':'iris.memory_fabric_owner_context_derivatives.v1','components':reports,'argv':commands,'input_sha256':{str(p):sha(p)for p in [Path(__file__),Path('/usr/bin/g++'),Path('/usr/bin/ar'),V/'verilated.h']},'host_seconds':time.monotonic()-start,'source_or_timing_logic_changed':False,'hardware_contacted':False,'timing_certified':False}
 (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':'built','report_sha256':sha(out/'report.json'),'host_seconds':result['host_seconds'],'identities':{n:q['source_identity']for n,q in reports.items()}}))
if __name__=='__main__':main()
