#!/usr/bin/env python3
"""Independent bounded warm-hit transport/issue phase proof (no calibration labels)."""
import argparse,copy,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def integer(x):
 if type(x)is not int or x<0:raise ValueError('Typed nonnegative integer required')
 return x

def source(text,pair=False,dual=False):
 rows=[];done=0
 for line in text.splitlines():
  if line=='DONE passed':done+=1;continue
  kind,payload=line.split(' ',1);r=json.loads(payload)
  if kind not in {'REQ','RESP','COM','RRD','CASE'}:raise ValueError('Unknown source event')
  if kind!='CASE':
   for value in r.values():integer(value)
  rows.append((kind,r))
 if done!=1:raise ValueError('Missing/duplicate completion')
 groups=[]
 for seed in (1,17):
  by={k:[x for kind,x in rows if kind==k and x['seed']==seed]for k in ['REQ','RESP','COM','RRD','CASE']}
  req,res,com=by['REQ'],by['RESP'],by['COM']
  if len(req)!=16 or len(res)!=16 or len(com)!=(32 if pair else 16)or len(by['CASE'])!=1:raise ValueError('Complete source geometry')
  if len({x['pc']for x in com})!=len(com):raise ValueError('Duplicate retired PC')
  retired={x['pc']:x['edge']for x in com}
  stride=8 if pair else 4;gap=3 if dual or not pair else 4
  for i,(a,d)in enumerate(zip(req,res)):
   if (a['ordinal'],d['ordinal'],a['address'],d['data'])!=(i,i,0x80000000+8*i,0x80000008+8*i):raise ValueError('Actual accepted request/response identity')
   if d['edge']!=a['edge']+2 or retired[0x80000008+stride*i]!=d['edge']:raise ValueError('Source S2 hit supplies COM, not MEM')
   if i and a['edge']!=req[i-1]['edge']+gap:raise ValueError('Actual continuous source load issue spacing')
   if pair:
    # The first dual-lane packet uses the real late ALU; subsequent ADDIs
    # issue in lane0 with the following load and complete ordinary EX+2 COM.
    delta=2 if dual and i==0 else 5
    if retired[0x8000000c+stride*i]!=a['edge']+delta:raise ValueError('Source dependent ALU stage/retirement phase')
  if dual:
   rr=by['RRD']; pcs=[pc for x in rr for pc in range(x['pc'],x['pc']+4*x['count'],4)]
   if pcs!=list(range(0x80000000,0x80000088,4))or not any(x['count']==2 for x in rr):raise ValueError('Actual legal dual-lane prefix handshakes')
   for a in req:
    if not any(x['edge']==a['edge']-1 and x['pc']<=0x80000008+8*a['ordinal']<x['pc']+4*x['count'] for x in rr):raise ValueError('Request follows accepted RRD by one source edge')
  groups.append(dict(seed=seed,loads=16,load_EX_spacing=gap,hit_response_after_EX=2,dependent_ordinary_ALU_EX_after_load_EX=3 if pair else None,dual_lane_stimulus=dual,first_dual_packet_uses_source_lateALU=dual))
 if len(rows)!=sum(1 for k,x in rows if x['seed']in(1,17)):raise ValueError('Unexpected seed')
 return groups

def cache(text):
 rows=[]
 for line in text.splitlines():
  if line=='DONE passed':continue
  kind,payload=line.split(' ',1)
  if kind!='HIT':raise ValueError('Unknown cache event')
  r=json.loads(payload)
  for k in ['seed','hart','accepted_edge','response_edge']:integer(r[k])
  if r['physical_s2_hit']is not True or r['no_TL_request']is not True or r['response_edge']!=r['accepted_edge']+2:raise ValueError('Real cache hit latency/traffic predicate')
  rows.append(r)
 if len(rows)!=4 or {(r['seed'],r['hart'])for r in rows}!={(s,h)for s in(1,17)for h in(0,1)}:raise ValueError('Complete 2seed/2Shuttle cache ports')
 return rows

