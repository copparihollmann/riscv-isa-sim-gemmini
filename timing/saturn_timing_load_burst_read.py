#!/usr/bin/env python3
"""Independent ownership/byte/hold-state reader for the synthetic unit probe."""
import argparse,hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pattern(offset):return (93+13*offset+offset//256)%256
def inspect(text):
 owners={};a=0;d=0;completed=0;retired=0;attempts=0;replays=0;pending=None;states=[];holds=[];addresses=set();vrf={};post=None;summary=None;peak=0
 for line in text.splitlines():
  if not line.startswith('BURST_'):continue
  kind,payload=line.split(' ',1)
  if kind=='BURST_RESULT':summary=json.loads(payload);continue
  parts=payload.split(',')
  if kind=='BURST_STATE':
   row=list(map(int,parts));mag,seed,edge,rdone,acount,dcount,occupied,reserved,inflight,backend,trap,releasing=row
   if mag not in[2,3]or seed not in[0,17]or edge!=len(states)or rdone!=retired or acount!=a or dcount!=d or occupied!=len(owners)or not 0<=reserved<=32 or not 0<=inflight<32:raise ValueError('Physical state counters/edge contradict independent accepted events')
   target=4*(1<<mag);loaded=target*32
   if owners and not backend:raise ValueError('Premature backend idle with outstanding accepted sources')
   if occupied==target and retired==4 and not releasing:
    if reserved!=target or inflight!=target%32 or not backend or not(backend or trap):raise ValueError('Capacity hold counter/reservation/CSR gate contradicts source signals')
    holds.append(edge)
   states.append(row)
  elif kind=='BURST_EX':
   edge,index,inst,address=map(int,parts)
   if pending is not None or index!=retired or inst!=0x02050007+((index*(1<<mag))<<7)or address!=0x80010000+index*(32<<mag):raise ValueError('Wrong or repeated EX restore load')
   pending=(0x80001000+4*index,inst);attempts+=1
  elif kind=='BURST_WB':
   edge=int(parts[0]);status=parts[1];pc,inst=map(int,parts[2:])
   if pending!=(pc,inst):raise ValueError('WB completion/replay has no matching accepted EX command')
   if status=='retire':retired+=1
   elif status=='replay':replays+=1
   else:raise ValueError('Unknown source WB control')
   pending=None
  elif kind=='BURST_A':
   edge,source,size,address=map(int,parts)
   if source in owners or not 32<=source<64 or size!=5 or address in addresses or address not in range(0x80010000,0x80010000+loaded,32):raise ValueError('Source/address reuse or wrong reader mapping')
   owners[source]={'size':size,'address':address,'beat':0};a+=1;peak=max(peak,len(owners));addresses.add(address)
  elif kind=='BURST_D':
   edge,source,size,beat,value=map(int,parts)
   if not states[-1][-1]or source not in owners:raise ValueError('D response while withheld or without accepted source')
   owner=owners[source]
   if size!=owner['size']or beat!=owner['beat']or not 0<=beat<4:raise ValueError('D beat size/count contradicts source owner')
   expected=int.from_bytes(bytes(pattern(owner['address']-0x80010000+beat*8+n)for n in range(8)),'little')
   if value!=expected:raise ValueError('D payload differs from independent address-byte oracle')
   owner['beat']+=1;d+=1
   if owner['beat']==4:del owners[source];completed+=1
  elif kind=='BURST_POST':
   post=list(map(int,parts))
   if post[1:]!=[0]*5 or owners or retired!=4:raise ValueError('Physical post-edge drain is incomplete')
  elif kind=='BURST_VRF':
   eg,word,value=map(int,parts);key=(eg,word)
   if key in vrf or not 0<=eg<32 or not 0<=word<8:raise ValueError('Missing/duplicate/out-of-range physical VRF word')
   offset=eg*32+4*word;expected=int.from_bytes(bytes(pattern(offset+b)if offset+b<loaded else 0 for b in range(4)),'little')
   if value!=expected:raise ValueError('Physical VRF word differs from independent restore-byte oracle')
   vrf[key]=value
  else:raise ValueError('Unknown burst trace record')
 if not states or summary is None or post is None or owners or pending or len(vrf)!=256 or len(holds)!=512 or holds!=list(range(holds[0],holds[0]+512))or a!=target or d!=4*target or completed!=target or retired!=4 or peak!=target or addresses!=set(range(0x80010000,0x80010000+loaded,32)):raise ValueError('Incomplete source burst/hold/drain/readback transcript')
 release=next(row[2]for row in states if row[-1]);expected={'lmul':1<<mag,'seed':seed,'four_load_bytes':loaded,'actual_EX_attempts':attempts,'WB_replays':replays,'WB_retired_loads':retired,'accepted_Get_requests':a,'accepted_D_beats':d,'completed_responses':completed,'peak_outstanding_sources':peak,'peak_reserved_load_slots':max(x[7]for x in states),'peak_nonwrapped_inflight':max(x[8]for x in states),'counter_at_capacity':states[holds[0]][8],'capacity_edge':holds[0]-1,'hold_edges':len(holds),'release_edge':release,'drained_edge':post[0],'VRF_word_checks':len(vrf),'no_premature_backend_idle':True,'derived_scalar_vector_CSR_gate_held':True}
 if summary!=expected:raise ValueError('Program summary differs from independently reconstructed physical transcript')
 return expected
def mutate(text,prefix,part,change):
 lines=text.splitlines();index=next(i for i,line in enumerate(lines)if line.startswith(prefix+' '));tag,data=lines[index].split(' ',1);words=data.split(',');words[part]=str(change(int(words[part])));lines[index]=tag+' '+','.join(words);return '\n'.join(lines)+'\n'
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--probe',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();base=a.probe.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);receipt=json.loads((base/'report.json').read_text());results=[];inputs=[Path(__file__),base/'report.json'];gold=None
 for row in receipt['results']:
  path=base/('m'+str(row['lmul'])+'-seed'+str(row['seed'])+'.stdout');assert sha(path)==receipt['artifact_sha256'][path.name];observed=inspect(path.read_text());assert all(row[k]==v for k,v in observed.items());results.append(observed);inputs.append(path)
  if row['lmul']==8 and row['seed']==0:gold=path.read_text()
 assert gold is not None
 mutations=[('unowned-D-source',mutate(gold,'BURST_D',1,lambda x:x^32)),('wrong-D-byte',mutate(gold,'BURST_D',4,lambda x:x^1)),('wrong-VRF-byte',mutate(gold,'BURST_VRF',2,lambda x:x^1)),('wrong-WB-PC',mutate(gold,'BURST_WB',2,lambda x:x+4)),('wrong-reader-prefix',mutate(gold,'BURST_A',1,lambda x:x^32))]
 lines=gold.splitlines();at=next(i for i,line in enumerate(lines)if line.startswith('BURST_STATE ')and line.split(' ',1)[1].split(',')[6:8]==['32','32']);parts=lines[at].split(' ',1)[1].split(',');parts[9]='0';lines[at]='BURST_STATE '+','.join(parts);mutations.append(('premature-idle','\n'.join(lines)+'\n'));lines=gold.splitlines();parts=lines[at].split(' ',1)[1].split(',');parts[8]='1';lines[at]='BURST_STATE '+','.join(parts);mutations.append(('wrong-capacity-counter','\n'.join(lines)+'\n'));rejections=[]
 for name,text in mutations:
  (out/(name+'.stdout')).write_text(text)
  try:inspect(text)
  except ValueError as error:rejections.append({'name':name,'reason':str(error)})
  else:raise ValueError('Independent reader missed corruption '+name)
 report={'schema':'iris.saturn_restore_burst_independent_reader.v1','pass':True,'results':results,'corruption_refusals':rejections,'input_sha256':{str(p):sha(p)for p in inputs},'artifact_sha256':{str(p.relative_to(out)):sha(p)for p in out.iterdir()if p.is_file()},'physical_FPGA_fault_or_cause_identified':False,'full_scalar_CSR_execution_claimed':False,'hardware_contacted':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'cases':len(results),'VRF_word_checks':sum(x['VRF_word_checks']for x in results),'guarded_capacity_edges':sum(x['hold_edges']for x in results),'corruption_refusals':len(rejections),'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
