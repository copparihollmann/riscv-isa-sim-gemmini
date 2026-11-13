#!/usr/bin/env python3
"""Conditional queue/control proof; no hardware observations or fitted values."""
import hashlib,itertools,json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 import argparse
 a=argparse.ArgumentParser();a.add_argument('--output',required=True);args=a.parse_args()
 out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False)
 compiler=Path('/scratch/eygao/iris-cy/.conda-env/bin/x86_64-conda-linux-gnu-c++')
 sdk=ROOT/'build/saturn-timing-ownership-sdk-v7/sdk'
 source=ROOT/'timing/overlap_completion_tk_queue_source_witness.cpp';header=ROOT/'timing/overlap_completion_command_queues_tk.hpp'
 def build(dst,src):
  cmd=[str(compiler),'-O2','-std=c++20','-no-pie','-I'+str(sdk),'-I'+str(ROOT/'timing'),str(src),str(sdk/'libiris_saturn_timing.a'),'-pthread','-latomic','-o',str(dst)]
  r=subprocess.run(cmd,capture_output=True,text=True);(dst.parent/'build.stdout').write_text(r.stdout);(dst.parent/'build.stderr').write_text(r.stderr)
  if r.returncode:raise RuntimeError('build failed '+str(dst))
  return cmd
 cmd=build(out/'witness',source);cases=[]
 for kind,shape,count,rotate,tk in itertools.product(('int8','fp8'),(8,16,32),(64,256),(0,1),(1,2,4)):
  traces=[]
  for seed in (0,17):
   name=f'{kind}.m{shape}.n{count}.r{rotate}.tk{tk}.s{seed}';t=time.monotonic()
   r=subprocess.run([str(out/'witness'),kind,str(shape),str(count),str(rotate),str(seed),str(tk)],capture_output=True,text=True,timeout=60)
   (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
   if r.returncode:raise RuntimeError(name+' '+r.stderr)
   summary=json.loads(r.stderr);assert summary['pass'] and summary['retired']==count
   assert summary['microissues']==count*((shape+15)//16)**2*tk
   traces.append(r.stdout);cases.append(dict(kind=kind,shape=shape,count=count,rotate=rotate,seed=seed,tk=tk,elapsed_seconds=time.monotonic()-t,**summary))
  assert traces[0]==traces[1], 'qualified control trace differs by seed'
 mutations={
  'Wrong_K_count_packed4':('input->tk!=1&&input->tk!=2&&input->tk!=4','input->tk!=1&&input->tk!=2&&input->tk!=4'),
  'Wrong_K_inner_loop':('if(++row_==(o.issue->command.tm+15)/16){row_=0;++k_;}','if(++row_==(o.issue->command.tm+15)/16){row_=0;k_=0;}')}
 # Mutation1 shortens the control K loop, not operanddata or observations.
 mutations['Wrong_K_count_packed4']=('const bool last_k=k_+1==seq_->tk','const bool last_k=k_+1==1')
 rejects=[]
 for name,(old,new) in mutations.items():
  d=out/name;d.mkdir();s=header.read_text();assert old in s;s=s.replace(old,new);(d/header.name).write_text(s);(d/source.name).write_text(source.read_text());build(d/'witness',d/source.name)
  rotate=1 if 'tile_blind' in name else 0
  r=subprocess.run([str(d/'witness'),'fp8','32','64','0','0','4'],capture_output=True,text=True,timeout=60)
  (d/'stdout').write_text(r.stdout);(d/'stderr').write_text(r.stderr)
  if r.returncode!=2 or 'queue differential edge' not in r.stderr:raise RuntimeError('mutant did not fail '+name+' '+r.stderr)
  rejects.append(dict(name=name,refusal=r.stderr.strip()))
 deps=[source,header,sdk/'saturn_timing.hpp',sdk/'libiris_saturn_timing.a',sdk/'ownership-schema.json',ROOT/'third_party/saturn/src/main/scala/backend/Backend.scala',ROOT/'third_party/saturn/src/main/scala/backend/OuterProductSequencer.scala',ROOT/'third_party/saturn/src/main/scala/common/DCEQueue.scala',ROOT/'third_party/saturn/src/main/scala/common/Parameters.scala',ROOT/'third_party/saturn/src/main/scala/shuttle/Frontend.scala',ROOT/'third_party/saturn/src/main/scala/frontend/PipelinedFaultCheck.scala',ROOT/'third_party/saturn/src/main/scala/backend/RegisterAccess.scala',Path(__file__).resolve(),compiler]
 report=dict(schema='iris.opu_entry_TK124_queue_source_differential.v1',pass_=True,cases=cases,checks=sum(c['checks'] for c in cases),mutant_rejections=rejects,build_command=cmd,input_sha256={str(p):sha(p) for p in deps},scope='Actual post-reset compute Saturn source unit; MM TK1/2/4 positive TM/TN 8/16/32; 128 quiet edges establish VRF scrub; no competing VRF writer; actual EX ready and PFC replay obeyed. Backend abstract inputs are actual valid/payload, never observed ready/state. Logical data/numeric correctness not asserted.',backend_storage={'VDQ':4,'VXIQ':3,'sequencer':1,'VAT32_is_storage':False},hardware_contacted=False,FPGA_image_association=False,CPU_COM_availability_bridge_qualified=False)
 report['pass']=report.pop('pass_');(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'runs':len(cases),'checks':report['checks'],'report':str(out/'report.json'),'sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
