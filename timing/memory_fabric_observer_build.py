#!/usr/bin/env python3
"""Independent read-only whole-RTL trace of composed fabric physical boundaries."""
import argparse,hashlib,json,re,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];CAP=R/'build/rtl-memory-return-path-v1-final';TOOLS=Path('/scratch/eygao/iris-cy/.conda-env')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--reference',type=Path,default=R/'build/memory-fabric-reference-v1');p.add_argument('--graph',type=Path,default=R/'build/memory-fabric-graph-v1/graph.json');p.add_argument('--output',type=Path,default=R/'build/memory-fabric-observer-v1');a=p.parse_args();out=a.output.resolve();ref=a.reference.resolve();g=json.loads(a.graph.read_text())
 if out.exists():raise ValueError('fresh independent observer required')
 members=set(re.findall(r'\s(\w+);',(ref/'model/VTestDriver___024root.h').read_text()));pre='TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__';nets={}
 def visit(e):
  if e['op']=='net':
   n=e['name'];member=pre+n[len('DigitalTop/'):].replace('/','__DOT__');assert member in members,member
   if n in nets:assert nets[n]['width']==e['width']
   nets[n]={'name':n,'member':member,'width':e['width']}
  elif e['op']=='slice':visit(e['value'])
  elif e['op']=='concat':
   for v in e['values']:visit(v)
 for c in g['components'].values():
  for f in c['physical_ports']:visit(f['global'])
 out.mkdir();fields=[];expressions=[];offset=0
 for n,f in sorted(nets.items()):
  fields.append({**f,'word_offset':offset,'word_count':(f['width']+63)//64})
  if f['width']<=64:expressions.append('std::uint64_t(iris_root->'+f['member']+')');offset+=1
  else:
   for limb in range((f['width']+63)//64):
    expression='std::uint64_t(iris_root->'+f['member']+'['+str(2*limb)+'])'
    if limb*64+32<f['width']:expression+='|(std::uint64_t(iris_root->'+f['member']+'['+str(2*limb+1)+'])<<32)'
    expressions.append(expression);offset+=1
 clock='TestDriver__DOT__testHarness__DOT__source__DOT__clk_i';assert clock in members
 header='#include <array>\n#include <cstdint>\n#include <zlib.h>\nstatic gzFile iris_fabric_trace_file;\n'
 header+='struct IrisFabricFrame {bool clock;std::array<std::uint64_t,'+str(offset+1)+'>words;};\n'
 header+='static IrisFabricFrame iris_fabric_frame(){return {bool(iris_root->'+clock+'),{std::uint64_t(iris_root->TestDriver__DOT__trace_count),'+','.join(expressions)+'}};}\n'
 header+='static void iris_fabric_trace(const IrisFabricFrame&before){if(before.clock||!iris_root->'+clock+')return;if(gzwrite(iris_fabric_trace_file,before.words.data(),before.words.size()*8)!=int(before.words.size()*8))throw std::runtime_error("memory fabric trace write failed");}\n';(out/'memory_fabric_observer.hpp').write_text(header)
 source=CAP/'board/rtl-loader/main.cc'
 if not source.exists():source=R/'board/rtl-loader/main.cc'
 text=source.read_text();start=text.index('        if(iris_root->TestDriver__DOT__trace_count>=next_report)');end=text.index('        // VPI callbacks',start);text=text[:start]+text[end:]
 text=text.replace('static uint64_t iris_preloaded;','static uint64_t iris_preloaded;\n#include "memory_fabric_observer.hpp"')
 text=text.replace('    uint64_t next_report=10000;','    const char*trace_path=std::getenv("IRIS_MEMORY_FABRIC_TRACE");\n    if(!trace_path)throw std::runtime_error("IRIS_MEMORY_FABRIC_TRACE path required");\n    iris_fabric_trace_file=gzopen(trace_path,"wb1");\n    if(!iris_fabric_trace_file)throw std::runtime_error("memory fabric trace open failed");')
 text=text.replace('        topp->eval();','        auto fabric_before=iris_fabric_frame();\n        topp->eval();\n        iris_fabric_trace(fabric_before);');text=text.replace('    return 0;','    if(gzclose(iris_fabric_trace_file)!=Z_OK)throw std::runtime_error("memory fabric trace close failed");\n    return 0;');(out/'main.cc').write_text(text)
 compile=['/usr/bin/g++','-O3','-std=c++20',*['-I'+str(p)for p in [TOOLS/'riscv-tools/include',ref/'rtl',ref/'model',TOOLS/'share/verilator/include',TOOLS/'share/verilator/include/vltstd']],'-c',str(out/'main.cc'),'-o',str(out/'observer.o')]
 with(out/'compile.log').open('w')as f:status=subprocess.run(compile,stdout=f,stderr=subprocess.STDOUT).returncode
 if status:raise ValueError('observer compile failed')
 while not(ref/'build.json').exists():time.sleep(1)
 assert json.loads((ref/'build.json').read_text())['exit_status']==0
 receipt=CAP/'build/rtl-loader-diag/loader-build.json'
 if not receipt.exists():receipt=R/'build/rtl-loader-diag/loader-build.json'
 link=json.loads(receipt.read_text())['commands'][-1][:]
 for i,v in enumerate(link):
  if v.endswith('preload-main.cc.o'):link[i]=str(out/'observer.o')
  elif v.endswith('VTestDriver__ALL.a'):link[i]=str(ref/'model/VTestDriver__ALL.a')
  elif v.endswith(('.o','.a')):
   p=Path(v);p=p if p.is_absolute()else R/'build/rtl-verilator/model'/p;frozen=CAP/p.relative_to(R);link[i]=str(frozen if frozen.exists()else p)
 link[link.index('-o')+1]=str(out/'simulator-memory-fabric');link.insert(link.index('-o'),'-lz')
 with(out/'link.log').open('w')as f:status=subprocess.run(link,stdout=f,stderr=subprocess.STDOUT).returncode
 if status:raise ValueError('observer link failed')
 inputs=[Path(__file__),a.graph,source,ref/'build.json',ref/'model/VTestDriver___024root.h',ref/'memory-fabric-ports-readonly.vlt',receipt,out/'main.cc',out/'memory_fabric_observer.hpp']+[Path(x)for x in link if x.endswith(('.o','.a'))]
 result={'schema':'iris.memory_fabric_whole_rtl_observer.v1','compile_argv':compile,'link_argv':link,'input_sha256':{str(p):sha(p)for p in inputs},'fields':fields,'frame_words':offset+1,'frame_encoding':'gzip little-endian uint64: preedge trace_count, then each field at1+word_offset','clock_member':clock,'capture_before_source_rising_edge':True,'source_clock_domain_scope':'saved wholeSoC common500MHz phase; SDK still exposes explicit Rocket/uncore edges','binary_sha256':sha(out/'simulator-memory-fabric'),'RTL_logic_modified':False,'internal_state_inputs':False,'hardware_contacted':False,'timing_certified':False,'loaded_image_association_verified':False}
 (out/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'fields':len(fields),'frame_words':offset+1,'binary_sha256':result['binary_sha256'],'report_sha256':sha(out/'build.json')}))
if __name__=='__main__':main()
