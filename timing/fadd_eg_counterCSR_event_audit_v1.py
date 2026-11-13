#!/usr/bin/env python3
"""Join authoritative FADD COM geometry to actual per-EG issue/write events."""
from pathlib import Path
import argparse,json,hashlib,collections,re
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def audit(b,o):
 run=json.loads((b/'run.json').read_text());assert run['pass']
 commands={};issues={};writes={};counterkinds=collections.Counter();geom=collections.Counter();killed=set();front=set()
 raw=(b/'async.jsonl').read_bytes();last=raw.rfind(b'\n')+1;tail=raw[last:];assert not tail or re.fullmatch(rb'{\"event\":\"publish\",\"hart\":1,\"instruction\":[0-9]+,\"backend_node\":',tail)
 for line in raw[:last].splitlines():
  e=json.loads(line);kind=e['event']
  if kind=='fadd_EG_front_reservation':front.add((e['hart'],e['generation']))
  if kind=='fadd_EG_wrongpath_cancel':killed.add((e['hart'],e['generation']))
  if kind=='fadd_EG_functional_COM':
   key=e['hart'],e['generation'];assert key not in commands and key not in killed
   assert e['geometry_authority']=='checked_architectural_COM'and e['SEW']in(16,32,64)and e['LMUL_numerator']in(1,2,4,8)and e['LMUL_denominator']==1 and e['VL']==256//e['SEW']*e['LMUL_numerator']and e['new_flags']==0
   assert(e['raw']&0xfc00707f)==0x1057 and e['raw']&(1<<25)and e['vd']==((e['raw']>>7)&31)and e['vs1']==((e['raw']>>15)&31)and e['vs2']==((e['raw']>>20)&31)
   commands[key]=e;geom[(e['hart'],e['SEW'],e['LMUL_numerator'])]+=1
  if kind=='fadd_EG_microissue':
   key=e['hart'],e['generation'];assert key in commands;c=commands[key];index=e['index'];assert 0<=index<2*c['LMUL_numerator']and e['cycle']>=c['cycle']+4
   assert (*key,index)not in issues;issues[(*key,index)]=e['cycle']
  if kind=='fadd_EG_physical_write':
   key=e['hart'],e['generation'];index=e['index'];assert key in commands and (*key,index)in issues and (*key,index)not in writes
   assert e['bytes']==16 and e['cycle']==issues[(*key,index)]+4;writes[(*key,index)]=e['cycle']
  if kind=='fadd_EG_counter_read':
   assert e['architecturally_retired']is True and e['csr']in(0xb00,0xb02,0xc00,0xc02)and(e['raw']>>20)==e['csr'];counterkinds[(e['csr'],e['async_compute_pending'])]+=1
 assert len(commands)==57600 and len(issues)==len(writes)==432000 and not(set(commands)&killed)
 for key,c in commands.items():assert all((*key,i)in writes for i in range(2*c['LMUL_numerator']))
 assert set(commands)<=front
 result=dict(schema='iris.FADD_EG_authoritative_COM_event_join.v1',**{'pass':True},actual_architectural_COM_commands=len(commands),source_microissues=len(issues),physical_16B_writes=len(writes),internal_VRF_write_bytes=16*len(writes),logical_FP_add_elements=sum(c['VL']for c in commands.values()),complete_join_key=['hart','generation','index'],geometry_from='checked_architectural_COM only; never provisional reservation',preCOM_wrongpath_cancellations=len(killed),canceled_commands_get_no_work_credit=True,all_EG_write_edges=4,retired_counter_events=sum(counterkinds.values()),counter_events=[dict(csr=k[0],numeric_tail_pending=k[1],count=v)for k,v in sorted(counterkinds.items())],command_geometry=[dict(hart=k[0],SEW=k[1],LMUL_numerator=k[2],LMUL_denominator=1,count=v)for k,v in sorted(geom.items())],physical_DRAM_or_TL_traffic_claimed=False,unit_utilization_or_peak_claimed=False,no_hardware_labels=True,async_complete_newline_prefix_bytes=last,async_trailing_partial_legacy_publish_bytes=len(tail),all_FADD_command_issue_and_write_events_complete=True,whole_async_trace_complete=not bool(tail),controlled_debugger_exit_can_leave_unflushed_legacy_observer_tail=True,input_sha256={str(p):sha(p)for p in [Path(__file__).resolve(),b/'run.json',b/'async.jsonl',b/'features.jsonl',ROOT/'build/FADD-EG-counterCSR-frozen-8a8cf119-v2/manifest.json']})
 o.mkdir(exist_ok=False);(o/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'pass':True,'sha256':sha(o/'report.json'),'commands':len(commands),'microissues':len(issues),'writes':len(writes)}))
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--replay',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();audit(a.replay.resolve(),a.output.resolve())
