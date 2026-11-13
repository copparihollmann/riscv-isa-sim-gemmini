#!/usr/bin/env python3
"""Link a read-only direct physical TL observer against the separate whole RTL."""
import hashlib,json,re,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1];REF=R/'build/noc-network-reference-v1';CAP=R/'build/noc-full-router-component-v1-final';OUT=R/'build/noc-network-rtl-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 if OUT.exists():raise ValueError('Fresh observer output required')
 extraction=json.loads((R/'build/noc-network-source-v1/extraction.json').read_text());fields=extraction['physical_ports'];prefix='TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__';header=(REF/'model/VTestDriver___024root.h').read_text();members=set(re.findall(r'\s(\w+);',header));assert all(prefix+x['name']in members for x in fields)
 code='struct IrisNetworkFrame{bool clock;uint64_t values['+str(len(fields))+'];};\nstatic IrisNetworkFrame iris_network_frame(){return {bool(iris_root->TestDriver__DOT__testHarness__DOT__source__DOT__clk_i),{'+','.join('uint64_t(iris_root->'+prefix+x['name']+')'for x in fields)+'}};}\n'
 code+='static void iris_network_trace(const IrisNetworkFrame& before){const auto tb=iris_root->TestDriver__DOT__trace_count;if(before.clock||!iris_root->TestDriver__DOT__testHarness__DOT__source__DOT__clk_i||tb<3)return;fprintf(stderr,"RTL_NOC_NETWORK %lu",tb);for(auto value:before.values)fprintf(stderr,",%lx",value);fputc(\'\\n\',stderr);}\n';inc=R/'timing/noc_network_observer.hpp';inc.write_text(code)
 # Visibility preserves a previously optimized-away top-level alias instead of
 # the old async-sink internal alias. These are the exact same physical valid:
 # TLInterconnectCoupler_sbus_from_rockettile contains only the asink instance,
 # whose auto_out_a_valid connects directly to auto_tl_out_a_valid; DigitalTop
 # connects that wire to NIFmaster3.io_tilelink_a_valid. No value is fabricated.
 path_fields=R/'timing/noc_network_path_fields.inc';old_member=prefix+'sbus_coupler_from_rockettile__DOT__asink__DOT__nodeOut_a_sink__DOT__io_deq_valid_0';new_member=prefix+'_sbus_coupler_from_rockettile_auto_tl_out_a_valid';old_path=(CAP/'build/rtl-memory-return-path-v1-final/board/rtl-loader/path_fields.inc').read_text();assert old_path.count(old_member)==1 and new_member in members;path_fields.write_text(old_path.replace(old_member,new_member))
 main=R/'timing/noc_network_observer.cpp';source=(CAP/'timing/noc_full_router_observer.cpp').read_text();source=source.replace('#include "path_fields.inc"','#include "noc_network_path_fields.inc"').replace('#include "noc_full_router_observer.hpp"','#include "noc_full_router_observer.hpp"\n#include "noc_network_observer.hpp"').replace('auto iris_full_router_before=iris_full_router_frame();','auto iris_full_router_before=iris_full_router_frame();\n        auto iris_network_before=iris_network_frame();').replace('iris_full_router_trace(iris_full_router_before);','iris_full_router_trace(iris_full_router_before);\n        iris_network_trace(iris_network_before);');main.write_text(source)
 old=json.loads((CAP/'build/noc-full-router-rtl-v1/build.json').read_text());OUT.mkdir();compile=old['compile_argv'][:];compile[compile.index('-c')+1]=str(main);compile[compile.index('-o')+1]=str(OUT/'observer.o');compile=[x.replace(str(R/'build/rtl-verilator/gen-collateral'),str(REF/'rtl')).replace(str(R/'build/rtl-verilator/model'),str(REF/'model'))for x in compile];compile.insert(1,'-I'+str(CAP/'timing'));compile.insert(1,'-I'+str(CAP/'build/rtl-memory-return-path-v1-final/board/rtl-loader'))
 with(OUT/'compile.log').open('w')as log:q=subprocess.run(compile,stdout=log,stderr=subprocess.STDOUT)
 (OUT/'compile-command.json').write_text(json.dumps(compile,indent=2)+'\n')
 if q.returncode:raise RuntimeError('Whole RTL observer compilation failed; see compile.log')
 assert (REF/'model/VTestDriver__ALL.a').exists(),'Wait for reference archive completion before linking'
 link=old['link_argv'][:];link[1]=str(OUT/'observer.o');link[link.index('-o')+1]=str(OUT/'simulator-network-boundary')
 for n,x in enumerate(link):
  if x.endswith('VTestDriver__ALL.a'):link[n]=str(REF/'model/VTestDriver__ALL.a')
  elif x.endswith(('.o','.a'))and n!=1:
   original=Path(x);frozen=CAP/original.relative_to(R)
   if frozen.exists():link[n]=str(frozen)
 with(OUT/'link.log').open('w')as log:q=subprocess.run(link,stdout=log,stderr=subprocess.STDOUT)
 if q.returncode:raise RuntimeError('Whole RTL observer link failed; see link.log')
 inputs=[Path(__file__),main,inc,path_fields,REF/'build.json',REF/'boundary-readonly.vlt',REF/'rtl/TLInterconnectCoupler_sbus_from_rockettile.sv',REF/'rtl/TLAsyncCrossingSink_a35d64s7k4z4c.sv',R/'build/noc-network-source-v1/extraction.json',CAP/'report.json']+[Path(x)for x in link if x.endswith(('.o','.a'))];report={'schema':'iris.network_whole_rtl_observer.v1','compile_argv':compile,'link_argv':link,'input_sha256':{str(p):sha(p)for p in inputs},'binary_sha256':sha(OUT/'simulator-network-boundary'),'physical_input_fields':208,'physical_output_fields':295,'direct_physical_signal_reads':True,'legacy_path_alias':{'old':old_member,'new':new_member,'reason':'Exact source direct asink->coupler->NIFmaster3 physical valid alias; only observer expression changed'},'source_RTL_logic_modified':False,'internal_model_inputs_injected':False,'hardware_contacted':False};(OUT/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'fields':len(fields),'native_sha256':report['binary_sha256']}))
if __name__=='__main__':main()
