#!/usr/bin/env python3
"""Verify per-K completion credit and final-K-only architectural projection."""
import argparse,hashlib,json
from pathlib import Path
from timing.memory_routes_current_audit_v2 import Elf
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--run',required=True);ap.add_argument('--build',required=True);ap.add_argument('--tk',required=True,type=int,choices=[1,2,4]);ap.add_argument('--output',required=True);a=ap.parse_args();r=Path(a.run).resolve();b=Path(a.build).resolve();o=Path(a.output).resolve();o.mkdir(parents=True,exist_ok=False);proof=json.load(open(r/'report.json'));assert proof['pass']is True and proof['normal_HTIF_guest_exit']is True and proof['numeric_words']==106496;trace=[json.loads(l)for l in(r/'async.jsonl').read_text().splitlines()];e=Elf(b/'guard.elf');events={};completed={};pub={};pending_micro={};scheduled={}
 for x in trace:
  h=x.get('hart');n=x.get('instruction');t=x.get('cycle')
  if x['event']=='opu_K_microissue':
   key=(h,n,x['entry'],x['k']);assert key not in events and x['tk']==a.tk and bool(x['last_k'])==(x['k']+1==a.tk);events[key]=dict(x);pending_micro[(h,n,x['entry'],x['cycle'])]=key
  elif x['event']=='opu_microissue_reserved':
   key=pending_micro.pop((h,n,x['entry'],x['seq']));z=events[key];raw=int.from_bytes(e.read(x['pc'],4),'little');assert raw&127==0x77 and((raw>>12)&7)in(0,1)
   latency=3 if((raw>>12)&7)==1 else 1
   assert x['write']==x['seq']+latency and x['array']==x['seq']+1 and x['macs']==z['macs']
   z['write']=x['write'];z['pc']=x['pc'];scheduled[(h,n,x['write'],z['k'])]=key
  elif x['event']=='opu_K_completion':
   key=scheduled.pop((h,n,t,x['k']));z=events[key]
   assert key not in completed and type(x['k'])is int and 0<=x['k']<a.tk
   assert type(x['last_k'])is int and x['last_k']in(0,1)and bool(x['projected_MRF_published'])==bool(x['last_k'])==(x['k']+1==a.tk)
   completed[key]=x
  elif x['event']=='opu_entry_publish':
   key=(h,n,t);assert key not in pub;pub[key]=x
 expected=12288*a.tk;assert not pending_micro and not scheduled and len(events)==len(completed)==expected and len(pub)==12288
 total=sum(x['macs']for x in events.values());assert total==2752512*a.tk
 for key,z in events.items():
  assert (z['hart'],z['instruction'],z['write'])in pub if z['last_k']else(z['hart'],z['instruction'],z['write'])not in pub
 # Every physical entry receives its K steps exactlyonce and in sourceorder.
 by_entry={}
 for key,z in events.items():by_entry.setdefault(key[:3],[]).append(z)
 for seq in by_entry.values():assert [x['k']for x in sorted(seq,key=lambda x:x['cycle'])]==list(range(a.tk))
 out={'schema':'iris.OPU_K_completion_ledger.v1','pass':True,'TK':a.tk,'source_K_completions':expected,'final_entry_publications':len(pub),'logical_MAC_credit':total,'numeric_words_independently_checked':106496,'intermediate_K_architectural_publications':0,'partial_K_physical_MRF_values':'notmodeled/unavailable; only source control and MACcredit qualified; CPU readersdrain','normal_HTIF_guest_exit':True,'hardware_contacted':False,'reference_timings_consumed':False,'input_sha256':{str(p):sha(p)for p in(Path(__file__).resolve(),r/'report.json',r/'async.jsonl',b/'build.json',b/'guard.elf')}};(o/'report.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({'pass':True,'TK':a.tk,'K_completions':expected,'final_publications':len(pub),'MACs':total,'sha256':sha(o/'report.json')}))
if __name__=='__main__':main()
