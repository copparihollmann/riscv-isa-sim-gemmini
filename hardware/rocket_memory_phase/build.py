#!/usr/bin/env python3
"""Observe real Rocket WB/late-cache phases using the frozen whole-RTL model."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
ROOT=Path(__file__).resolve().parents[2]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    original=ROOT/'build/memory-fabric-observer-v1';base=json.loads((original/'build.json').read_text())
    for path,digest in base['input_sha256'].items():
        if sha(path)!=digest:raise ValueError('frozen whole-RTL input changed: '+path)
    model=ROOT/'build/memory-fabric-reference-v1/model';header=model/'VTestDriver___024root.h';text=header.read_text()
    top='TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__'
    tile=top+'tile_prci_domain_2__DOT__element_reset_domain_rockettile__DOT__';core=tile+'core__DOT__';evidence=[]
    def field(name,scope=core):
        member=scope+name
        if not re.search(r'\b'+re.escape(member)+r'\s*;',text):raise ValueError('source phase member absent: '+member)
        evidence.append(dict(name=name,cpp_member=member));return 'iris_root->'+member
    data={
      'wb_valid':field('wb_valid'),'wb_reg_valid':field('wb_reg_valid'),'wb_pc':field('wb_reg_pc'),'wb_inst':field('wb_reg_inst'),'wb_mem':field('wb_ctrl_mem'),'wb_wxd':field('wb_ctrl_wxd'),'wb_replay':field('wb_reg_replay'),'wb_xcpt':field('wb_reg_xcpt'),
      'retire':field('__Vcellinp__csr__io_retire'),'inhibit':field('csr__DOT__reg_mcountinhibit'),'instret':'('+field('csr__DOT__large_0')+'<<6)|'+field('csr__DOT__small_0'),
      'll_wen':field('ll_wen'),'ll_waddr':field('ll_waddr'),'rf_waddr':field('rf_waddr'),'rf_wdata':field('rf_wdata'),'core_dresp_valid':field('dmem_resp_valid'),'core_dresp_replay':field('dmem_resp_replay'),
      'req_valid':field('_dcacheArb_io_mem_req_valid',tile),'req_addr':field('_dcacheArb_io_mem_req_bits_addr',tile),'req_tag':field('_dcacheArb_io_mem_req_bits_tag',tile),'req_cmd':field('_dcacheArb_io_mem_req_bits_cmd',tile),'req_ready':field('_dcache_io_cpu_req_ready',tile),
      'cache_resp_valid':field('_dcache_io_cpu_resp_valid',tile),'cache_tag':field('_dcache_io_cpu_resp_bits_tag',tile),'cache_replay':field('_dcache_io_cpu_resp_bits_replay',tile),'cache_has_data':field('_dcache_io_cpu_resp_bits_has_data',tile),'cache_nack':field('_dcache_io_cpu_s2_nack',tile),
    }
    # The physical memory field is a wide array; source RegFile access is
    # rf(~register), RocketCore1373–1386. This is read-only observation.
    rf=core+'rf_ext__DOT__Memory'
    if not re.search(re.escape(rf)+r'\s*;',text):raise ValueError('source physical RF array absent')
    evidence.append(dict(name='rf',cpp_member=rf,index_mapping='reg0=constant0; reg1..31 ->31-reg',source='RocketCore.scala1373–1386'))
    clock='iris_root->TestDriver__DOT__testHarness__DOT__source__DOT__clk_i'
    code='#include <array>\n#include <cstdint>\n#include <sstream>\n#include <zlib.h>\nstatic gzFile iris_fabric_trace_file;\n'
    code+='struct IrisFabricFrame {bool clock=false;uint64_t tb=0;'+''.join('uint64_t '+k+'=0;'for k in data)+'std::array<uint64_t,32> rf{};};\n'
    code+='static IrisFabricFrame iris_fabric_frame(){IrisFabricFrame p;p.clock='+clock+';p.tb=iris_root->TestDriver__DOT__trace_count;\n'
    code+=''.join('p.'+name+'='+value+';\n'for name,value in data.items())
    code+='for(unsigned r=1;r<32;++r)p.rf[r]=iris_root->'+rf+'[31-r];return p;}\n'
    code+='static void iris_phase_json(std::ostringstream& s,const IrisFabricFrame& p){s<<"{";\n'
    for i,k in enumerate(['tb',*data]):code+='s<<"'+(''if i==0 else ',')+'\\"'+k+'\\":"<<p.'+k+';\n'
    code+='s<<",\\"rf\\":[";for(unsigned r=0;r<32;++r){if(r)s<<",";s<<p.rf[r];}s<<"]}";}\n'
    code+='static void iris_fabric_trace(const IrisFabricFrame& before){auto after=iris_fabric_frame();if(before.clock||!after.clock)return;static uint64_t edge=0;++edge;\n'
    code+='bool selected=(before.wb_valid&&before.wb_mem)||before.cache_resp_valid||before.req_valid||before.ll_wen;if(!selected)return;\n'
    code+='std::ostringstream s;s<<"{\\"edge\\":"<<edge<<",\\"before\\":";iris_phase_json(s,before);s<<",\\"after\\":";iris_phase_json(s,after);s<<"}\\n";const auto row=s.str();if(gzwrite(iris_fabric_trace_file,row.data(),row.size())!=int(row.size()))throw std::runtime_error("Rocket memory phase trace write failed");}\n'
    inc=out/'rocket_memory_phase.hpp';inc.write_text(code)
    source=original/'main.cc';main=source.read_text().replace('#include "memory_fabric_observer.hpp"','#include "rocket_memory_phase.hpp"').replace('IRIS_MEMORY_FABRIC_TRACE','IRIS_ROCKET_MEMORY_PHASE');local=out/'main.cc';local.write_text(main)
    compile=[str(local)if x==str(source)else str(out/'observer.o')if x==str(original/'observer.o')else x for x in base['compile_argv']]
    link=[str(out/'observer.o')if x==str(original/'observer.o')else str(out/'simulator-rocket-memory-phase')if x==str(original/'simulator-memory-fabric')else x for x in base['link_argv']]
    for i,argv in enumerate((compile,link)):
        r=subprocess.run(argv,text=True,capture_output=True);(out/f'build-{i}.log').write_text(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError('read-only Rocket phase observer build failed: '+r.stderr[-3500:])
    files=[Path(__file__).resolve(),original/'build.json',source,header,local,inc,ROOT/'third_party/rocket-chip/src/main/scala/rocket/RocketCore.scala',ROOT/'third_party/rocket-chip/src/main/scala/rocket/HellaCacheArbiter.scala']+[Path(x)for x in link if x.endswith(('.o','.a'))]
    report=dict(schema='iris.rocket.memory_phase_observer_build.v1',binary_sha256=sha(out/'simulator-rocket-memory-phase'),compile_argv=compile,link_argv=link,input_sha256={str(p):sha(p)for p in files},observed_fields=evidence,whole_rtl_logic_modified=False,source_read_only=True,hardware_contacted=False,timing_certified=False,loaded_image_association_verified=False,scope='Saved-Iris two-state whole-CPU memory/WB/late-result pre/post edges; same compiled whole-RTL archive and loader/TSI actors.')
    (out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status='built_read_only_Rocket_memory_phase_observer',binary_sha256=report['binary_sha256'])))
if __name__=='__main__':main()
