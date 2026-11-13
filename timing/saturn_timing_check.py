#!/usr/bin/env python3
"""Continuous full-unit source boundary replay; only source-qualified payload is compared."""
import argparse,hashlib,json,re,struct,subprocess,time
from collections import Counter
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def capture(path,profiles):
 rows=[[],[],[]];outputs=[[],[],[]];times=[[],[],[]]
 for line in path.open():
  if not line.startswith('RTL_SATURN_RUNTIME '):continue
  parts=line.split(' ',1)[1].strip().split(',');tb=int(parts[0]);h=int(parts[1]);j=profiles['rocket'if h==2 else'compute'];n=len(j['words']['input']);words=[int(x,16)for x in parts[2:]]
  if len(words)!=n+len(j['words']['output']):raise ValueError('Wrong captured physical port width')
  if times[h]and tb<=times[h][-1]:raise ValueError('Core clock edges not strictly increasing')
  times[h].append(tb);rows[h].append(dict(zip([f['word_name']for f in j['words']['input']],words[:n])));outputs[h].append(dict(zip([f['word_name']for f in j['words']['output']],words[n:])))
 if any(not v or not v[0]['reset']for v in rows):raise ValueError('Missing actual per-core reset history')
 return rows,outputs,times

def qualified(profile,i,o,stage2=None,previous_hella_store=False):
 """Output bit masks from real valid/protocol qualifiers, never guessed reset data."""
 masks={};core='io_core_'if profile=='rocket'else'io_'
 for name,value in o.items():
  if name.endswith('_valid')or name in [core+n for n in ['ex_ready','backend_busy','trap_check_busy','set_vxsat']]+(['io_com_retire_late','io_com_xcpt','io_com_scalar_check_ready','io_com_internal_replay','io_com_block_all']if profile=='compute'else['io_core_mem_block_mem','io_core_mem_block_all','io_core_wb_replay','io_core_wb_retire','io_core_wb_xcpt']):masks[name]=(1<<64)-1
 if i['auto_atl_out_d_valid']:masks['auto_atl_out_d_ready']=(1<<64)-1
 if o['auto_atl_out_a_valid']:
  for name in o:
   if name.startswith('auto_atl_out_a_bits_')and not name.startswith('auto_atl_out_a_bits_data'):masks[name]=(1<<64)-1
  if o['auto_atl_out_a_bits_opcode']in [0,1]:
   busmask=o['auto_atl_out_a_bits_mask']
   for name in o:
    if name.startswith('auto_atl_out_a_bits_data'):
     word=int(name.rsplit('_',1)[1])if profile=='compute'else 0;masks[name]=sum(255<<(8*b)for b in range(8)if busmask>>(8*word+b)&1)
 tlb='io_tlb_req_'if profile=='rocket'else'io_mem_tlb_req_'
 if o[tlb+'valid']:
  for name in o:
   if name.startswith(tlb+'bits_'):masks[name]=(1<<64)-1
 for group in ['resp','set_vstart','set_vconfig','set_fflags']:
  if o[core+group+'_valid']:
   for name in o:
    if name.startswith(core+group+'_bits'):masks[name]=(1<<64)-1
 if profile=='compute':
  if stage2 or o['io_com_retire_late']or o['io_com_xcpt']:masks['io_com_pc']=(1<<64)-1
  if o['io_com_xcpt']:
   for n in ['io_com_cause','io_com_tval']:masks[n]=(1<<64)-1
 else:
  if stage2 or o['io_core_wb_retire']or o['io_core_wb_replay']or o['io_core_wb_xcpt']:
   for n in ['io_core_wb_inst','io_core_wb_pc']:masks[n]=(1<<64)-1
  if o['io_core_wb_xcpt']:
   for n in ['io_core_wb_cause','io_core_wb_tval']:masks[n]=(1<<64)-1
  if o['io_dmem_req_valid']:
   for name in o:
    if name.startswith('io_dmem_req_bits_'):masks[name]=(1<<64)-1
  if previous_hella_store:
   masks['io_dmem_s1_data_mask']=(1<<64)-1
   for n in range(4):masks['io_dmem_s1_data_data_'+str(n)]=sum(255<<(8*b)for b in range(8)if o['io_dmem_s1_data_mask']>>(8*n+b)&1)
  if o['io_fp_req_valid']:
   for name in o:
    if name.startswith('io_fp_req_bits_'):masks[name]=(1<<64)-1
 return masks

