#!/usr/bin/env python3
"""Observe every source edge and actual cache/frontend interface inputs, without RTL edits."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[2]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--probe',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);loader=ROOT/'build/rtl-loader-diag/loader-build.json';base=json.loads(loader.read_text())
    for path,digest in base['input_sha256'].items():
        if sha(path)!=digest:raise ValueError('compiled RTL input changed: '+path)
    probe=json.loads(a.probe.read_text());bodies=probe['compiled_body_validation']
    if len(bodies)!=2 or sha(probe['elf'])!=probe['elf_sha256']:raise ValueError('probe identities changed')
    bounds=[b['counter_pcs'] for b in bodies]
    if any(len(b)!=4 for b in bounds):raise ValueError('probe counter brackets changed')
    model=ROOT/'build/rtl-verilator/model';header=model/'VTestDriver___024root.h';text=header.read_text();fields=[];snapshots=[]
    top='TestDriver__DOT__testHarness__DOT__chiptop0__DOT__system__DOT__'
    for hart in (0,1):
        tile=top+'tile_prci_domain'+('_1' if hart else '')+'__DOT__element_reset_domain_shuttle_tile__DOT__'
        def field(suffix):
            name=tile+suffix
            if not re.search(r'\b'+re.escape(name)+r'\s*;',text):raise ValueError('required observed field missing: '+name)
            fields.append(dict(hart=hart,cpp_member=name));return 'iris_root->'+name
        def core(name):return field('core__DOT__'+name)
        def front(name):return field('frontend__DOT__'+name)
        def cache(name):return front('icache__DOT__'+name)
        def counter(index):
            small=tile+'core__DOT__csr__DOT__small_'+str(index);match=re.search(r'/\*(\d+):0\*/\s*'+re.escape(small)+r'\s*;',text)
            if not match:raise ValueError('unknown source counter split width')
            return '('+core('csr__DOT__large_'+str(index))+' << '+str(int(match[1])+1)+') | '+core('csr__DOT__small_'+str(index))
        s=dict(mc=counter(1),ir=counter(0),retire0=core('com_retire_0'),retire1=core('com_retire_1'),
               com0_valid=core('com_uops_reg_0_valid'),com1_valid=core('com_uops_reg_1_valid'),
               com0_pc=core('com_uops_reg_0_bits_pc'),com1_pc=core('com_uops_reg_1_bits_pc'),
               com0_raw=core('com_uops_reg_0_bits_inst'),com1_raw=core('com_uops_reg_1_bits_inst'),
               com0_replay=core('com_uops_0_bits_needs_replay'),com1_replay=core('com_uops_1_bits_needs_replay'),
               com0_kill=core('kill_com_0'),com1_kill=core('kill_com_1'),
               deq0_valid=front('fb__DOT___out_uop_T_1397'),deq1_valid=front('fb__DOT___out_uop_T_2795'),
               rrd0_stall=core('rrd_stall_0'),rrd1_stall=core('rrd_stall_1'),ex_stall=core('ex_stall'),
               ex_busy=core('ex_bsy'),mem_busy=core('mem_bsy'),com_busy=core('com_bsy'),
               ex0_csr=core('ex_uops_reg_0_bits_ctrl_csr'),ex0_mem=core('ex_uops_reg_0_bits_ctrl_mem'),
               flush_rrd=core('flush_rrd_ex'),redirect_flush=field('_core_io_imem_redirect_flush'),
               flush_icache=field('_core_io_imem_flush_icache'),
               fetch0_pc=front('s0_vpc'),fetch1_pc=front('s1_vpc'),fetch2_pc=front('s2_vpc'),
               fetch0_valid=front('s0_valid'),fetch1_valid=front('s1_valid'),fetch2_valid=front('s2_valid'),
               fetch1_replay=front('s1_is_replay'),fetch2_replay=front('s2_is_replay'),
               fetch2_redirect=front('f2_do_redirect'),fetch2_tlb_miss=front('s2_tlb_miss'),
               fetch2_btb_valid=front('s2_btb_resp_valid'),fetch2_btb_taken=front('s2_btb_resp_bits_taken'),
               cache_response_valid=front('_icache_io_resp_valid'),cache_s1_valid=cache('s1_valid'),cache_s2_valid=cache('s2_valid'),
               cache_s2_hit=cache('s2_hit'),cache_s2_miss=cache('s2_miss'),cache_refill_request=cache('s2_request_refill'),
               cache_refill_valid=cache('refill_valid'),cache_refill_beat=cache('refill_one_beat'),cache_refill_done=cache('refill_done'),
               cache_refill_address=cache('refill_paddr'),cache_refill_counter=cache('r_counter'),
               fb_enq_valid=front('__Vcellinp__fb__io_enq_valid'),fb_enq_mask=front('__Vcellinp__fb__io_enq_bits_mask'),
               fb_enq_ptr=front('fb__DOT__enq_ptr'),fb_deq_ptr=front('fb__DOT__deq_ptr'))
        for label,suffix in {
            'cache_a_ready':'_widget_auto_anon_in_a_ready',
            'cache_s1_paddr':'frontend__DOT__s1_ppc',
            'frontend_f1_clear':'frontend__DOT__f1_clear',
            'frontend_f2_clear':'frontend__DOT__f2_clear',
            'frontend_tlb_miss':'frontend__DOT___tlb_io_resp_miss',
            'frontend_s2_ae':'frontend__DOT__s2_tlb_resp_ae_inst',
            'frontend_s2_pf':'frontend__DOT__s2_tlb_resp_pf_inst',
            'frontend_can_request_reg':'frontend__DOT__icache__DOT__s2_request_refill_REG',
            'cache_tag_match0':'frontend__DOT__icache__DOT__tagMatch',
            'cache_tag_match1':'frontend__DOT__icache__DOT__tagMatch_1',
            'cache_s0_fire':'frontend__DOT__icache__DOT__s0_ren',
            'frontend_f1_target':'frontend__DOT__f1_predicted_target',
            'frontend_f2_target':'frontend__DOT__f2_predicted_target',
            'frontend_prev_half_valid':'frontend__DOT__f2_prev_is_half',
            'frontend_prev_half':'frontend__DOT__f2_prev_half',
            'frontend_jump_reset':'frontend__DOT__jump_to_reset',
            'frontend_s0_replay':'frontend__DOT__s0_is_replay',
        }.items():s[label]=field(suffix)
        sync=top+'chipyard_prcictrl_domain__DOT__resetSynchronizer__DOT__nodeOut_member_allClocks_uncore_reset_catcher__DOT__io_sync_reset_chain__DOT__output_chain__DOT__sync_0'
        if not re.search(r'\b'+re.escape(sync)+r'\s*;',text):raise ValueError('source uncore reset output not found')
        fields.append(dict(hart=hart,cpp_member=sync));s['tile_reset']='(!iris_root->'+sync+')'
        for label,member in [('source_clock','TestDriver__DOT__testHarness__DOT__source__DOT__clk_i'),('global_reset','TestDriver__DOT__reset')]:
            if not re.search(r'\b'+re.escape(member)+r'\s*;',text):raise ValueError('source clock/reset member missing')
            fields.append(dict(hart=hart,cpp_member=member));s[label]='iris_root->'+member
        state=[cache('repl_way_prng__DOT__state_'+str(i)) for i in range(16)]
        s['cache_replacement_state']=' | '.join('('+value+' << '+str(i)+')' for i,value in enumerate(state))
        s['cache_replacement_way']=state[0]
        index='(('+s['cache_refill_address']+' >> 6) & 63)'
        words=cache('tag_array_ext__DOT__Memory')+'['+index+']'
        s['cache_index_tags']=words
        s['cache_index_tag0']='('+words+' & 0x7fffffull)'
        s['cache_index_tag1']='(('+words+' >> 23) & 0x7fffffull)'
        bits=cache('vb_array')
        for way in (0,1):
            bit='('+index+' + '+str(way*64)+')'
            s['cache_index_valid'+str(way)]='(('+bits+'['+bit+' / 32] >> ('+bit+' % 32)) & 1)'
        for i in range(7):
            s['fb_valid'+str(i)]=front('fb__DOT__ram_'+str(i)+'_valid')
            s['fb_pc'+str(i)]=front('fb__DOT__ram_'+str(i)+'_bits_pc')
        snapshots.append(s)
    names=list(snapshots[0])
    if list(snapshots[1])!=names:raise ValueError('heterogeneous Shuttle observer schema')
    code='#include <array>\n#include <cstdio>\n#include <cstdint>\n'
    code+='struct IrisFrontendSnapshot {'+''.join('uint64_t '+name+'=0;' for name in names)+'};\n'
    code+='static std::array<IrisFrontendSnapshot,2> iris_front_snapshot(){std::array<IrisFrontendSnapshot,2>a{};\n'
    for h,s in enumerate(snapshots):code+=''.join('a['+str(h)+'].'+name+'='+value+';\n' for name,value in s.items())
    code+='return a;}\nstatic void iris_front_emit(const IrisFrontendSnapshot&p){fprintf(stderr,"{");\n'
    for i,name in enumerate(names):code+='fprintf(stderr,"'+('' if i==0 else ',')+'\\"'+name+'\\":%llu",(unsigned long long)p.'+name+');\n'
    code+='fprintf(stderr,"}");}\n'
    code+='static constexpr uint64_t iris_begin[2]={'+','.join(str(b[0])+'ull' for b in bounds)+'};\n'
    code+='static constexpr uint64_t iris_end[2]={'+','.join(str(b[3])+'ull' for b in bounds)+'};\n'
    code+='static void iris_front_after(const std::array<IrisFrontendSnapshot,2>&before,uint64_t time){static int active[2]={-1,-1};static unsigned invocations[2][2]{};static unsigned tail[2]{};static uint64_t edges[2]{};auto after=iris_front_snapshot();\n'
    code+='for(unsigned h=0;h<2;++h){const auto&b=before[h];const auto&a=after[h];if(b.source_clock || !a.source_clock)continue;++edges[h];int opening=-1,closing=-1;\n'
    code+='if(b.com0_valid && b.retire0 && (b.com0_raw&127)==0x73){for(int k=0;k<2;++k){if(b.com0_pc==iris_begin[k])opening=k;if(b.com0_pc==iris_end[k])closing=k;}}\n'
    code+='if(opening>=0){active[h]=opening;++invocations[h][opening];}int kind=active[h];bool cache=b.cache_refill_request || b.cache_refill_valid || b.cache_refill_beat || a.cache_refill_valid;\n'
    code+='if(true){fprintf(stderr,"FRONT_PHASE {\\"hart\\":%u,\\"time_ps\\":%llu,\\"edge\\":%llu,\\"kind\\":%d,\\"invocation\\":%u,\\"opening\\":%d,\\"closing\\":%d,\\"before\\":",h,(unsigned long long)time,(unsigned long long)edges[h],kind,kind<0?0:invocations[h][kind],opening,closing);iris_front_emit(b);fprintf(stderr,",\\"after\\":");iris_front_emit(a);fprintf(stderr,"}\\n");}\n'
    code+='if(tail[h])--tail[h];if(closing>=0){active[h]=-1;tail[h]=4;}}}\n'
    inc=out/'frontend_fields.inc';inc.write_text(code);original=ROOT/'board/rtl-loader/main.cc';main=original.read_text()
    include='static uint64_t iris_preloaded;';marker='        topp->eval();'
    if main.count(include)!=1 or main.count(marker)!=1:raise ValueError('unexpected base loader source')
    main=main.replace(include,include+'\n#include "frontend_fields.inc"')
    main=main.replace(marker,'        const auto frontend_before=iris_front_snapshot();\n'+marker+'\n        iris_front_after(frontend_before,contextp->time());')
    local=out/'main.cc';local.write_text(main);obj=out/'main.o';binary=out/'simulator-frontend-phase'
    compile=list(base['commands'][0]);compile[compile.index(str(original))]=str(local);compile[-1]=str(obj)
    link=list(base['commands'][-1]);link[1]=str(obj);link[-1]=str(binary)
    for i,argv in enumerate((compile,link)):
        r=subprocess.run(argv,cwd=model,text=True,capture_output=True);(out/f'build-{i}.log').write_text(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError('read-only observer build failed')
    inputs={**base['input_sha256'],str(loader):sha(loader),str(a.probe.resolve()):sha(a.probe),str(Path(__file__).resolve()):sha(__file__),str(inc):sha(inc),str(local):sha(local)}
    for name in ('TestHarness','DigitalTop','TilePRCIDomain','ShuttleCore','ShuttleFrontend','ShuttleFetchBuffer','ShuttleICache','CSRFile','MaxPeriodFibonacciLFSR','tag_array_64x46','FixedClockBroadcast_7','ClockGroupAggregator_allClocks','ClockGroupCombiner','ChipyardPRCICtrlClockSinkDomain','ClockGroupResetSynchronizer','ResetCatchAndSync_d3','AsyncResetSynchronizerShiftReg_w1_d3_i0_152','AsyncResetSynchronizerPrimitiveShiftReg_d3_i0'):
        path=ROOT/'build/rtl-verilator/gen-collateral'/(name+'.sv');inputs[str(path)]=sha(path)
    for name in ('Core','Frontend','FetchBuffer','ICache'):
        path=ROOT/'third_party/shuttle/src/main/scala'/('exu' if name=='Core' else 'ifu')/(name+'.scala');inputs[str(path)]=sha(path)
    report=dict(schema='iris.frontend_observer.build.v1',binary=str(binary),binary_sha256=sha(binary),commands=[compile,link],input_sha256=inputs,
                observed_fields=fields,snapshot_fields=names,probe_elf_sha256=probe['elf_sha256'],counter_brackets=bounds,
                rtl_design_changed=False,hardware_contacted=False,observer_source_only=True,
                selection='Every observed source-clock rising edge, including reset, WFI and non-ROI activity; no counter-change gating.',
                source_read_phase='before/after eval on observed source clock risingedges, including WFI' ,calibrated=False,ethan_image_association_verified=False)
    (out/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(binary)


if __name__=='__main__':main()
