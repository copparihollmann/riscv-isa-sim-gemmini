#!/usr/bin/env python3
"""Independent fullgraph overlap and bounded/full counter parity witness."""
from pathlib import Path
import hashlib,json,os,subprocess,time
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 parent=R/'build/rvv-vector-store-actor-v2-gates-v1/positive-h0-seed0-ACK200';run=json.loads((parent/'run.json').read_text());assert run['status']=='passed';out=R/'build/rvv-vector-store-actor-v2-full-overlap-v1';out.mkdir(exist_ok=False);fixture=out/'full.fixture';old=(parent/'actor.fixture').read_text();assert old.count(' bounded\n')==1;fixture.write_text(old.replace(' bounded\n',' full\n'));argv=[('--iris-timing-fixture='+str(fixture))if x.startswith('--iris-timing-fixture=')else('--iris-timing-trace='+str(out/'graph.json'))if x.startswith('--iris-timing-trace=')else x for x in run['argv']];env=dict(os.environ,IRIS_EMPIRICAL_ASYNC_TRACE=str(out/'async.jsonl'),IRIS_EMPIRICAL_FEATURES=str(out/'features.jsonl'));start=time.perf_counter()
 with(out/'stdout').open('w')as so,(out/'stderr').open('w')as se:r=subprocess.run(argv,env=env,stdout=so,stderr=se,timeout=90)
 assert r.returncode==0 and (out/'stdout').read_bytes()==(parent/'stdout').read_bytes()
 graph=json.loads((out/'graph.json').read_text());nodes=graph['events'];events=[json.loads(x)for x in(out/'async.jsonl').read_text().splitlines()];front=next(x for x in events if x.get('event')=='VSE_actor_front_COM');last=max(x['cycle']for x in events if x.get('event')=='VSE_actor_ACK_publish'and x['command']==front['command']);overlap=[n for n in nodes if n.get('completed')and n.get('hart')==0 and n.get('start',0)>front['cycle']and n.get('end',last+1)<last and ('.EX'in n.get('name','')or'.COM'in n.get('name',''))and n.get('pc',0)!=front['pc']]
 if not overlap:raise ValueError('No actualscalarpipelineoverlap')
 bounded=[json.loads(x)for x in(parent/'features.jsonl').read_text().splitlines()];full=[json.loads(x)for x in(out/'features.jsonl').read_text().splitlines()];assert len(full)==len(bounded)
 for a,b in zip(full,bounded):
  for key in ['hart','sequence','pc','raw','value','read_cycle','retired']:assert a[key]==b[key]
 inputs=[Path(__file__),parent/'run.json',parent/'stdout',parent/'features.jsonl',fixture,Path(argv[0]),Path(next(x.split('=',1)[1]for x in argv if x.startswith('--extlib='))),Path(argv[-1])];report=dict(schema='iris.VSE_actor_actual_scalar_overlap.v1',status='passed',argv=argv,host_seconds=time.perf_counter()-start,exactboundedfull_console_parity=True,CSR_codepoint_parity_count=len(full),pending_store_window={'front_COM':front['cycle'],'final_matching_ACK':last},actual_completed_scalar_EX_or_COM_nodes=len(overlap),examples=overlap[:6],instruction_PC_ownership='ActualownscalarpipelinePC; no nearestTL/VRFPC inference',input_sha256={str(p):sha(p)for p in inputs},output_sha256={str(p):sha(p)for p in out.iterdir()if p.is_file()},hardware_contacted=False,physical_memory_timing_certified=False);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(sha(out/'report.json'))
if __name__=='__main__':main()
