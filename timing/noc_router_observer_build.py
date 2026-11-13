#!/usr/bin/env python3
"""Read-only native-memory cached RTL observation for one node5 return branch."""
from pathlib import Path
import hashlib,json,re,subprocess
ROOT=Path(__file__).resolve().parents[1];CAP=ROOT/'build/rtl-memory-return-path-v1-final';B=ROOT/'build/noc-router-rtl-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 if B.exists():raise ValueError('Refuse to overwrite observer build')
 if sha(CAP/'report.json')!='2e32a62c428c8f434c7893beb419da576b1e3a7ff4f4574aef41dc2c1f1dac0c':raise ValueError('Wrong cached RTL capsule')
 h=(CAP/'build/rtl-verilator/model/VTestDriver___024root.h').read_text();ns=set(re.findall(r'\s(\w+);',h));SYS='TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__';P=SYS+'sbus_system_bus_noc_acd_noc_noc_router_sink_domain_5__DOT__routers__DOT__';I=P+'input_unit_0_from_4__DOT__';E=P+'egress_unit_2_to_3__DOT__';V=P+'vc_allocator__DOT__';A=SYS+'_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_4_auto_routers_source_nodes_out_1_flit_0_';items=[]
 def f(n):
  if n not in ns:raise ValueError('Missing exact observer: '+n)
  return 'iris_root->'+n
 def add(n,e):items.append({'name':n,'expression':e})
 def bits(es):return '('+'|'.join('(uint64_t('+e+')<<'+str(i)+')' for i,e in enumerate(es))+')'
 add('arrival_valid',f(A+'valid'));add('arrival_vc',f(A+'bits_virt_channel_id'));add('arrival_dest',f(A+'bits_flow_egress_node'));add('arrival_dest_id',f(A+'bits_flow_egress_node_id'))
 for w in range(3):add('arrival_word'+str(w),'0')
 add('nif_ready',f(SYS+'_sbus_system_bus_noc_acd_noc_nif_master_acd_3_io_flits_d_ready'))
 for i,unit in [(1,'input_unit_1_from_6'),(2,'ingress_unit_2_from_6'),(3,'ingress_unit_3_from_7')]:
  add('peer'+str(i)+'_eligible',f(V+'in_arb_vals_'+str(i)));es=[]
  for k in range(13):
   m=0 if k<6 else 1 if k<12 else 2;n=k if k<6 else k-6 if k<12 else 0
   es.append(f(P+'_'+unit+'_io_vcalloc_req_bits_vc_sel_1_0') if k==6 else f(V+'in_arb_reqs_'+str(i)+'_'+str(m)+'_'+str(n)))
  add('peer'+str(i)+'_outputs',bits(es))
 add('input_mask',f(I+'mask'));add('router_mask',f(V+'mask'));add('output_mask',f(V+'mask_1'));add('switch_mask',f(I+'salloc_arb__DOT__mask'));add('switch_lock',f(I+'salloc_arb__DOT__lock_0'));add('egress_sa_mask',f(P+'switch_allocator__DOT__arbs_2__DOT__mask'));add('egress_sa_lock',f(P+'switch_allocator__DOT__arbs_2__DOT__lock_0'));add('egress_sa_valids',f(P+'switch_allocator__DOT__arbs_2__DOT__in_valids'))
 add('waiting_vcs',bits([f(I+'vcalloc_vals_'+str(k)) for k in range(6)]));add('selected_vc',f(I+'vcalloc_sel'));add('input_grants',f(V+'in_arb_sel'));add('output_grants',bits([f(V+'in_alloc_'+str(0 if k<6 else 1 if k<12 else 2)+'_'+str(k if k<6 else k-6 if k<12 else 0)) for k in range(13)]));add('route_fire',f(I+'_route_arbiter_io_out_valid'));add('route_vc',f(I+'_route_arbiter_io_out_bits_src_virt_id'))
 for i in range(6):
  Q=I+'input_buffer__DOT__qs_'+str(i)+'__DOT__'
  for name,field in [('state',I+'states_'+str(i)+'_g'),('local',I+'states_'+str(i)+'_vc_sel_2_0'),('enq',Q+'enq_ptr_value'),('deq',Q+'deq_ptr_value'),('maybe',Q+'maybe_full'),('push',Q+'do_enq'),('pop',Q+'do_deq')]:add('vc'+str(i)+'_'+name,f(field))
  for w in range(3):add('vc'+str(i)+'_head'+str(w),f(Q+'ram_ext__DOT__Memory')+'['+f(Q+'deq_ptr_value')+']['+str(w)+']')
  for slot in range(5):
   for w in range(3):add('vc'+str(i)+'_mem'+str(slot)+'_'+str(w),f(Q+'ram_ext__DOT__Memory')+'['+str(slot)+']['+str(w)+']')
 for name,field in [('empty',E+'channel_empty'),('enq',E+'q__DOT__wrap'),('deq',E+'q__DOT__wrap_1'),('maybe',E+'q__DOT__maybe_full'),('push',E+'q__DOT__do_enq'),('pop',E+'q__DOT__do_deq')]:add('egress_'+name,f(field))
 for slot in range(2):
  for w in range(3):add('egress_mem'+str(slot)+'_'+str(w),f(E+'q__DOT__ram_ext__DOT__Memory')+'['+str(slot)+']['+str(w)+']')
 O=SYS+'_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_5_auto_routers_egress_nodes_out_flit_'
 for name,field in [('valid','valid'),('head','bits_head'),('tail','bits_tail')]:add('out_'+name,f(O+field))
 for w in range(3):add('out_payload'+str(w),f(O+'bits_payload')+'['+str(w)+']')
 indices={x['name']:k for k,x in enumerate(items)}
 post='if(b.values['+str(indices['arrival_valid'])+']){switch(b.values['+str(indices['arrival_vc'])+']){'
 for i in range(6):
  post+='case '+str(i)+': if(!b.values['+str(indices['vc'+str(i)+'_push'])+'])throw std::runtime_error("NoC accepted-flit observer saw unaccepted valid arrival");'
  for w in range(3):post+='b.values['+str(indices['arrival_word'+str(w)])+']='+f(I+'input_buffer__DOT__qs_'+str(i)+'__DOT__ram_ext__DOT__Memory')+'[b.values['+str(indices['vc'+str(i)+'_enq'])+']]['+str(w)+'];'
  post+='break;'
 post+='default:throw std::runtime_error("Bad NoC arrival VC");}}'
 B.mkdir();header=ROOT/'timing/noc_router_observer.hpp';header.write_text('''// Source-specific read-only router-return snapshot and accepted-flit boundary.
struct IrisRouterFrame {bool clk; uint64_t values['''+str(len(items))+'''];};
static IrisRouterFrame iris_router_frame(){return {bool(iris_root->TestDriver__DOT__testHarness__DOT__source__DOT__clk_i),{'''+','.join('uint64_t('+x['expression']+')' for x in items)+'''}};}
static void iris_router_trace(IrisRouterFrame b){const auto tb=iris_root->TestDriver__DOT__trace_count;if(b.clk||!iris_root->TestDriver__DOT__testHarness__DOT__source__DOT__clk_i||iris_root->TestDriver__DOT__reset||tb<90000||tb>130000)return;'''+post+'''fprintf(stderr,"RTL_ROUTER %lu",tb);for(auto x:b.values)fprintf(stderr,",%lx",x);fputc('\\n',stderr);}
''')
 schema=ROOT/'timing/noc_router_observer_fields.json';schema.write_text(json.dumps(items,indent=2)+'\n');source=ROOT/'timing/noc_router_observer.cpp';s=(CAP/'board/rtl-loader/va2_main.cc').read_text().replace('#include "va2_fields.inc"','#include "va2_fields.inc"\n#include "noc_router_observer.hpp"').replace('auto iris_va2_before=iris_va2_frame();','auto iris_va2_before=iris_va2_frame();\n        auto iris_router_before=iris_router_frame();').replace('iris_va2_trace(iris_va2_before);','iris_va2_trace(iris_va2_before);\n        iris_router_trace(iris_router_before);');source.write_text(s)
 old=json.loads((CAP/'build/rtl-loader-diag/va2-diag-build.json').read_text());cmd=old['compile_argv'][:];cmd[cmd.index('-c')+1]=str(source);cmd[cmd.index('-o')+1]=str(B/'observer.o');cmd.insert(1,'-I'+str(CAP/'board/rtl-loader'));subprocess.run(cmd,check=True)
 link=old['link_argv'][:];link[1]=str(B/'observer.o');link[link.index('-o')+1]=str(B/'simulator-router-boundary')
 for k,p in enumerate(link):
  if p.endswith(('.o','.a')) and k!=1:
   original=Path(p) if Path(p).is_absolute() else ROOT/'build/rtl-verilator/model'/p
   if original.is_relative_to(ROOT) and (CAP/original.relative_to(ROOT)).exists():link[k]=str(CAP/original.relative_to(ROOT))
 subprocess.run(link,cwd=ROOT/'build/rtl-verilator/model',check=True);paths=[Path(__file__),header,schema,source]+[Path(x) for x in link if x.endswith(('.o','.a'))]+[CAP/'build/rtl-verilator/model/VTestDriver___024root.h',CAP/'report.json']
 (B/'build.json').write_text(json.dumps({'compile_argv':cmd,'link_argv':link,'input_sha256':{str(x):sha(x) for x in paths},'binary_sha256':sha(B/'simulator-router-boundary'),'rtl_modified':False,'hardware_contacted':False},indent=2)+'\n');print('fields',len(items))
if __name__=='__main__':main()