class Timeline:
 """Independent scalar stage identities + accepted physical TL-beat accounting.

 This ledger is observation/checker metadata, not a model input. It never
 generates peer-ready, memory data, a queue state or timing penalties.
 """
 def __init__(self,profile):self.profile=profile;self.s1=None;self.s2=None;self.hella_store=False;self.pending={};self.stats=Counter();self.events=[];self.next_id=0
 def observe(self,edge,tb,i,o):
  if i['reset']:self.s1=None;self.s2=None;self.hella_store=False;self.pending={};return
  def event(kind,**kw):self.events.append(dict(kind=kind,edge=edge,tb=tb,**kw));self.stats[kind]+=1
  if i['auto_atl_out_d_valid']and o['auto_atl_out_d_ready']:
   source=i['auto_atl_out_d_bits_source'];opcode=i['auto_atl_out_d_bits_opcode']
   if source not in self.pending:raise ValueError('D return without accepted source ownership')
   owner=self.pending[source]
   if i['auto_atl_out_d_bits_size']!=owner['size']or opcode!=(1 if owner['opcode']==4 else 0):raise ValueError('D response type/size contradicts accepted A')
   owner['d_seen']+=1;event('TL_D_beat',source=source,opcode=opcode,owner_edge=owner['edge'],beat=owner['d_seen'],total=owner['d_total'])
   if owner['d_seen']==owner['d_total']:del self.pending[source]
   elif owner['d_seen']>owner['d_total']:raise ValueError('Excess D data beat')
  if o['auto_atl_out_a_valid']and i['auto_atl_out_a_ready']:
   source=o['auto_atl_out_a_bits_source'];opcode=o['auto_atl_out_a_bits_opcode'];size=o['auto_atl_out_a_bits_size'];address=o['auto_atl_out_a_bits_address'];bus=8 if self.profile=='rocket'else 32
   if opcode not in [0,1,4]:raise ValueError('Unsupported observed ATL protocol opcode')
   if source not in self.pending:self.pending[source]={'edge':edge,'opcode':opcode,'size':size,'address':address,'a_seen':0,'d_seen':0,'a_total':max(1,((1<<size)+bus-1)//bus)if opcode in [0,1]else 1,'d_total':max(1,((1<<size)+bus-1)//bus)if opcode==4 else 1}
   owner=self.pending[source]
   if any(owner[k]!=v for k,v in [('opcode',opcode),('size',size),('address',address)])or owner['a_seen']>=owner['a_total']:raise ValueError('A source identifier reused before response completion')
   owner['a_seen']+=1;event('TL_A_beat',source=source,opcode=opcode,size=size,address=address,beat=owner['a_seen'],total=owner['a_total'])
  rocket=self.profile=='rocket';core='io_core_'if rocket else'io_';valid=i[core+'ex_valid'];ready=o[core+'ex_ready'];fire=valid and ready and(rocket or i['io_ex_fire'])
  if valid and ready:
   inst=i['io_core_ex_inst'if rocket else'io_ex_uop_inst'];pc=i['io_core_ex_pc'if rocket else'io_ex_uop_pc'];cmd={'id':self.next_id,'pc':pc,'inst':inst,'ex_edge':edge,'fired':bool(fire)};self.next_id+=1;event('EX_candidate',**cmd)
   if fire:event('EX_fire',**cmd)
  else:cmd=None
  kill=i['io_core_killm']if rocket else i['io_mem_kill']or(self.s1 is not None and not self.s1['fired'])
  if self.s1 is not None and kill:event('MEM_kill',**self.s1)
  if self.s2 is not None:event('COM_front_token',**self.s2)
  if rocket:
   for field,kind in [('io_core_wb_replay','WB_replay'),('io_core_wb_retire','WB_front_retire'),('io_core_wb_xcpt','WB_exception')]:
    if o[field]:event(kind,pc=o['io_core_wb_pc'],inst=o['io_core_wb_inst'])
   if o['io_dmem_req_valid']and i['io_dmem_req_ready']:event('Hella_A_request',cmd=o['io_dmem_req_bits_cmd'],tag=o['io_dmem_req_bits_tag'])
   if o['io_fp_req_valid']and i['io_fp_req_ready']:event('shared_FPU_request')
   if i['io_fp_resp_valid']:event('shared_FPU_response')
   self.hella_store=bool(o['io_dmem_req_valid']and i['io_dmem_req_ready']and o['io_dmem_req_bits_cmd']==1)
  else:
   for field,kind in [('io_com_retire_late','COM_retire_late'),('io_com_internal_replay','COM_internal_replay'),('io_com_xcpt','COM_exception')]:
    if o[field]:event(kind,pc=o['io_com_pc'])
  if o[core+'resp_valid']and i[core+'resp_ready']:event('scalar_response',rd=o[core+'resp_bits_rd'],fp=o[core+'resp_bits_fp'],data=o[core+'resp_bits_data'])
  if o[core+'set_fflags_valid']:event('fflags_update',bits=o[core+'set_fflags_bits'])
  self.s2=self.s1 if not kill else None;self.s1=cmd

def compare(profile,j,rows,physical,times,lines):
 samples=[line for line in lines if line.startswith('SATURN_FRAME ')]
 if len(samples)!=len(rows):raise ValueError('Missing/extra runtime output edges')
 ledger=Timeline(profile);checks=0;known_after_reset=False;masks_by_edge=[]
 for edge,(line,i,gold,tb)in enumerate(zip(samples,rows,physical,times)):
  parts=line.split();assert int(parts[1])==edge and len(parts)==2+len(j['words']['output']);actual=dict(zip([f['word_name']for f in j['words']['output']],map(int,parts[2:])));masks=qualified(profile,i,gold,ledger.s2,ledger.hella_store)if known_after_reset else{};masks_by_edge.append(masks)
  for name,mask in masks.items():
   if(actual[name]^gold[name])&mask:raise ValueError(f'Runtime mismatch {profile} edge{edge}/TB{tb} {name}: {actual[name]} vs {gold[name]}, mask{mask:x}')
   checks+=1
  if i['reset']:known_after_reset=True
  ledger.observe(edge,tb,i,gold)
 return {'edges':len(rows),'qualified_output_word_checks':checks,'source_events':dict(ledger.stats),'pending_TL_sources_at_end':len(ledger.pending)},ledger,masks_by_edge

def mailbox(path,case):
 lines=path.read_text().splitlines()
 if len(lines)!=28 or any(not re.fullmatch('[0-9a-f]{16}',x)for x in lines):raise ValueError('Malformed mailbox signature')
 words=[int(x,16)for x in lines];kind,checks={'vme':(7,[1472,1472,2]),'rvv':(8,[33]*3),'fpcomp':(3,[52]*3),'shared-fpu':(9,[28]*3)}[case]
 if words[:4]!=[0x4952495350524f42,1,kind,0]:raise ValueError('Failed/wrong guest mailbox')
 result=[]
 for h in range(3):
  row=dict(zip(['stage','actual','expected','cause','pc','tval','checks','done'],words[4+8*h:12+8*h]),hart=h)
  if row['checks']!=checks[h]or row['done']!=1 or row['actual']!=row['expected']or row['cause']!=(2 if case=='vme'and h==2 else 0):raise ValueError('Incomplete or wrong numeric/refusal mailbox')
  result.append(row)
 return result

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--sdk',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();sdk=a.sdk.resolve();run=a.run.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);r=json.loads(run.read_text());assert r['exit_status']==0 and not r['timed_out'];assert sha(r['argv'][0])==r['binary_sha256']and sha(r['argv'][-1])==r['elf_sha256'];harts=mailbox(run.with_suffix('.signature'),r['case']);profiles={k:json.loads((R/'build/saturn-timing-source-v1'/k/'ports.json').read_text())for k in ['compute','rocket']};rows,physical,times=capture(run.with_suffix('.stderr'),profiles);reports=[]
 for h in range(3):
  profile='rocket'if h==2 else'compute';j=profiles[profile];inputs=out/f'hart{h}.input';inputs.write_text(''.join('step '+str(e)+' '+' '.join(str(i[f['word_name']])for f in j['words']['input'])+'\n'for e,i in enumerate(rows[h])));command=[str(sdk/'saturn-timing'),'--reference-two-state','--profile',profile,'--hart',str(h),'--seed','17'];start=time.monotonic()
  with inputs.open()as ins,(out/f'hart{h}.stdout').open('w')as stdout,(out/f'hart{h}.stderr').open('w')as stderr:q=subprocess.run(command,stdin=ins,stdout=stdout,stderr=stderr,timeout=180)
  if q.returncode:raise ValueError('Runtime cut refused actual physical input history')
  proof,ledger,masks=compare(profile,j,rows[h],physical[h],times[h],(out/f'hart{h}.stdout').read_text().splitlines());(out/f'hart{h}.events.json').write_text(json.dumps(ledger.events,separators=(',',':'))+'\n')
  with(out/f'hart{h}.masks.bin').open('wb')as f:
   f.write(struct.pack('<8sQQ',b'SATMSK01',len(masks),len(j['words']['output'])))
   for row in masks:f.write(struct.pack('<'+'Q'*len(j['words']['output']),*[row.get(field['word_name'],0)for field in j['words']['output']]))
  first=next((edge for edge,i in enumerate(rows[h])if i['io_core_ex_valid'if profile=='rocket'else'io_ex_valid']),len(rows[h]));mix=1469598103934665603;mix_words=0
  for edge in range(first,len(rows[h])):
   for field in j['words']['output']:
    mask=masks[edge].get(field['word_name'],0)
    if mask:mix=((mix^(physical[h][edge][field['word_name']]&mask))*1099511628211)&((1<<64)-1);mix_words+=1
  (out/f'hart{h}.benchmark-window.json').write_text(json.dumps({'first_EX_candidate_edge':first,'end_edge_exclusive':len(rows[h]),'qualified_field_mix64':mix,'qualified_words':mix_words,'scope':'Real guest interval including scalar gaps and all source edges; no skipped model edges'},indent=2)+'\n')
  assert proof['pending_TL_sources_at_end']==0,'Guest ended with unreturned vector TL requests';reports.append({'hart':h,'profile':profile,'argv':command,'host_seconds':time.monotonic()-start,'qualified_active_window_mix64':mix,**proof})
 inputs=[Path(__file__),sdk/'saturn-timing',sdk/'build.json',run,run.with_suffix('.stdout'),run.with_suffix('.stderr'),run.with_suffix('.signature'),Path(r['argv'][0]),Path(r['argv'][-1])];report={'schema':'iris.saturn_runtime_actual_reset_replay.v1','case':r['case'],'harts':reports,'guest_mailbox':harts,'input_sha256':{str(p):sha(p)for p in inputs},'all_physical_inputs_from_whole_RTL':True,'internal_state_or_readiness_reinjected':False,'qualified_numeric_payload_only':True,'general_definedness_or_live_Spike_timing_certified':False,'hardware_contacted':False};report['artifact_sha256']={str(p.relative_to(out)):sha(p)for p in out.iterdir()if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'case':r['case'],'harts':reports,'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
