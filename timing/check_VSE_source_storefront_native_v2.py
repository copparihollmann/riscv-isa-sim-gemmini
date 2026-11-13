#!/usr/bin/env python3
"""Actual source transport handshakes joined to live Spike COM and RAM goldens."""
from pathlib import Path
import argparse,concurrent.futures,json
from check_VSE_live_boundary_native_v1 import R,F,execute,sha
B=R/'build/spike-VSE-source-storefront-v2'
P=R/'build/VSE-live-boundary-frozen-e24c891b-v1'
def run(o,h,seed,delay):
 d=o/('h%d-seed%d-D%d'%(h,seed,delay));f=o/(d.name+'.fixture');f.write_text(F.read_text()+'\nexperimental_vse_boundary SOURCE-STOREFRONT-SYNTHETIC-D-ONLY-v2 %d %d core_edges\n'%(h,delay));elf=R/('build/VSE-live-boundary-guest-h%d-v1/guest.elf'%h);r=execute(d,B/'spike',B/'libsifive_uart.so',f,elf,seed);checks=[r['exit_status']==0,not r['timed_out'],not(d/'stderr').read_text()];stdout=(d/'stdout').read_text();rows=[json.loads(x.split(' ',1)[1])for x in stdout.splitlines()if x.startswith('IRIS_VSE_BOUNDARY {')];checks.extend([rows==[dict(hart=h,checked_words=512,stored_words=193,mismatch_or=0,checksum=886531796120)],'IRIS_VSE_BOUNDARY_DONE'in stdout]);events=[json.loads(x)for x in(d/'async.jsonl').read_text().splitlines()]
 names=['VSE_source_upstream_ROB_reserve','VSE_source_storefront_VMU_request_fire','VSE_source_storefront_ATL_A_fire','VSE_source_storefront_ATL_D_fire','VSE_source_storefront_VMU_matching_response','VSE_boundary_synthetic_response_publish','VSE_boundary_ordered_SIFQ_release'];stages=[[x for x in events if x['event']==n]for n in names];front=[x for x in events if x['event']=='VSE_boundary_checked_COM'];key=lambda x:(x['command'],x['tag'],x['generation']);checks.extend([len(front)==8,*[len(xs)==49 for xs in stages],*[set(map(key,xs))==set(map(key,stages[0]))for xs in stages],[key(x)for x in stages[-1]]==[key(x)for x in stages[0]],sum(x['bytes']for x in stages[-2])==772])
 maps=[{key(x):x for x in xs}for xs in stages]
 for k in maps[0]:
  if not all(k in m for m in maps):checks.append(False);continue
  q,v,a,d_,vrf,pub,release=(m[k]for m in maps);checks.extend([q['cycle']<v['cycle']<=a['cycle']<d_['cycle']<vrf['cycle']==pub['cycle']<=release['cycle'],d_['cycle']-a['cycle']>=delay+(0 if a['tag']&1 else 3)])
 for xs in stages[1:5]:
  for x in xs:checks.extend([x['master_tick']==2*x['cycle'],x['cycle']-x['source_edge']==front[0]['cycle']+1,x['external_D_synthetic_test_only']])
 for a,b in zip(front,front[1:]):checks.append(b['cycle']>max(x['cycle']for x in stages[-1]if x['command']==a['command']))
 summary=json.loads((d/'summary.json').read_text());t=summary['VSE_source_storefront'];checks.extend([t['actual_VMU_requests']==t['actual_ATL_A']==t['actual_ATL_D']==t['actual_VMU_responses']==49,t['drained']and t['owned_transport']==0,t['idle_source_edges_evaluated']>0,t['source_edges']==summary['cycles']-front[0]['cycle'],not summary['VSE_live_boundary']['pending']])
 if delay==200:checks.append(t['raw_busy_false_with_live_owners']>0)
 return dict(path=str(d),**{'pass':all(checks)},checks=len(checks),failed_checks=[i for i,v in enumerate(checks)if not v],h=h,seed=seed,external_D_delay_test_edges=delay,source_summary=t)
def parity(o,mode):
 d=o/mode;d.mkdir();f=F
 if mode=='old-synthetic-ON-parity':f=d/'oldmode.fixture';f.write_text(F.read_text()+'\nexperimental_vse_boundary SYNTHETIC-DIRECTED-TEST-ONLY-v1 0 20 core_edges\n')
 runs=[]
 for name,base in[('parent',P),('child',B)]:runs.append(execute(d/name,base/'spike',base/'libsifive_uart.so',f,R/'build/VSE-live-boundary-guest-h0-v1/guest.elf'))
 eq={n:(d/'parent'/n).read_bytes()==(d/'child'/n).read_bytes()for n in('stdout','stderr','features.jsonl','async.jsonl','summary.json')};return dict(path=str(d),kind=mode,**{'pass':all(eq.values())and all(x['exit_status']==0 and not x['timed_out']for x in runs)},equal_outputs=eq)
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--quick',action='store_true');a=p.parse_args();o=a.output.resolve();o.mkdir(exist_ok=False);cases=[(0,0,20)]if a.quick else[(h,s,d)for h in(0,1)for s in(0,17)for d in(1,20,200)]
 with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:results=[f.result()for f in[pool.submit(run,o,*c)for c in cases]]
 if not a.quick:results.extend(parity(o,m)for m in('all-new-flags-OFF-parity','old-synthetic-ON-parity'))
 report=dict(schema='iris.VSE_source_storefront_live_normal.v2',**{'pass':all(x['pass']for x in results)},runs=results,actual_source_transport=True,external_D_synthetic_test_only=True,product_System_backend_available=False,VMU_or_CPU_phase_qualified=False,coherent_memory_timing_qualified=False,hardware_or_protected_labels_accessed=False,input_sha256={str(p):sha(p)for p in[Path(__file__),R/'timing/check_VSE_live_boundary_native_v1.py',B/'pipeline-build.json']});(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':report['pass'],'sha256':sha(o/'report.json')}));raise SystemExit(not report['pass'])
if __name__=='__main__':main()
