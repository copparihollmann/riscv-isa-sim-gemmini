#!/usr/bin/env python3
"""Read-only full physical node5 boundary from the independent whole-SoC model."""
from pathlib import Path
import hashlib,json,re,subprocess
R=Path(__file__).resolve().parents[1];CAP=R/'build/rtl-memory-return-path-v1-final';OUT=R/'build/noc-full-router-rtl-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 if OUT.exists():raise ValueError('Refuse to overwrite full boundary observer')
 h=(CAP/'build/rtl-verilator/model/VTestDriver___024root.h').read_text();ns=set(re.findall(r'\s(\w+);',h));S='TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__';P=lambda node:S+'sbus_system_bus_noc_acd_noc_noc_router_sink_domain'+('_'+str(node) if node else '')+'__DOT__routers__DOT__';M=S+'sbus_system_bus_noc_acd_noc_nif_master_acd_3__DOT__';items=[];post=[]
 def f(n):
  if n not in ns:raise ValueError('Missing physical source: '+n)
  return 'iris_root->'+n
 def add(n,e):items.append({'name':n,'expression':e});return len(items)-1
 def present(n):return n in ns
 reset=f(S+'chipyard_prcictrl_domain__DOT__resetSynchronizer__DOT__nodeOut_member_allClocks_uncore_reset_catcher__DOT__io_sync_reset_chain__DOT__output_chain__DOT__sync_0');add('i_reset','!'+reset)
 # Network interfaces, with payload sampled from the actual accepted write slot.
 transfers=[]
 def channel(prefix,source_node,out_index,dest_node,input_index):
  a=S+'_sbus_system_bus_noc_acd_noc_noc_router_sink_domain'+('_'+str(source_node) if source_node else '')+'_auto_routers_source_nodes_out_'+str(out_index)+'_flit_0_'
  valid=add(prefix+'valid',f(a+'valid'));add(prefix+'head',f(a+'bits_head'));tail=add(prefix+'tail','0');words=[add(prefix+'payload'+str(w),'0') for w in range(3)]
  for name,field in [('vnet','vnet_id'),('ingress_node','ingress_node'),('ingress_id','ingress_node_id'),('egress_node','egress_node'),('egress_id','egress_node_id')]:add(prefix+name,f(a+'bits_flow_'+field))
  vc=add(prefix+'vc',f(a+'bits_virt_channel_id'));unit=P(dest_node)+'input_unit_'+str(input_index)+'_from_'+str(source_node)+'__DOT__';transfers.append({'valid':valid,'vc':vc,'tail':tail,'words':words,'unit':unit})
 channel('i_net0_',4,1,5,0);channel('i_net1_',6,1,5,1)
 # Ingress0 A and ingress1 C exact queue/bypass TL fields -> native NoC payload.
 for k,ch in [(0,'a'),(1,'c')]:
  base=S+'_sbus_system_bus_noc_acd_noc_nif_master_acd_3_io_flits_'+ch+'_';add('i_local'+str(k)+'_valid',f(base+'valid'));add('i_local'+str(k)+'_head',f(base+'bits_head'));add('i_local'+str(k)+'_tail',f(base+'bits_tail'))
  for w in range(3):add('i_local'+str(k)+'_payload'+str(w),'iris_full_tl_payload('+str(k)+','+str(w)+')')
  add('i_local'+str(k)+'_egress_id',f(base+'bits_egress_id') if not k else '7+2*((iris_full_tl_address(1)>>6)&3)')
 def pops(node,unit_index,from_node):
  unit=P(node)+'input_unit_'+str(unit_index)+'_from_'+str(from_node)+'__DOT__';credits=[];free=[]
  for k in range(6):
   Q=unit+'input_buffer__DOT__qs_'+str(k)+'__DOT__';pop=f(Q+'do_deq') if present(Q+'do_deq') else '0';credits.append('(uint64_t('+pop+')<<'+str(k)+')')
   tail='0'
   if present(Q+'ram_ext__DOT__Memory'):
    tail='(iris_root->'+Q+'ram_ext__DOT__Memory['+f(Q+'deq_ptr_value')+'][0]&2)'
   free.append('(uint64_t(bool('+pop+')&&bool('+tail+'))<<'+str(k)+')')
  return '('+'|'.join(credits)+')','('+'|'.join(free)+')'
 for k,(node,unit) in enumerate([(4,1),(6,1)]):
  c,v=pops(node,unit,5);add('i_credit'+str(k),c);add('i_free'+str(k),v)
 add('i_local_ready',f(S+'_sbus_system_bus_noc_acd_noc_nif_master_acd_3_io_flits_d_ready'))
 input_count=len(items)
 channel('o_net0_',5,0,4,1);channel('o_net1_',5,1,6,1)
 for k,name in [(0,'ingress_unit_2_from_6'),(1,'ingress_unit_3_from_7')]:
  q=P(5)+name+'__DOT__route_buffer__DOT__';add('o_ingress_ready'+str(k),'!(('+f(q+'wrap')+'=='+f(q+'wrap_1')+')&&'+f(q+'maybe_full')+')')
 for k,from_node in [(0,4),(1,6)]:
  c,v=pops(5,k,from_node);add('o_credit'+str(k),c);add('o_free'+str(k),v)
 loc=S+'_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_5_auto_routers_egress_nodes_out_flit_'
 for name,field in [('valid','valid'),('head','bits_head'),('tail','bits_tail')]:add('o_local_'+name,f(loc+field))
 for w in range(3):add('o_local_payload'+str(w),f(loc+'bits_payload')+'['+str(w)+']')
 for k,source in [(0,4),(1,6)]:
  I=P(5)+'input_unit_'+str(k)+'_from_'+str(source)+'__DOT__';vals='('+'|'.join('(uint64_t('+f(I+'vcalloc_vals_'+str(i))+')<<'+str(i)+')' for i in range(6))+')';ready='(('+f(P(5)+'vc_allocator__DOT__in_arb_sel')+'>>'+str(k)+')&1)';add('o_va'+str(k),'__builtin_popcountll('+vals+')-'+ready)
 add('o_va2','0');add('o_va3','0')
 for k,source in [(0,4),(1,6)]:
  I=P(5)+'input_unit_'+str(k)+'_from_'+str(source)+'__DOT__';c,_=pops(5,k,source);add('o_sa'+str(k),'__builtin_popcountll('+f(I+'salloc_arb__DOT__in_valids')+')-__builtin_popcountll('+c+')')
 add('o_sa2','0');add('o_sa3','0')
 # Exact post-write capture addresses are extra observer state, never DUT inputs.
 aux=[]
 for t,transfer in enumerate(transfers):
  for k in range(6):
   Q=transfer['unit']+'input_buffer__DOT__qs_'+str(k)+'__DOT__';deq=Q+'enq_ptr_value';push=Q+'do_enq';mem=Q+'ram_ext__DOT__Memory'
   if present(mem) and present(deq) and present(push):
    aux.append(('enq'+str(t)+'_'+str(k),f(deq)));aux.append(('push'+str(t)+'_'+str(k),f(push)))
    body='if(!b.push'+str(t)+'_'+str(k)+'||b.enq'+str(t)+'_'+str(k)+'>=5)throw std::runtime_error("Full node5 physical transfer missing accepted write");const auto &data='+f(mem)+'[b.enq'+str(t)+'_'+str(k)+'];'
    body+='b.values['+str(transfer['tail'])+']=(data[0]>>1)&1;'
    for w,idx in enumerate(transfer['words']):body+='b.values['+str(idx)+']=iris_full_bits(data,'+str(2+w*32)+','+str(32 if w<2 else 9)+');'
   else:body='throw std::runtime_error("Unobservable/untraversable physical VC transfer");'
   post.append((t,k,body))
 helper='''// Exact TL adapter packing, using public queue registers and async-sink registers.
template<class T> static uint64_t iris_full_bits(const T& v,unsigned lo,unsigned count){uint64_t result=0;for(unsigned k=0;k<count;k++)result|=uint64_t((v[(lo+k)/32]>>((lo+k)%32))&1)<<k;return result;}
static unsigned __int128 iris_full_tl(unsigned channel){
'''
 for k,ch in [(0,'a'),(1,'c')]:
  q=M+ch+'__DOT__q__DOT__';cdc=S+'sbus_coupler_from_rockettile__DOT__asink__DOT__nodeOut_'+ch+'_sink__DOT__io_deq_bits_deq_bits_reg__DOT__cdc_reg';helper+=('if(channel==0){' if k==0 else 'else{')+'const auto &q='+f(q+'ram')+';const auto &c='+f(cdc)+';const bool full='+f(q+'full')+';'
  offs={'op':(0,3,122 if not k else 114),'param':(3,3,119 if not k else 111),'size':(6,4,115 if not k else 107),'source':(10,10,108 if not k else 100),'addr':(20,35,73 if not k else 65),'data':(63 if not k else 55,64,1),'corrupt':(127 if not k else 119,1,0)}
  for name,(qo,n,co) in offs.items():helper+='uint64_t '+name+'=full?iris_full_bits(q,'+str(qo)+','+str(n)+'):iris_full_bits(c,'+str(co)+','+str(7 if name=='source' else n)+')'+('|512' if name=='source' else '')+';'
  helper+='if('+f(M+ch+'__DOT__is_body')+')return '
  if not k:helper+='(static_cast<unsigned __int128>(full?iris_full_bits(q,55,8):iris_full_bits(c,65,8))<<65)|'
  helper+='(static_cast<unsigned __int128>(data)<<1)|corrupt;return (static_cast<unsigned __int128>(op)<<52)|(static_cast<unsigned __int128>(param)<<49)|(static_cast<unsigned __int128>(size)<<45)|(static_cast<unsigned __int128>(source)<<35)|addr;}'
 helper+='}\nstatic uint64_t iris_full_tl_payload(unsigned channel,unsigned word){return uint64_t(iris_full_tl(channel)>>(32*word))&(word<2?0xffffffffULL:511ULL);}\n'
 # C packet's address is still in the constant header field; body payload cannot supply it.
 ch='c';q=M+ch+'__DOT__q__DOT__';cdc=S+'sbus_coupler_from_rockettile__DOT__asink__DOT__nodeOut_c_sink__DOT__io_deq_bits_deq_bits_reg__DOT__cdc_reg';helper+='static uint64_t iris_full_tl_address(unsigned){return '+f(q+'full')+'?iris_full_bits('+f(q+'ram')+',20,35):iris_full_bits('+f(cdc)+',65,35);}\n'
 header=R/'timing/noc_full_router_observer.hpp';code=helper+'struct IrisFullRouterFrame{bool clk;uint64_t values['+str(len(items))+'];'+''.join('uint64_t '+n+';' for n,_ in aux)+'};\nstatic IrisFullRouterFrame iris_full_router_frame(){return {bool(iris_root->TestDriver__DOT__testHarness__DOT__source__DOT__clk_i),{'+','.join('uint64_t('+x['expression']+')' for x in items)+'},'+','.join(e for _,e in aux)+'};}\n'
 code+='static void iris_full_router_trace(IrisFullRouterFrame b){const auto tb=iris_root->TestDriver__DOT__trace_count;if(b.clk||!iris_root->TestDriver__DOT__testHarness__DOT__source__DOT__clk_i||tb<3)return;'
 code+='if(!b.values[0]){'
 for t,tr in enumerate(transfers):
  code+='if(b.values['+str(tr['valid'])+']){switch(b.values['+str(tr['vc'])+']){'
  for tt,k,body in post:
   if tt==t:code+='case '+str(k)+':{'+body+'}break;'
  code+='default:throw std::runtime_error("Physical VC out of range");}}'
 code+='}fprintf(stderr,"RTL_FULL_ROUTER %lu",tb);for(auto x:b.values)fprintf(stderr,",%lx",x);fputc(\'\\n\',stderr);}\n';header.write_text(code)
 schema=R/'timing/noc_full_router_observer_fields.json';schema.write_text(json.dumps({'input_count':input_count,'fields':items},indent=2)+'\n');main=R/'timing/noc_full_router_observer.cpp';s=(CAP/'board/rtl-loader/va2_main.cc').read_text().replace('#include "va2_fields.inc"','#include "va2_fields.inc"\n#include "noc_full_router_observer.hpp"').replace('auto iris_va2_before=iris_va2_frame();','auto iris_va2_before=iris_va2_frame();\n        auto iris_full_router_before=iris_full_router_frame();').replace('iris_va2_trace(iris_va2_before);','iris_va2_trace(iris_va2_before);\n        iris_full_router_trace(iris_full_router_before);');main.write_text(s)
 old=json.loads((CAP/'build/rtl-loader-diag/va2-diag-build.json').read_text());OUT.mkdir();cmd=old['compile_argv'][:];cmd[cmd.index('-c')+1]=str(main);cmd[cmd.index('-o')+1]=str(OUT/'observer.o');cmd.insert(1,'-I'+str(CAP/'board/rtl-loader'));subprocess.run(cmd,check=True)
 link=old['link_argv'][:];link[1]=str(OUT/'observer.o');link[link.index('-o')+1]=str(OUT/'simulator-full-boundary')
 for k,v in enumerate(link):
  if v.endswith(('.o','.a')) and k!=1:
   original=Path(v) if Path(v).is_absolute() else R/'build/rtl-verilator/model'/v
   if original.is_relative_to(R) and (CAP/original.relative_to(R)).exists():link[k]=str(CAP/original.relative_to(R))
 subprocess.run(link,cwd=R/'build/rtl-verilator/model',check=True);files=[Path(__file__),header,schema,main,CAP/'report.json']+[Path(v) for v in link if v.endswith(('.o','.a'))];(OUT/'build.json').write_text(json.dumps({'compile_argv':cmd,'link_argv':link,'input_sha256':{str(p):sha(p) for p in files},'binary_sha256':sha(OUT/'simulator-full-boundary'),'rtl_modified':False,'physical_inputs_only':True,'network_payload_sampling':'Read-only just-accepted neighbor/own FIFO writes, preedgeVC/enqaddress; checked againstactualenqueue.','reset_binding':'!uncore reset catcher sync_0, exact generated C++ node5 sequential condition','hardware_contacted':False},indent=2)+'\n');print('fields',len(items),'inputs',input_count)
if __name__=='__main__':main()
