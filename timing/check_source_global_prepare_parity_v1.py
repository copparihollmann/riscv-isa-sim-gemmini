#!/usr/bin/env python3
"""NEW event-only observational parity of old/new source coupled evaluators."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import signal
import subprocess
import time
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb')as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()
def instrument(text):
    text=text.replace('#include "saturn_storefront_v1.hpp"','#include "saturn_storefront_v1.hpp"\n#include <fstream>\n#include <cstdlib>')
    marker='namespace U=iris::rvv_memory_boundary_v1;';assert text.count(marker)==1
    observer=r'''
namespace {
std::ofstream integration_trace;
void trace_word(std::uint64_t word){if(integration_trace)integration_trace.write(reinterpret_cast<const char*>(&word),sizeof(word));}
void trace_receipt(const T::Receipt&e){if(!integration_trace)return;trace_word(2);for(std::uint64_t v:{std::uint64_t(e.phase),std::uint64_t(e.owner.hart),std::uint64_t(e.owner.tag),e.owner.epoch,e.owner.command,e.owner.generation,e.owner.pc,std::uint64_t(e.owner.raw),std::uint64_t(e.load),std::uint64_t(e.source),std::uint64_t(e.mask),e.source_edge,e.master_tick,e.address})trace_word(v);for(unsigned n=0;n<16;++n){trace_word(e.known[n]);trace_word(e.data[n]&e.known[n]);}}
}
'''
    text=text.replace(marker,marker+observer)
    marker='    f.system.commit({edge,edge,true,f.tick%10==0});f.service.commit();';assert text.count(marker)==1
    observed=r'''
    if(integration_trace&&!f.reset){
      bool record=f.bin.ar_valid.value||f.bin.aw_valid.value||f.bin.w_valid.value||f.bout.r_valid||f.bout.b_valid;
      if(edge)for(const auto&p:clients)record|=p->get("auto_atl_out_a_valid")||p->in[p->transport->input_index("auto_atl_out_d_valid")].value.limbs[0]||p->get("io_vec_load_resp_valid")||p->get("io_vec_store_ack_valid")||p->rob_out.reserve_fire||p->rob_out.deq_fire;
      if(record){trace_word(1);trace_word(f.tick);trace_word(stage);trace_word(edge);
        for(auto v:{f.bin.ar_valid.value,std::uint64_t(f.bout.ar_ready),f.bin.aw_valid.value,std::uint64_t(f.bout.aw_ready),f.bin.w_valid.value,std::uint64_t(f.bout.w_ready),std::uint64_t(f.bout.r_valid),f.bin.r_ready.value,std::uint64_t(f.bout.b_valid),f.bin.b_ready.value})trace_word(v);
        if(f.bin.ar_valid.value)for(auto v:{f.bin.ar.address.value,f.bin.ar.id.value,f.bin.ar.len.value,f.bin.ar.size.value,f.bin.ar.burst.value,f.bin.ar.lock.value})trace_word(v);
        if(f.bin.aw_valid.value)for(auto v:{f.bin.aw.address.value,f.bin.aw.id.value,f.bin.aw.len.value,f.bin.aw.size.value,f.bin.aw.burst.value,f.bin.aw.lock.value})trace_word(v);
        if(f.bin.w_valid.value){trace_word(f.bin.w.strobe.value);trace_word(f.bin.w.last.value);std::uint64_t mask=0;for(unsigned n=0;n<8;++n)if(f.bin.w.strobe.value&(1u<<n))mask|=std::uint64_t(255)<<(8*n);trace_word(f.bin.w.data.value&mask);}
        if(f.bout.r_valid){trace_word(f.bout.r_id);trace_word(f.bout.r_last);trace_word(f.bout.r_data);}if(f.bout.b_valid)trace_word(f.bout.b_id);
        if(edge)for(unsigned h=0;h<2;++h){const auto&c=*clients[h];trace_word(h);for(auto name:{"io_vec_store_req_ready","io_vec_load_req_ready","auto_atl_out_a_valid","auto_atl_out_d_ready","io_vec_store_ack_valid","io_vec_load_resp_valid","io_mem_busy"})trace_word(c.get(name));
          trace_word(c.rob_out.reserve_fire);if(c.rob_out.reserve_fire)trace_word(c.rob_out.reserve_tag);trace_word(c.rob_out.deq_fire);if(c.rob_out.deq_fire)trace_word(c.reservation_order.front());
          if(c.get("auto_atl_out_a_valid")){for(auto name:{"auto_atl_out_a_bits_opcode","auto_atl_out_a_bits_param","auto_atl_out_a_bits_size","auto_atl_out_a_bits_source","auto_atl_out_a_bits_address","auto_atl_out_a_bits_mask","auto_atl_out_a_bits_corrupt"})trace_word(c.get(name));const auto mask=c.get("auto_atl_out_a_bits_mask");const auto&data=c.out.words[c.transport->output_index("auto_atl_out_a_bits_data")];for(unsigned n=0;n<32;++n)trace_word((mask&(std::uint64_t(1)<<n))?std::uint8_t(data.limbs[n/8]>>(8*(n%8))):0);}
          if(c.get("io_vec_store_ack_valid"))trace_word(c.get("io_vec_store_ack_bits_tag"));if(c.get("io_vec_load_resp_valid")){trace_word(c.get("io_vec_load_resp_bits_tag"));const auto&data=c.out.words[c.transport->output_index("io_vec_load_resp_bits_data")];trace_word(data.limbs[0]);trace_word(data.limbs[1]);}
        }
      }
    }
'''
    text=text.replace(marker,observed+marker)
    marker='for(const auto&e:c.transport->last_receipts()){';assert text.count(marker)==1
    text=text.replace(marker,marker+'trace_receipt(e);')
    marker='int main(int argc,char**argv){try{';assert text.count(marker)==1
    text=text.replace(marker,marker+'if(const char*p=std::getenv("IRIS_SOURCE_INTEGRATION_TRACE"))integration_trace.open(p,std::ios::binary|std::ios::trunc);')
    return text
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--case',choices=['resident','writeback'],required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);start=time.monotonic();commands=[]
    old=ROOT/('timing/saturn_storefront_system_arena_v2.cpp'if args.case=='resident'else'timing/saturn_storefront_system_writeback_v2.cpp');new=ROOT/('timing/saturn_storefront_system_arena_v3.cpp'if args.case=='resident'else'timing/saturn_storefront_system_writeback_v3.cpp')
    reference=ROOT/('build/saturn-storefront-System-arena-check-v2/positive.stdout'if args.case=='resident'else'build/saturn-storefront-System-writeback-check-v2/positive.stdout')
    system=ROOT/'build/shuttle-memory-system-native-v6';lp=ROOT/'build/serial-memory-context-sdk-v2/fased';typed=ROOT/'build/saturn-storefront-typed-component-v1';build=json.loads((system/'build.json').read_text());includes=[typed/'sdk',*map(Path,build['required_include_directories']),lp/'sdk',ROOT/'timing'];libs=[*map(Path,build['required_static_libraries_in_link_order']),lp/'sdk/libiris_fased_service.a',typed/'sdk/libiris_saturn_storefront.a']
    sources=[Path(__file__).resolve(),old,new,reference,ROOT/'timing/shuttle_memory_coupled_fixture_v1.hpp',ROOT/'timing/shuttle_memory_system_write_v1.cpp',system/'build.json',lp/'build.json',typed/'manifest.json',*libs];inputs={str(p):sha(p)for p in sources}
    def run(name,argv,trace=None,timeout=180):
        environment=dict(os.environ);environment.pop('IRIS_SOURCE_INTEGRATION_TRACE',None)
        if trace:environment['IRIS_SOURCE_INTEGRATION_TRACE']=str(trace)
        with(out/(name+'.stdout')).open('wb')as so,(out/(name+'.stderr')).open('wb')as se:
            proc=subprocess.Popen(list(map(str,argv)),stdout=so,stderr=se,env=environment,start_new_session=True)
            try:rc=proc.wait(timeout=timeout);timed=False
            except subprocess.TimeoutExpired:
                timed=True
                try:os.killpg(proc.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:rc=proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    try:os.killpg(proc.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    rc=proc.wait()
        commands.append(dict(name=name,argv=list(map(str,argv)),exit_status=rc,timed_out=timed));return rc==0 and not timed
    passed=True
    for kind,path in [('old',old),('global',new)]:
        cpp=out/(kind+'.observational.cpp');cpp.write_text(instrument(path.read_text()));exe=out/kind
        cmd=['/usr/bin/g++','-O2','-std=c++20',*['-I'+str(p)for p in includes],'-isystem','/scratch/eygao/iris-cy/.conda-env/share/verilator/include',cpp,'-Wl,--start-group',*libs,'-Wl,--end-group','-pthread','-latomic','-o',exe]
        ok=run(kind+'-compile',cmd)
        if ok:ok=run(kind,[exe],out/(kind+'.trace.bin'))
        passed &= ok
    parity={}
    if passed:
        parity=dict(observational_old_stdout_matches_frozen_normal=(out/'old.stdout').read_bytes()==reference.read_bytes(),global_stdout_matches_old=(out/'global.stdout').read_bytes()==(out/'old.stdout').read_bytes(),event_and_receipt_trace_byte_equal=sha(out/'old.trace.bin')==sha(out/'global.trace.bin'),trace_bytes=(out/'old.trace.bin').stat().st_size,trace_sha256=sha(out/'old.trace.bin'))
        passed &= parity['observational_old_stdout_matches_frozen_normal']and parity['global_stdout_matches_old']and parity['event_and_receipt_trace_byte_equal']and parity['trace_bytes']>0
    unchanged=all(sha(p)==h for p,h in inputs.items());passed &= unchanged
    report=dict(schema='iris.source_global_prepare_parity.v1',**{'pass':bool(passed)},case=args.case,seed=1,parity=parity,commands=commands,input_sha256=inputs,inputs_unchanged=unchanged,host_seconds=time.monotonic()-start,
        observability='Events only: qualified source A/ACK/load data, source ROB reserve/release, actual AXI channels and immutable receipts with edges. Boot/unqualified/unused payload bits omitted.',
        instrumentation_timing_mutation=False,source_RTL_or_latencies_modified=False,native_or_hardware_qualification=False,hardware_contacted=False,protected_performance_labels_consumed=False)
    report['output_sha256']={str(p):sha(p)for p in out.iterdir()if p.is_file()};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(pass_=passed,report_sha256=sha(out/'report.json'),host_seconds=report['host_seconds'])));return 0 if passed else 1
if __name__=='__main__':raise SystemExit(main())
