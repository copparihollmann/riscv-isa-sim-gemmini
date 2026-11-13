#!/usr/bin/env python3
"""Read-only whole-SoC actual three-clock runtime port observer; no peer injection."""
import hashlib,json,re,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1];REF=R/'build/saturn-timing-reference-v1';OUT=R/'build/saturn-timing-rtl-v1';CAP=R/'build/opu-sequencer-component-v2-final'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 OUT.mkdir(parents=True,exist_ok=False);profiles={k:json.loads((R/'build/saturn-timing-source-v1'/k/'ports.json').read_text())for k in ['compute','rocket']};header=(REF/'model/VTestDriver___024root.h').read_text();members=set(re.findall(r'\s(\w+);',header));prefix='TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__';uncore='TestDriver__DOT__testHarness__DOT__source__DOT__clk_i';rocket=prefix+'chipyard_prcictrl_domain__DOT___clock_gater_auto_clock_gater_out_member_allClocks_tileClockGroup_rockettile_2_clock';assert uncore in members and rocket in members;counts=[sum(len(x)for x in profiles[k]['words'].values())for k in ['compute','compute','rocket']];size=max(counts);code='struct IrisSaturnFrame{bool clocks[3];uint64_t values[3]['+str(size)+'];};\nstatic IrisSaturnFrame iris_saturn_frame(){return {{bool(iris_root->'+uncore+'),bool(iris_root->'+uncore+'),bool(iris_root->'+rocket+')},{';bindings=[]
 for h in range(3):
  profile=profiles['rocket'if h==2 else'compute'];path=prefix+'tile_prci_domain'+('_'+str(h)if h else'')+'__DOT__element_reset_domain_'+('rockettile'if h==2 else'shuttle_tile')+'__DOT__vector_unit__DOT__';values=[]
  for f in profile['words']['input']+profile['words']['output']:
   member=path+f['name'];assert member in members,member;value='iris_root->'+member
   if f['width']>64:
    value='uint64_t('+value+'['+str(f['lo']//32)+'])'
    if f['word_width']>32:value+='|(uint64_t(iris_root->'+member+'['+str(f['lo']//32+1)+'])<<32)'
   values.append('uint64_t('+value+')');bindings.append({'hart':h,'field':f,'member':member})
  code+='{'+','.join(values)+'}'+(','if h<2 else'')
 code+='}};}\nstatic void iris_saturn_trace(const IrisSaturnFrame&before){const auto tb=iris_root->TestDriver__DOT__trace_count;bool after[3]={bool(iris_root->'+uncore+'),bool(iris_root->'+uncore+'),bool(iris_root->'+rocket+')};constexpr unsigned count[3]={'+','.join(map(str,counts))+'};for(unsigned h=0;h<3;h++){if(before.clocks[h]||!after[h]||tb<3)continue;fprintf(stderr,"RTL_SATURN_RUNTIME %lu,%u",tb,h);for(unsigned n=0;n<count[h];n++)fprintf(stderr,",%lx",before.values[h][n]);fputc(\'\\n\',stderr);}}\n';inc=R/'timing/saturn_timing_observer.hpp';inc.write_text(code);source=(CAP/'board/rtl-loader/main.cc').read_text();source=source.replace('static uint64_t iris_preloaded;','static uint64_t iris_preloaded;\n#include "saturn_timing_observer.hpp"').replace('        topp->eval();','        auto iris_saturn_before=iris_saturn_frame();\n        topp->eval();\n        iris_saturn_trace(iris_saturn_before);');mainfile=R/'timing/saturn_timing_observer.cpp';mainfile.write_text(source)
 old=json.loads((CAP/'build/opu-sequencer-rtl-v1/build.json').read_text());compile=old['compile_argv'][:];compile[compile.index('-c')+1]=str(mainfile);compile[compile.index('-o')+1]=str(OUT/'observer.o');compile=[x.replace(str(R/'build/opu-sequencer-reference-v1'),str(REF))for x in compile];(OUT/'compile-command.json').write_text(json.dumps(compile,indent=2)+'\n')
 with(OUT/'compile.log').open('w')as log:q=subprocess.run(compile,stdout=log,stderr=subprocess.STDOUT)
 if q.returncode:raise RuntimeError('Saturn whole-SoC observer compile failed')
 link=old['link_argv'][:];link[1]=str(OUT/'observer.o');link[link.index('-o')+1]=str(OUT/'simulator-saturn-boundary');link=[x.replace(str(R/'build/opu-sequencer-reference-v1'),str(REF))for x in link];assert(REF/'model/VTestDriver__ALL.a').exists(),'Wait for whole-SoC reference build'
 with(OUT/'link.log').open('w')as log:q=subprocess.run(link,stdout=log,stderr=subprocess.STDOUT)
 if q.returncode:raise RuntimeError('Saturn whole-SoC observer link failed')
 (OUT/'bindings.json').write_text(json.dumps(bindings,indent=2)+'\n');inputs=[Path(__file__),mainfile,inc,CAP/'board/rtl-loader/main.cc',REF/'build.json',REF/'boundary-readonly.vlt']+[R/'build/saturn-timing-source-v1'/k/'ports.json'for k in profiles]+[Path(x)for x in link if x.endswith(('.o','.a'))];report={'schema':'iris.saturn_whole_rtl_runtime_observer.v1','compile_argv':compile,'link_argv':link,'input_sha256':{str(p):sha(p)for p in inputs},'binary_sha256':sha(OUT/'simulator-saturn-boundary'),'physical_words_per_hart':counts,'source_clocks':[uncore,uncore,rocket],'RTL_logic_modified':False,'hardware_contacted':False};(OUT/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'native_sha256':report['binary_sha256'],'physical_words_per_hart':counts}))
if __name__=='__main__':main()
