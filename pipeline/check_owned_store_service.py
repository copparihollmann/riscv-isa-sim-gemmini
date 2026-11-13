#!/usr/bin/env python3
"""Actual ELF controls for fractional service, issue spacing and rule priority."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--uart',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);runs={};counts={}
 base=json.loads((ROOT/'build/rocket-packet-native-first-v1/report.json').read_text())['argv']
 for label,setup,interval,cache in [('fraction',.25,1,False),('II',0,4,False),('cache-only',None,1,True),('cache-family',100,1,True)]:
  d=out/label;d.mkdir();text=(ROOT/'build/rocket-packet-native-first-v1/first.fixture').read_text().replace('unfitted-bounded-v1 bounded','unfitted-bounded-v1 full')+'\nempirical_store_front owned-dirty-L1-COM-v1\n'
  for h in range(3):
   text+=f'resource empirical.store-test{h} 1\n'
   if setup is not None:text+=f'empirical_family {h} memory.DRAM.store empirical.store-test{h} {setup} 0 {interval} SYNTHETIC_SERVICE '+('0'*64)+' core_cycles\n'
   if cache:text+=f'empirical_cache_service {h} 0 0 0 0 1 0 SYNTHETIC_ZERO_CACHE '+('0'*64)+' core_cycles\n'
  fixture=d/'fixture';fixture.write_text(text);argv=[x for x in base if not x.startswith(('--iris-timing-fixture=','--iris-timing-trace='))];argv[0]=str(a.binary.resolve());argv=['--extlib='+str(a.uart.resolve())if x.startswith('--extlib=')else x for x in argv];argv[-1]=str(ROOT/'build/empirical-owned-store-guest-v2/guest.elf');argv[-1:-1]=['--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(d/'graph.json')]
  inputs=[Path(__file__).resolve(),a.binary,a.uart,fixture,Path(argv[-1])];before={str(p.resolve()):sha(p)for p in inputs};start=time.monotonic();r=subprocess.run(argv,capture_output=True,timeout=120,env=dict(os.environ,IRIS_EMPIRICAL_ASYNC_TRACE=str(d/'async.jsonl'),IRIS_EMPIRICAL_FEATURES=str(d/'features.jsonl')));elapsed=time.monotonic()-start;(d/'stdout').write_bytes(r.stdout);(d/'stderr').write_bytes(r.stderr);assert r.returncode==0,(label,r.stderr)
  numeric=[list(map(int,x.split()[1:]))for x in r.stdout.decode().splitlines()if x.startswith('IRIS_OWNED_STORE ')];assert sorted(numeric)==[[0,0,0,305419896],[1,0,0,305419896],[2,0,0,305419896]],numeric
  g=json.loads((d/'graph.json').read_text());events=[json.loads(x)for x in(d/'async.jsonl').read_text().splitlines()];nodes={n['id']:n for n in g['events']};deferred={e['response']:e for e in events if e['event']=='store_defer'}
  if label=='fraction':
   actual=[0,0,0]
   for n in g['events']:
    if n['name']=='empirical.memory.DRAM.store':actual[n['hart']]+=n['end']-n['start']-3
    elif n['id']in deferred:
     e=deferred[n['id']];actual[n['hart']]+=n['end']-n['start']-(0 if e['owned_at_COM']else 3)
   expected=[g['per_hart_features'][h]['memory.DRAM.store']['instructions']//4 for h in range(3)]
   assert actual==expected,(actual,expected);counts['fractional_cycles']=actual
  if label=='II':
   owned=[nodes[i]for i,e in deferred.items()if e['owned_at_COM']];assert len(owned)>100
   assert all(n['end']-n['start']==1 for n in owned)
   launches={h:sorted(n['start']for n in g['events']if n['resource']==f'empirical.store-test{h}')for h in range(3)}
   assert all(all(b-a>=4 for a,b in zip(starts,starts[1:]))for starts in launches.values());counts['II4_owned_reservations']=len(owned)
  assert all(sha(p)==h for p,h in before.items());runs[label]={'stdout':r.stdout,'stderr':r.stderr,'prefix':(d/'features.jsonl').read_bytes(),'trace':(d/'async.jsonl').read_bytes(),'cycles':g['cycles'],'retired':g['retired_instructions']};(d/'report.json').write_text(json.dumps({'pass':True,'argv':argv,'input_sha256':before,'host_seconds':elapsed,'retired_instructions':g['retired_instructions'],'simulated_MIPS':sum(g['retired_instructions'])/elapsed/1e6},indent=2)+'\n');print(label,elapsed,flush=True)
 assert runs['cache-only']==runs['cache-family'],'DRAM family must be superseded by cache rules'
 report={'schema':'iris.owned_store_service_controls.v1','pass':True,'binary_sha256':sha(a.binary),'uart_sha256':sha(a.uart),'actual_counts':counts,'cache_family_priority_guest_prefix_trace_byte_parity':True,'all_costs_synthetic':True};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(sha(out/'report.json'))
if __name__=='__main__':main()
