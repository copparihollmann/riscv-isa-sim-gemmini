#!/usr/bin/env python3
"""Link a read-only physical-cache-port observer to the separate whole SoC."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
ROOT=Path(__file__).resolve().parents[1]
CAP=ROOT/'build/rtl-memory-return-path-v1-final'
TOOLS=Path('/scratch/eygao/iris-cy/.conda-env')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--reference',type=Path,default=ROOT/'build/cache-hierarchy-reference-v1');p.add_argument('--source',type=Path,default=ROOT/'build/cache-hierarchy-source-v1');p.add_argument('--output',type=Path,default=ROOT/'build/cache-hierarchy-observer-v1');a=p.parse_args()
    ref=a.reference.resolve();out=a.output.resolve();extraction=a.source.resolve()/'extraction.json';j=json.loads(extraction.read_text())
    if out.exists():raise ValueError('fresh observer output required')
    out.mkdir();prefix='TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__'
    descriptors=[('shuttle0','shuttle',prefix+'tile_prci_domain__DOT__element_reset_domain_shuttle_tile__DOT__dcache__DOT__'),
                 ('shuttle1','shuttle',prefix+'tile_prci_domain_1__DOT__element_reset_domain_shuttle_tile__DOT__dcache__DOT__'),
                 ('rocket2','rocket',prefix+'tile_prci_domain_2__DOT__element_reset_domain_rockettile__DOT__dcache__DOT__'),
                 ('l2','l2',prefix+'coh_wrapper__DOT__l2__DOT__')]
    members=set(re.findall(r'\s(\w+);',(ref/'model/VTestDriver___024root.h').read_text()))
    fields=[];expressions=[];word=0
    for instance,kind,prefix in descriptors:
        for port in j['components'][kind]['physical_ports']:
            member=prefix+port['name']
            if member not in members:raise ValueError('physical cache port is not visible '+member)
            fields.append(dict(port,instance=instance,kind=kind,member=member,word_offset=word,word_count=(port['width']+63)//64))
            if port['width']<=64:expressions.append('std::uint64_t(iris_root->'+member+')');word+=1
            else:
                for limb in range((port['width']+63)//64):
                    expression='std::uint64_t(iris_root->'+member+'['+str(limb*2)+'])'
                    if limb*64+32<port['width']:expression+='|(std::uint64_t(iris_root->'+member+'['+str(limb*2+1)+'])<<32)'
                    expressions.append(expression);word+=1
    clock='TestDriver__DOT__testHarness__DOT__source__DOT__clk_i'
    assert clock in members
    header='''#include <array>
#include <cstdint>
#include <zlib.h>
static gzFile iris_cache_trace_file;
'''
    header+='struct IrisCacheFrame {bool clock;std::array<std::uint64_t,'+str(word+1)+'> words;};\n'
    header+='static IrisCacheFrame iris_cache_frame(){return {bool(iris_root->'+clock+'),{std::uint64_t(iris_root->TestDriver__DOT__trace_count),'+','.join(expressions)+'}};}\n'
    header+='static void iris_cache_trace(const IrisCacheFrame& before){if(before.clock||!iris_root->'+clock+')return;if(gzwrite(iris_cache_trace_file,before.words.data(),before.words.size()*8)!=int(before.words.size()*8))throw std::runtime_error("cache trace write failed");}\n'
    (out/'cache_hierarchy_observer.hpp').write_text(header)
    main=(CAP/'board/rtl-loader/main.cc')
    if not main.exists():main=ROOT/'board/rtl-loader/main.cc'
    code=main.read_text()
    # No internal core state is needed for this physical-boundary observer.
    start=code.index('        if(iris_root->TestDriver__DOT__trace_count>=next_report)')
    stop=code.index('        // VPI callbacks',start)
    code=code[:start]+code[stop:]
    code=code.replace('static uint64_t iris_preloaded;','static uint64_t iris_preloaded;\n#include "cache_hierarchy_observer.hpp"')
    code=code.replace('    uint64_t next_report=10000;','    const char* trace_path=std::getenv("IRIS_CACHE_TRACE");\n    if(!trace_path)throw std::runtime_error("IRIS_CACHE_TRACE output path required");\n    iris_cache_trace_file=gzopen(trace_path,"wb1");\n    if(!iris_cache_trace_file)throw std::runtime_error("cache trace open failed");')
    code=code.replace('        topp->eval();','        auto cache_before=iris_cache_frame();\n        topp->eval();\n        iris_cache_trace(cache_before);')
    code=code.replace('    return 0;','    if(gzclose(iris_cache_trace_file)!=Z_OK)throw std::runtime_error("cache trace close failed");\n    return 0;')
    (out/'main.cc').write_text(code)
    include=['-I'+str(path)for path in [TOOLS/'riscv-tools/include',ref/'rtl',ref/'model',TOOLS/'share/verilator/include',TOOLS/'share/verilator/include/vltstd']]
    compile=['/usr/bin/g++','-O3','-std=c++20',*include,'-c',str(out/'main.cc'),'-o',str(out/'observer.o')]
    with(out/'compile.log').open('w')as log:q=subprocess.run(compile,stdout=log,stderr=subprocess.STDOUT)
    if q.returncode:raise RuntimeError('whole cache observer compilation failed; see compile.log')
    # The separately launched whole-RTL build owns this archive. Never link it
    # while ar is still writing it, and never edit any source or model object.
    while not(ref/'build.json').exists():time.sleep(1)
    reference=json.loads((ref/'build.json').read_text())
    if reference['exit_status']:raise RuntimeError('whole cache RTL build failed')
    loader_receipt=CAP/'build/rtl-loader-diag/loader-build.json'
    if not loader_receipt.exists():loader_receipt=ROOT/'build/rtl-loader-diag/loader-build.json'
    old=json.loads(loader_receipt.read_text())
    link=old['commands'][-1][:]
    for index,value in enumerate(link):
        if value.endswith('preload-main.cc.o'):link[index]=str(out/'observer.o')
        elif value.endswith('VTestDriver__ALL.a'):link[index]=str(ref/'model/VTestDriver__ALL.a')
        elif value.endswith(('.o','.a')):
            original=Path(value)
            if not original.is_absolute():original=ROOT/'build/rtl-verilator/model'/original
            frozen=CAP/original.relative_to(ROOT)
            link[index]=str(frozen if frozen.exists()else original)
    link[link.index('-o')+1]=str(out/'simulator-cache-boundary');link.insert(link.index('-o'),'-lz')
    with(out/'link.log').open('w')as log:q=subprocess.run(link,stdout=log,stderr=subprocess.STDOUT)
    if q.returncode:raise RuntimeError('whole cache observer link failed; see link.log')
    inputs=[Path(__file__),main,extraction,loader_receipt,ref/'build.json',ref/'cache-ports-readonly.vlt',ref/'model/VTestDriver___024root.h',out/'main.cc',out/'cache_hierarchy_observer.hpp']+[Path(x)for x in link if x.endswith(('.o','.a'))]
    report={'schema':'iris.whole_cache_boundary_observer.v1','compile_argv':compile,'link_argv':link,'input_sha256':{str(x):sha(x)for x in inputs},'fields':fields,'frame_words':word+1,'frame_encoding':'gzip little-endian uint64; first word preedge TestDriver trace_count; then fields at1+word_offset','clock_member':clock,'capture_before_rising_edge':True,'binary_sha256':sha(out/'simulator-cache-boundary'),'RTL_logic_modified':False,'internal_state_inputs':False,'hardware_contacted':False,'timing_certified':False,'loaded_fpga_image_verified':False}
    (out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'fields':len(fields),'frame_words':word+1,'binary_sha256':report['binary_sha256'],'report_sha256':sha(out/'build.json')}))
if __name__=='__main__':main()
