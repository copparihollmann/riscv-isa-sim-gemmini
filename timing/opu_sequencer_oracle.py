#!/usr/bin/env python3
"""Independent instruction expansion and absolute-event scheduling for saved OPU control.

This oracle does not import generated C++, internal RTL state, Spike, or the
controller SDK. Matrix coordinates and VRF EG sets come from architectural tile
geometry. Readouts/FP8 dependencies are absolute-time events, not shifted RTL
pipe/tracker/history state. It deliberately covers the saved physical control
boundary, not tile arithmetic or automatic architectural dispatch legality.
"""
from dataclasses import dataclass
from collections import Counter
MASK=(1<<64)-1

def decode(bits,sew):
 key=bits&0xfc00707f
 if key==0xf0000077 and sew==0:return 'int8'
 if key==0xf0001077 and sew==0:return 'fp8'
 if key==0x5c006057 and sew==2:return 'mvin'
 if bits&0xfdf0707f==0x41f06057 and sew==2:return 'mvout'
 if bits&0xfdfff07f==0x41e06057:return 'zero'
 if bits&0xfdfff07f==0x41c06057:return 'discard'
 raise ValueError('Unsupported dispatched instruction')
def expand_arch_group(base,emul):
 first=(base>>emul)<<emul
 return {2*r+g for r in range(first,first+(1<<emul))for g in range(2)}
