#!/usr/bin/env python3
"""Independent EX/permission timestamp observations from the complete Saturn unit."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);a=ap.parse_args();o=Path(a.output).resolve();o.mkdir(parents=True,exist_ok=False);sdk=ROOT/'build/saturn-timing-ownership-sdk-v7/sdk';compiler=Path('/scratch/eygao/iris-cy/.conda-env/bin/x86_64-conda-linux-gnu-c++');src=Path(__file__).with_name('overlap_completion_front_phase_witness.cpp');binary=o/'witness';cmd=[str(compiler),'-O2','-std=c++20','-no-pie','-I'+str(sdk),'-I'+str(ROOT/'timing'),str(src),str(sdk/'libiris_saturn_timing.a'),'-pthread','-latomic','-o',str(binary)];r=subprocess.run(cmd,capture_output=True);(o/'build.stdout').write_bytes(r.stdout);(o/'build.stderr').write_bytes(r.stderr);assert not r.returncode;rows=[];joins=[]
 for shape,count,rotate in [(16,64,0),(32,256,0),(16,64,1)]:
  name=f'fp8.m{shape}.n{count}.rotate{rotate}';r=subprocess.run([str(binary),'fp8',str(shape),str(count),str(rotate),'0'],capture_output=True,text=True,timeout=60);(o/(name+'.stdout')).write_text(r.stdout);(o/(name+'.stderr')).write_text(r.stderr);assert not r.returncode
  latest={};recs=[json.loads(l)for l in r.stdout.splitlines()];summary=json.loads(r.stderr);this=[]
  for x in recs:
   if x['EX_fire']:latest[x['EX_pc']]=x['edge']
   if x['front_permission']:
    assert x['COM_pc']in latest and x['backend_input_fire'];delta=x['edge']-latest[x['COM_pc']];assert delta==2
    this.append({'pc':x['COM_pc'],'EX_edge':latest[x['COM_pc']],'permission_backend_input_edge':x['edge'],'latency_source_edges':delta})
  assert len(this)==count;rows.append(dict(shape=shape,count=count,rotate=rotate,summary=summary));joins.extend(this)
 core=ROOT/'third_party/shuttle/src/main/scala/exu/Core.scala';integration=ROOT/'third_party/saturn/src/main/scala/shuttle/Frontend.scala';paths=[Path(__file__).resolve(),src,ROOT/'timing/overlap_completion_command_queues.hpp',sdk/'libiris_saturn_timing.a',sdk/'saturn_timing.hpp',core,integration,ROOT/'third_party/saturn/src/main/scala/frontend/PipelinedFaultCheck.scala'];j={'schema':'iris.OPU_EX_permission_phase_witness.v1','pass':True,'programs':rows,'actual_accepted_EX_to_successful_backend_input_joins':len(joins),'all_latencies_source_edges':2,'backpressure_replays_included':sum(x['summary']['front_replays']for x in rows),'joins':joins,'native_current_bridge':'RRD+1 EX, RRD+3 COM, COM+1 backendinput; disclosed conservative policy','structural_source_implication':'Under an unstalled CPU EX-to-MEM-to-COM chain, observed EX+2 frontpermission/backendinput aligns with COM, so the native COM+1 convention is one edge late. This witness does not qualify the whole CPU stall/replay/global-edge integration.','exact_CPU_bridge_certified':False,'no_observed_ready_or_state_inputs':True,'reserved_or_hardware_timing_labels_read':False,'hardware_contacted':False,'input_sha256':{str(p):sha(p)for p in paths}}
 (o/'report.json').write_text(json.dumps(j,indent=2)+'\n');print(json.dumps({'pass':True,'joins':len(joins),'replays':j['backpressure_replays_included'],'report_sha256':sha(o/'report.json')}))
if __name__=='__main__':main()
