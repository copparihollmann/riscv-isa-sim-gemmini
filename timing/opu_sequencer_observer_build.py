#!/usr/bin/env python3
"""Link a read-only complete sequencer port observer against independent whole RTL."""
import hashlib,json,re,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1];REF=R/'build/opu-sequencer-reference-v1';OUT=R/'build/opu-sequencer-rtl-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 OUT.mkdir(parents=True,exist_ok=False);profile=json.loads((R/'build/opu-sequencer-native-v3/ports.json').read_text());header=(REF/'model/VTestDriver___024root.h').read_text();members=set(re.findall(r'\s(\w+);',header));prefix='TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__';allfields=profile['input']+profile['output'];assert 'assign io_wsboard = wsboard;'in(REF/'rtl/OuterProductSequencer.sv').read_text();clock='TestDriver__DOT__testHarness__DOT__source__DOT__clk_i';assert clock in members
 code='struct IrisOPUFrame{bool clock;uint64_t values[2]['+str(len(allfields))+'];};\nstatic IrisOPUFrame iris_opu_frame(){return {bool(iris_root->'+clock+'),{'
 bindings=[]
 for h in range(2):
  path=prefix+'tile_prci_domain'+('_1'if h else'')+'__DOT__element_reset_domain_shuttle_tile__DOT__vector_unit__DOT__vu__DOT__vos__DOT__';values=[]
  for f in allfields:
   member=path+('wsboard'if f['port']=='io_wsboard'else f['port']);assert member in members,member
   val='iris_root->'+member
   if f['physical_width']>64:val='(uint64_t('+val+'['+str(f['lo']//32)+'])|(uint64_t('+val+'['+str(f['lo']//32+1)+'])<<32))'
   values.append('uint64_t('+val+')');bindings.append(dict(hart=h,field=f,member=member,alias_reason='Exact assign io_wsboard = wsboard'if f['port']=='io_wsboard'else None))
  code+='{'+','.join(values)+'}'+(','if h==0 else'')
 code+='}};}\nstatic void iris_opu_trace(const IrisOPUFrame&before){auto tb=iris_root->TestDriver__DOT__trace_count;if(before.clock||!iris_root->'+clock+'||tb<3)return;for(unsigned h=0;h<2;h++){fprintf(stderr,"RTL_OPU_SEQUENCER %lu,%u",tb,h);for(auto v:before.values[h])fprintf(stderr,",%lx",v);fputc(\'\\n\',stderr);}}\n';inc=R/'timing/opu_sequencer_observer.hpp';inc.write_text(code)
 source=(R/'board/rtl-loader/main.cc').read_text();source=source.replace('static uint64_t iris_preloaded;','static uint64_t iris_preloaded;\n#include "opu_sequencer_observer.hpp"').replace('        topp->eval();','        auto iris_opu_before=iris_opu_frame();\n        topp->eval();\n        iris_opu_trace(iris_opu_before);');mainfile=R/'timing/opu_sequencer_observer.cpp';mainfile.write_text(source)
 old=json.loads((R/'build/noc-network-rtl-v1/build.json').read_text());compile=old['compile_argv'][:];compile[compile.index('-c')+1]=str(mainfile);compile[compile.index('-o')+1]=str(OUT/'observer.o');compile=[x.replace(str(R/'build/noc-network-reference-v1'),str(REF))for x in compile];(OUT/'compile-command.json').write_text(json.dumps(compile,indent=2)+'\n')
 with(OUT/'compile.log').open('w')as log:q=subprocess.run(compile,stdout=log,stderr=subprocess.STDOUT)
 if q.returncode:raise RuntimeError('Observer compile failed')
 link=old['link_argv'][:];link[1]=str(OUT/'observer.o');link[link.index('-o')+1]=str(OUT/'simulator-opu-boundary');link=[x.replace(str(R/'build/noc-network-reference-v1'),str(REF))for x in link]
 with(OUT/'link.log').open('w')as log:q=subprocess.run(link,stdout=log,stderr=subprocess.STDOUT)
 if q.returncode:raise RuntimeError('Observer link failed')
 (OUT/'bindings.json').write_text(json.dumps(bindings,indent=2)+'\n');inputs=[Path(__file__),mainfile,inc,R/'board/rtl-loader/main.cc',REF/'build.json',REF/'boundary-readonly.vlt',REF/'rtl/OuterProductSequencer.sv',R/'build/opu-sequencer-native-v3/ports.json']+[Path(x)for x in link if x.endswith(('.o','.a'))];report={'schema':'iris.opu_sequencer_whole_rtl_observer.v1','compile_argv':compile,'link_argv':link,'input_sha256':{str(p):sha(p)for p in inputs},'binary_sha256':sha(OUT/'simulator-opu-boundary'),'physical_inputs_per_hart':18,'physical_output_words_per_hart':99,'clock_alias':'BothShuttleTile clocks are sbus FixedClockBroadcast_7 out2/out3, same original uncore source clk_i; no clock visibility change','wsboard_output_alias':'Exact source assign io_wsboard = wsboard; port was not public in v1 visibility config, identical retained register is read','RTL_logic_modified':False,'hardware_contacted':False};(OUT/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'binary_sha256':report['binary_sha256']}))
if __name__=='__main__':main()
