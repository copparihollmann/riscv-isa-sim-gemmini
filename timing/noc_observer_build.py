#!/usr/bin/env python3
"""Build a new read-only host observer against the frozen memory-path model."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CAP=ROOT/'build/rtl-memory-return-path-v1-final'
B=ROOT/'build/noc-rtl-state-v1'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    j=json.loads((CAP/'report.json').read_text())
    if sha(CAP/'report.json')!='2e32a62c428c8f434c7893beb419da576b1e3a7ff4f4574aef41dc2c1f1dac0c':raise ValueError('Wrong frozen RTL capsule')
    old=json.loads((CAP/'build/rtl-loader-diag/va2-diag-build.json').read_text());schema=json.loads((CAP/'board/rtl-loader/noc_fields.json').read_text());fields={x['field'] for x in schema};P='TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__sbus_system_bus_noc_acd_noc_noc_router_sink_domain_5__DOT__routers__DOT__';I=P+'input_unit_0_from_4__DOT__';V=P+'vc_allocator__DOT__';E=P+'egress_unit_2_to_3__DOT__'
    def f(n):
        if n not in fields:raise ValueError('Missing exact observable: '+n)
        return 'iris_root->'+n
    def bits(exprs):return '('+'|'.join('(uint64_t('+e+')<<'+str(k)+')' for k,e in enumerate(exprs))+')'
    items=[('input_unit_mask',f(I+'mask')),('single_vc_input_mask',f(V+'mask')),('islip_output_mask',f(V+'mask_1')),('waiting_vcs',bits([f(I+'vcalloc_vals_'+str(k)) for k in range(6)])),('incoming_route_fire',f(I+'_route_arbiter_io_out_valid')),('incoming_route_vc',f(I+'_route_arbiter_io_out_bits_src_virt_id')),('eligible_input_units',bits([f(V+'in_arb_vals_'+str(k)) for k in range(4)])),('selected_eligible_output_vcs',bits([f(V+'_in_vc_sel_T_'+str(10+7*k)) for k in range(13)])),('selected_vc',f(I+'vcalloc_sel')),('input_unit_grants',f(V+'in_arb_sel')),('islip_output_selection',f(V+'sel')),('output_vc_grants',bits([f(V+'in_alloc_'+str(0 if k<6 else 1 if k<12 else 2)+'_'+str(k if k<6 else k-6 if k<12 else 0)) for k in range(13)])),('egress_empty',f(E+'channel_empty'))]
    for k in range(6):
        Q=I+'input_buffer__DOT__qs_'+str(k)+'__DOT__';items += [('vc'+str(k)+'_state',f(I+'states_'+str(k)+'_g')),('vc'+str(k)+'_head_word0',f(Q+'ram_ext__DOT__Memory')+'['+f(Q+'deq_ptr_value')+'][0]')]
    B.mkdir(parents=True,exist_ok=True)
    if (B/'observer-build.json').exists():raise ValueError('Refuse to overwrite observer build')
    header=ROOT/'timing/noc_observer.hpp';header.write_text('''// Pure read-only source-bound full arbiter boundary frame.
struct IrisNativeNoCFrame { bool clk; uint64_t values['''+str(len(items))+''']; };
static IrisNativeNoCFrame iris_native_noc_frame(){return {bool(iris_root->TestDriver__DOT__testHarness__DOT__source__DOT__clk_i),{'''+','.join('uint64_t('+e+')' for _,e in items)+'''}};}
static void iris_native_noc_trace(const IrisNativeNoCFrame &b){const auto tb=iris_root->TestDriver__DOT__trace_count;if(b.clk||!iris_root->TestDriver__DOT__testHarness__DOT__source__DOT__clk_i||iris_root->TestDriver__DOT__reset||tb<99000||tb>130000)return;fprintf(stderr,"RTL_ARB %lu",tb);for(auto x:b.values)fprintf(stderr,",%lx",x);fputc('\\n',stderr);}
''')
    fields_path=ROOT/'timing/noc_observer_fields.json';fields_path.write_text(json.dumps([{'name':n,'expression':e} for n,e in items],indent=2)+'\n')
    main=ROOT/'timing/noc_observer.cpp';s=(CAP/'board/rtl-loader/va2_main.cc').read_text().replace('#include "va2_fields.inc"','#include "va2_fields.inc"\n#include "noc_observer.hpp"').replace('auto iris_va2_before=iris_va2_frame();','auto iris_va2_before=iris_va2_frame();\n        auto iris_native_noc_before=iris_native_noc_frame();').replace('iris_va2_trace(iris_va2_before);','iris_va2_trace(iris_va2_before);\n        iris_native_noc_trace(iris_native_noc_before);');main.write_text(s)
    argv=old['compile_argv'][:];argv[argv.index('-c')+1]=str(main);argv[argv.index('-o')+1]=str(B/'observer.o');argv.insert(1,'-I'+str(CAP/'board/rtl-loader'));subprocess.run(argv,cwd=ROOT,check=True)
    link=old['link_argv'][:];link[1]=str(B/'observer.o');link[link.index('-o')+1]=str(B/'simulator-noc-boundary')
    for k,v in enumerate(link):
        if v.endswith(('.o','.a')) and k!=1:
            original=Path(v) if Path(v).is_absolute() else ROOT/'build/rtl-verilator/model'/v
            if original.is_relative_to(ROOT) and (CAP/original.relative_to(ROOT)).exists():link[k]=str(CAP/original.relative_to(ROOT))
    subprocess.run(link,cwd=ROOT/'build/rtl-verilator/model',check=True)
    paths=[main,header,fields_path,Path(__file__),CAP/'board/rtl-loader/va2_main.cc']
    for name,digest in old['input_sha256'].items():
        original=Path(name);archived=CAP/original.relative_to(ROOT)
        if sha(archived)!=digest:raise ValueError('Frozen observer input changed')
        paths.append(archived)
    for name in link:
        if name.endswith(('.o','.a')):paths.append(Path(name))
    paths += [ROOT/'build/rtl-verilator/model/VTestDriver___024root.h',ROOT/'build/rtl-verilator/model/VTestDriver.h',Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/lib/libriscv.so')]
    out={'schema':'iris.noc_boundary_observer_build.v1','source_capsule_sha256':sha(CAP/'report.json'),'compile_argv':argv,'link_argv':link,'input_sha256':{str(x):sha(x) for x in paths},'binary_sha256':sha(B/'simulator-noc-boundary'),'rtl_modified':False,'hardware_contacted':False};(B/'observer-build.json').write_text(json.dumps(out,indent=2)+'\n');print(out['binary_sha256'])
if __name__=='__main__':main()
