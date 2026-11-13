#!/usr/bin/env python3
import argparse,hashlib,json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--case',required=True,choices=['vme','rvv','fpcomp','shared-fpu']);p.add_argument('--hart',required=True,type=int,choices=[0,1,2]);p.add_argument('--repetitions',type=int,default=3);a=p.parse_args();bench=R/'build/saturn-timing-active-bench-v1';out=bench/(a.case+'-h'+str(a.hart));
 if out.with_suffix('.json').exists():raise ValueError('Fresh active benchmark receipt required')
 replay=R/'build/saturn-timing-replay-v2'/a.case;inputs=replay/f'hart{a.hart}.input';masks=replay/f'hart{a.hart}.masks.bin';window=replay/f'hart{a.hart}.benchmark-window.json';j=json.loads(window.read_text());command=[str(bench/'benchmark'),'rocket'if a.hart==2 else'compute',str(a.hart),str(inputs),str(masks),str(a.repetitions)];start=time.monotonic();q=subprocess.run(command,capture_output=True,text=True,timeout=180);out.with_suffix('.stdout').write_text(q.stdout);out.with_suffix('.stderr').write_text(q.stderr)
 if q.returncode:raise RuntimeError('Active direct stepping failed')
 result=json.loads(q.stdout)
 for run in result['runs']:
  if run['qualified_field_mix64']!=j['qualified_field_mix64']or run['qualified_words']!=j['qualified_words']:raise ValueError('Direct SDK result differs from independent whole-SoC masked field mix')
 assert result['executed_prefix_edges']==j['first_EX_candidate_edge']and result['timed_active_guest_edges']==j['end_edge_exclusive']-j['first_EX_candidate_edge'];paths=[Path(__file__),bench/'benchmark',bench/'build.json',inputs,masks,window,replay/'report.json'];report={'schema':'iris.saturn_actual_workload_speed.v1','case':a.case,'hart':a.hart,'argv':command,'exit_status':q.returncode,'host_seconds_total':time.monotonic()-start,'input_sha256':{str(p):sha(p)for p in paths},'result':result,'independent_whole_RTL_mix_verified':True,'production_SoC_iteration_speed_claimed':False,'hardware_contacted':False};out.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'case':a.case,'hart':a.hart,'runs':result['runs'],'active_edges':result['timed_active_guest_edges'],'receipt_sha256':sha(out.with_suffix('.json'))}))
if __name__=='__main__':main()