def bitset(values):return sum(1<<v for v in values)
@dataclass
class Instruction:
 bits:int;tn:int;tm:int;tk:int;alt:int;sew:int;tss:int;vat:int;rm:int;emul:int
 def __post_init__(self):
  self.kind=decode(self.bits,self.sew);self.mm=self.kind in ['int8','fp8'];self.move=self.kind in ['mvin','mvout'];self.rd=self.bits>>7&31;self.a=self.bits>>20&31;self.b=self.bits>>15&31
  self.tile=(self.tss>>29&3)if self.move else(self.rd>>3)
  self.index=self.tss&31;self.col=bool(self.move and self.tss>>24&1)
  self.empty=(not self.tm or not self.tn or not self.tk)if self.mm else (not self.tm or not self.tn)if self.kind=='zero'else not self.tn if self.move else True
  self.ops=[(k,r,c)for k in range(self.tk)for r in range((self.tm+15)//16)for c in range((self.tn+15)//16)]if self.mm and not self.empty else [(0,r,c)for r in range((self.tm+15)//16)for c in range((self.tn+15)//16)]if self.kind=='zero'and not self.empty else [(0,0,c)for c in range((self.tn+3)//4)]if self.move and not self.empty else [(0,0,0)]
  self.ordinal=0
  self.read_b={2*((self.b+2*k)&31)+g for k in range(self.tk)for g in range(2)}if self.mm and not self.empty else set()
  self.read_a={2*((self.a+2*k)&31)+g for k in range(self.tk)for g in range(2)}if self.mm and not self.empty else expand_arch_group(self.a,self.emul)if self.kind=='mvin'and not self.empty else set()
  self.write=expand_arch_group(self.rd,self.emul)if self.kind=='mvout'and not self.empty else set()
 def coord(self):return self.ops[self.ordinal]
 def entry(self):
  _,r,c=self.coord()
  return 4*self.tile+2*r+c if self.mm or self.kind=='zero' else 4*self.tile+2*(c//4 if self.col else self.index//16)+(self.index//16 if self.col else c//4)
 def eg(self):
  k,r,c=self.coord()
  return ((2*((self.b+2*k)&31)+c)&63, (2*((self.a+2*k)&31)+r if self.mm else 2*self.a+c)&63,(2*self.rd+c)&63)

class Oracle:
 def __init__(self):
  self.edge=0;self.reset_seen=False;self.current=None;self.busy=False;self.readouts=[];self.fp8=[];self.wsboard=0;self.stats=Counter();self.dispatches=[];self.issues=[]
 def evaluate(self,i):
  o={};cur=self.current;busy=self.busy
  put=lambda n,v:o.__setitem__('io_'+n,int(v))
  put('busy',busy);put('seq_hazard_valid',busy)
  k,r,c=cur.coord()if cur else(0,0,0);b,a,vd=cur.eg()if cur else(0,0,0)
  read1=bool(cur and cur.mm and not cur.empty);read2=bool(cur and(cur.mm or cur.kind=='mvin')and not cur.empty);moveout=bool(cur and cur.kind=='mvout'and not cur.empty)
  cluster=cur.index%4 if cur else 0;depth=5-cluster;due=self.edge+depth+1
  structural=not any(e['due']==due for e in self.readouts)
  fp8=[e for e in self.fp8 if 0<self.edge-e[0]<=2]
  fpblock=any(e[1]==cur.entry()for e in fp8)if cur and cur.kind=='fp8'and not cur.empty else bool(fp8)
  raw=bool((({b}if read1 else set())|({a}if read2 else set()))&{v for v in range(64)if i['io_older_writes']>>v&1})
  wawwar=bool(moveout and (i['io_older_writes']|i['io_older_reads'])>>vd&1)
  stalls={'raw':raw,'wawwar':wawwar,'fp8':fpblock,'vrf_b':read1 and not i['io_rvs1_ready'],'vrf_a':read2 and not i['io_rvs2_ready'],'write_port':moveout and not i['io_pipe_write_req_available'],'readout_collision':moveout and not structural}
  fire=busy and not any(stalls.values());tail=bool(cur and cur.ordinal==len(cur.ops)-1)
  put('dis_ready',not busy or tail and fire);put('iss_valid',fire)
  if cur:put('tail',tail)
  put('rvs1_valid',busy and read1);put('rvs2_valid',busy and read2)
  if cur:
   for n in ['seq_hazard_bits_vat','vat']:put(n,cur.vat)
   put('seq_hazard_bits_rintent',bitset(cur.read_a|cur.read_b));put('seq_hazard_bits_wintent',bitset(cur.write))
   for n,e in [('rvs1',b),('rvs2',a)]:put(n+'_bits_eg',e);put(n+'_bits_oldest',cur.vat==i['io_vat_head'])
   put('pipe_write_req_bank_sel',1<<(vd%4));put('pipe_write_req_pipe_depth',depth);put('pipe_write_req_oldest',cur.vat==i['io_vat_head'])
   put('iss_bits_signed_l',cur.rd&1);put('iss_bits_signed_t',cur.alt);put('iss_bits_e5m2_l',cur.rd&1);put('iss_bits_e5m2_t',cur.alt);put('iss_bits_fp8',cur.kind=='fp8');put('iss_bits_rm',cur.rm)
   for q in range(4):
    for t in range(4):put(f'iss_bits_row_en_{q}_{t}',16*r+q+4*t<cur.tm);put(f'iss_bits_col_en_{q}_{t}',16*c+q+4*t<cur.tn)
    put(f'iss_bits_mv_en_{q}',4*c+q<cur.tn)
  for q in range(4):
   put(f'iss_bits_mrf_idx_{q}',cur.entry()if fire else 0);put(f'iss_bits_row_idx_{q}',cur.index//4%4 if fire else 0);put(f'iss_bits_col_idx_{q}',c%4 if fire else 0)
   put(f'iss_bits_macc_{q}',bool(fire and cur.mm and not cur.empty));put(f'iss_bits_zero_{q}',bool(fire and cur.kind=='zero'and not cur.empty))
   put(f'iss_bits_mvin_{q}',bool(fire and cur.kind=='mvin'and not cur.empty and not cur.col and cluster==q));put(f'iss_bits_mvin_col_{q}',bool(fire and cur.kind=='mvin'and not cur.empty and cur.col and cluster==q))
  for q in range(1,4):put(f'iss_bits_shift_{q}',any(not e['column']and e['cluster']<q and self.edge-e['issued']==q-e['cluster']for e in self.readouts))
  put('pipe_write_req_request',busy and moveout and structural);put('pipe_write_req_fire',fire);put('write_reg_enable',any(e['due']==self.edge+1 for e in self.readouts));put('wsboard',self.wsboard)
  results=[e for e in self.readouts if e['due']==self.edge];assert len(results)<=1
  put('write_valid',bool(results))
  if results:
   e=results[0];put('write_bits',e['eg']);mask=sum(((1<<32)-1)<<(32*q)for q in range(4)if e['mask']>>q&1);put('write_mask',mask&MASK);put('write_mask_hi',mask>>64)
  self.last=(o,stalls,fire,tail,vd,cluster,results)
  return o
 def commit(self,i):
  o,stalls,fire,tail,vd,cluster,results=self.last;cur=self.current
  if i['reset']:
   self.reset_seen=True;self.current=None;self.busy=False;self.readouts=[];self.fp8=[];self.wsboard=0;self.edge+=1;return
  if self.busy:
   for n,v in stalls.items():self.stats['stall_'+n]+=bool(v)
  if fire:
   self.stats['issues_'+cur.kind]+=1;self.issues.append({'edge':self.edge,'kind':cur.kind,'tile':cur.tile,'entry':cur.entry(),'coord':cur.coord(),'empty':cur.empty,'column':cur.col,'index':cur.index})
   if cur.kind=='fp8'and not cur.empty:self.fp8.append((self.edge,cur.entry()))
   if cur.kind=='mvout'and not cur.empty:
    _,_,c=cur.coord();self.readouts.append(dict(issued=self.edge,cluster=cluster,column=cur.col,due=self.edge+6-cluster,eg=vd,mask=sum(1<<q for q in range(4)if 4*c+q<cur.tn)));self.wsboard|=1<<vd
   if not tail:
    k,r,c=cur.coord()
    if cur.mm:
     nextk=cur.ops[cur.ordinal+1][0]
     if nextk!=k:
      done={2*((base+2*k)&31)+g for base in [cur.a,cur.b]for g in range(2)};cur.read_a-=done;cur.read_b-=done
    elif cur.kind=='mvin':cur.read_a.discard(cur.eg()[1])
    elif cur.kind=='mvout':cur.write.discard(vd)
    cur.ordinal+=1
   self.busy=not tail
  for e in results:self.wsboard&=~(1<<e['eg']);self.stats['writebacks']+=1
  self.readouts=[e for e in self.readouts if e['due']>self.edge];self.fp8=[e for e in self.fp8 if self.edge-e[0]<2]
  if i['io_dis_valid']and o['io_dis_ready']:
   cur=Instruction(i['io_dis_bits_bits'],i['io_dis_bits_vconfig_vl'],i['io_dis_bits_vconfig_vtype_tm'],i['io_dis_bits_vconfig_vtype_tk'],i['io_dis_bits_vconfig_vtype_altfmt'],i['io_dis_bits_vconfig_vtype_vsew'],i['io_dis_bits_rs1_data'],i['io_dis_bits_vat'],i['io_dis_bits_rm'],i['io_dis_bits_emul']);self.current=cur;self.busy=True;self.dispatches.append({'edge':self.edge,'kind':cur.kind,'tile':cur.tile,'tm':cur.tm,'tn':cur.tn,'tk':cur.tk,'empty':cur.empty,'column':cur.col,'index':cur.index});self.stats['dispatched_'+cur.kind]+=1
  self.edge+=1