def native_events(events,pair=True,expected_gap=2):
 byid={x['id']:x for x in events}
 if len(byid)!=len(events):raise ValueError('Duplicate graph node identity')
 rows=[];base=0x80000480;stride=8 if pair else 4
 for h in(0,1):
  commits=sorted([x for x in events if x['hart']==h and x['name']=='LD.COM'and base<=x['pc']<base+16*stride and x['completed']is True and not x.get('cancelled',False)],key=lambda x:(x['end'],x['id']))
  if len(commits)!=48:raise ValueError('All three actual 16load invocations must retire')
  for ordinal,c in enumerate(commits):
   i=ordinal%16
   if c['pc']!=base+stride*i or len(c['deps'])!=1:raise ValueError('Exact compiled-PC sequence/COM owner')
   ld=byid[c['deps'][0]]
   if ld['name']!='LD.result-ready'or ld['pc']!=c['pc']or ld['hart']!=h or not ld['completed']:raise ValueError('Load result/COM identity')
   if c['end']!=ld['submitted']+3:raise ValueError('Existing EX→COM3 remains intact')
   if pair:
    alu=[x for x in events if x['hart']==h and x['name']=='ADDI.COM'and x['pc']==c['pc']+4 and x['submitted']>=ld['submitted']and x['completed']is True and not x.get('cancelled',False) and len(x['deps'])==1 and ld['id']in byid[x['deps'][0]]['deps']]
    alu=sorted(alu,key=lambda x:(x['submitted'],x['id']))
    if not alu:raise ValueError('Missing actual dependent ALU retirement')
    ar=byid[alu[0]['deps'][0]]
    if ld['id']not in ar['deps']or ar['end']-(ld['submitted']+1)!=expected_gap:raise ValueError('Exact RAW producer plus source EX phase')
    if alu[0]['end']!=ar['end']+2:raise ValueError('ALU COM phase unchanged')
   if i<15:
    following=byid[commits[ordinal+1]['deps'][0]]
    target=3 if pair and expected_gap==3 else 2 if pair else 4
    if following['submitted']-ld['submitted']!=target:raise ValueError('Whole steady packet sequence including next memory slot')
   rows.append(dict(hart=h,call=ordinal//16,ordinal=i,load_EX=ld['submitted']+1,COM=c['end'],dependent_ALU_EX=(ar['end']if pair else None)))
 return rows

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--native-off',type=Path);p.add_argument('--native-on',type=Path);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 refs=[('singlelane-load',1,False,False),('singlelane-pair',2,True,False),('duallane-pair',4,True,True)];source_rows=[];inputs=[Path(__file__).resolve()]
 for name,v,pair,dual in refs:
  b=ROOT/('build/warm-load-phase-shuttle-v'+str(v));t=(b/'stdout').read_text();source_rows+=source(t,pair,dual);inputs +=[b/x for x in ['argv.json','check','stdout','stderr']]+[ROOT/('timing/warm_load_phase_shuttle_v'+str(v)+'.cpp')]
 cb=ROOT/'build/warm-load-phase-cache-v1';cache_rows=cache((cb/'stdout').read_text());inputs +=[cb/x for x in ['argv.json','check','stdout','stderr']]+[ROOT/'timing/warm_load_phase_cache_v1.cpp']
 controls=[]
 def reject(name,fn):
  try:fn()
  except (ValueError,KeyError,TypeError):controls.append(dict(name=name,rejected=True));return
  raise ValueError('Accepted corruption: '+name)
 t=(ROOT/'build/warm-load-phase-shuttle-v4/stdout').read_text();lines=t.splitlines();i=next(i for i,s in enumerate(lines)if s.startswith('RESP '))
 for name,key,value in [('response-one-edge-early','edge',4),('wrong-value','data',0),('boolean-edge','edge',True)]:
  bad=lines[:];r=json.loads(bad[i].split(' ',1)[1]);r[key]=value;bad[i]='RESP '+json.dumps(r);reject(name,lambda b='\n'.join(bad):source(b,True,True))
 reject('missing-request',lambda:source('\n'.join(x for n,x in enumerate(lines)if n!=next(j for j,s in enumerate(lines)if s.startswith('REQ '))),True,True))
 reject('duplicate-COM',lambda:source(t+'\n'+next(x for x in lines if x.startswith('COM ')),True,True))
 reject('single-lane-as-dual-proof',lambda:source((ROOT/'build/warm-load-phase-shuttle-v2/stdout').read_text(),True,True))
 graph_rows={}
 for mode,path,gap in [('off',a.native_off,2),('on',a.native_on,3)]:
  if path:
   path=path.resolve();r=json.loads(path.read_text());ev=r['events'];graph_rows[mode]=native_events(ev,True,gap);inputs.append(path)
   selected=[x for x in ev if 0x80000480<=x['pc']<0x80000500 and x['hart']<2];(a.output/(mode+'-qualified-nodes.json')).write_text(json.dumps(selected,indent=2)+'\n')
   if mode=='on':
    bad=copy.deepcopy(ev);c=next(x for x in bad if x['hart']==0 and x['name']=='ADDI.result-ready'and x['pc']==0x80000484 and x['completed']);c['end']-=1;reject('native-early-consumer',lambda:native_events(bad,True,3))
 source_paths=['third_party/shuttle/src/main/scala/dmem/DCache.scala','third_party/shuttle/src/main/scala/exu/Core.scala','third_party/rocket-chip/src/main/scala/rocket/RocketCore.scala','build/shuttle-lsu-phase-source-v1/build.json','build/shuttle-lsu-phase-source-v1/obj/VShuttleLSUPhase__ALL.a','build/shuttle-lsu-phase-source-v1/rtl/ShuttleCore.sv','build/shuttle-memory-system-native-v6/build.json']
 inputs +=[ROOT/x for x in source_paths]
 r=dict(schema='iris.warm_load_phase_source_proof.v1',pass_=True,source_cases=source_rows,native_phase_comparison_scope='Explicit continuous functional instruction supply with empiricalIcache OFF; parentcosted instruction-cache controls preserved separately. No frontend service timestamps inferred from perhartmcycle.',actual_cache_hits=cache_rows,native_qualified_rows={k:len(v)for k,v in graph_rows.items()},negative_controls=controls,scope='Source-component warm hit/COM-bypass/ordinary dependent ALU; continuous actual2lane delivery separately qualified. Native first late-ALU-pair split remains conservative.',initial_single_lane_4edge_pair_not_hardware_throughput_claim=True,Rocket_phase_change_qualified=False,blanket_load_cost_qualified=False,RTL_internal_state_or_readiness_injected=False,whole_SoC_cycle_accuracy_certified=False,hardware_contacted=False,reserved_hardware_timing_labels_consumed=False,input_sha256={str(x):sha(x)for x in inputs});r['pass']=r.pop('pass_');(a.output/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(status='passed',source_cases=len(source_rows),negative_controls=len(controls),native_rows=r['native_qualified_rows'],report_sha256=sha(a.output/'report.json'))))
if __name__=='__main__':main()
