#!/usr/bin/env python3
"""Replay independent NoC references on the context-aware host-only derivative."""
import hashlib,json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'build/memory-fabric-context-checks-v2';SDK=R/'build/memory-fabric-context-sdk-v1/noc/sdk';CXX=Path('/scratch/eygao/iris-cy/.conda-env/bin/x86_64-conda-linux-gnu-c++')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 if O.exists():raise ValueError('fresh qualification output required')
 O.mkdir();commands=[];inputs=[Path(__file__),CXX,R/'timing/noc_network_bench.cpp',SDK/'libiris_noc.a'];start=time.monotonic()
 def run(cmd,stem):
  commands.append(cmd)
  with(O/(stem+'.stdout')).open('w')as f,(O/(stem+'.stderr')).open('w')as e:q=subprocess.run(cmd,stdout=f,stderr=e)
  assert q.returncode==0,(stem,q.returncode)
  return json.loads((O/(stem+'.stdout')).read_text())if stem!='compile'else None
 run([str(CXX),'-O3','-std=c++20','-no-pie','-I'+str(SDK),str(R/'timing/noc_network_bench.cpp'),str(SDK/'libiris_noc.a'),'-pthread','-latomic','-o',str(O/'benchmark')],'compile')
 runs=[]
 for case,mode in [('control8','step'),('control8','revised'),('coherent','step'),('coherent','revised')]:
  p=R/'build/noc-network-replay-v1'/(case+'-step.input');inputs.append(p);argv=[str(O/'benchmark'),str(p),'1','1',mode];x=run(argv,case+'-'+mode);expected=1085834545165361624 if case=='control8'else 5185151649837067476
  assert x['passes'][0]['defined_field_mix64']==expected,(case,mode)
  runs.append({'case':case,'mode':mode,'edges':x['edges_per_pass'],'mix64':expected,'independent_reference_match':True})
 selftest=run([str(O/'benchmark'),'selftest',str(R/'build/noc-network-replay-v1/control8-step.input'),str(O/'context-snapshot.bin')],'selftest')
 result={'schema':'iris.memory_fabric_context_reference_checks.v1','status':'passed','runs':runs,'selftest':selftest,'argv':commands,'input_sha256':{str(p):sha(p)for p in set(inputs)},'binary_sha256':sha(O/'benchmark'),'output_sha256':{p.name:sha(p)for p in O.iterdir()if p.suffix in ['.stdout','.stderr','.bin']},'host_seconds':time.monotonic()-start,'hardware_contacted':False,'timing_certified':False,'arbitrary_unreset_history_order_independence_proved':False}
 (O/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':'passed','report_sha256':sha(O/'report.json'),'source_edges':sum(x['edges']for x in runs)}))
if __name__=='__main__':main()
