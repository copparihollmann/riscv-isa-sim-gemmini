// NEW isolated source/fabric epoch; no primary/frozen source is included by path
// mutation. External memory/service periods remain explicit synthetic fixtures.
#include "../../../pipeline/rocket_fabric_peer.cpp"
#include "../../../pipeline/rocket_fabric_fixture.cpp"
#include "../../../pipeline/rocket_dcache_arbiter.cpp"
#include "iris_timing_adapter.h"
#include "processor.h"
#include <iomanip>
#include <ostream>
namespace {
iris::fabric::Bits fabric_known(unsigned width){iris::fabric::Bits b;for(unsigned n=0;n<width;++n)b.limbs[n/64]|=uint64_t(1)<<(n%64);return b;}
}
void iris_timing_adapter::rocket_fabric_initialize(){
  auto& f=rocket_frontend_;f.fabric=std::make_unique<iris::frontend::RocketFabricPeer>(profile_.frontend_seed,profile_.frontend_reset_edges);
  f.fabric_backing=std::make_unique<iris::frontend::FabricBacking>(profile_.fabric_initial_elf);
  f.arbiter_inputs.resize(f.fabric->arbiter_input_fields().size());f.fabric_inputs.resize(f.fabric->fabric_input_fields().size());
  for(unsigned i=0;i<f.arbiter_inputs.size();++i)f.arbiter_inputs[i].known=fabric_known(f.fabric->arbiter_input_fields()[i].width);
  for(unsigned i=0;i<f.fabric_inputs.size();++i)f.fabric_inputs[i].known=fabric_known(f.fabric->fabric_input_fields()[i].width);
  f.fabric_fixture=std::make_unique<iris::frontend::RocketFabricFixture>(profile_.fabric_first_edges,profile_.fabric_gap_edges,
    [this](uint64_t address,unsigned bytes){
      if(address>=0x80000000&&address<0x180000000ULL)return rocket_frontend_.fabric_backing->read(address,bytes);
      if(address>=0x10000&&address+bytes<=0x20000){const auto beat=cores_[2]->iris_frontend_read_beat(address&~uint64_t(7));
        if(!std::all_of(beat.known.begin(),beat.known.end(),[](auto k){return k==0xff;}))throw std::runtime_error("IRIS_ROCKET_FABRIC_UNKNOWN_ROM_BITS");
        return bytes==8?beat.value:(beat.value>>((address&7)*8))&((uint64_t(1)<<(bytes*8))-1);}
      return cores_[2]->iris_fabric_external_io_read(address,bytes);
    },
    [this](uint64_t address,unsigned bytes,uint64_t value,uint64_t mask){
      if(address>=0x80000000&&address<0x180000000ULL)rocket_frontend_.fabric_backing->write(address,bytes,value,mask);
      else cores_[2]->iris_fabric_external_io_write(address,bytes,value,mask);
    });
  clock_.configure_resource("rocket2.source-ICACHE-transaction",1);clock_.configure_resource("rocket2.source-scalar-cache",32);clock_.configure_resource("fabric.external-test-service",5);
}
void iris_timing_adapter::rocket_fabric_evaluate(){
  auto& f=rocket_frontend_;
  // Frontend and Dcache observe the same source PMP control values. This
  // does not claim reset-knownness for unreset permission/address bits.
  for(unsigned i=0;i<8;++i){const auto&p=f.inputs.pmp[i];auto set=[&](const std::string&name,uint64_t value){f.fabric_inputs[iris::fabric::MemoryFabric::external_input_index("rocket_cache","io_ptw_pmp_"+std::to_string(i)+"_"+name)].value=iris::fabric::Bits(value);};set("cfg_l",p.locked);set("cfg_a",p.mode);set("cfg_x",p.execute);set("cfg_w",p.write);set("cfg_r",p.read);set("addr",p.address);set("mask",p.mask);}
  f.fabric->evaluate({f.inputs,f.arbiter_inputs,f.fabric_inputs});f.fabric_outputs=f.fabric->sample();f.outputs=f.fabric_outputs.frontend;
}
void iris_timing_adapter::rocket_fabric_prepare(){
  if(!profile_.rocket_memory_fabric)return;auto& f=rocket_frontend_;
  if(f.fabric_prepared)return;
  if(f.next_uncore_edge<clock_.now())throw std::logic_error("IRIS_ROCKET_FABRIC_SKIPPED_UNCORE_EDGE");
  if(!f.prepared&&f.next_uncore_edge!=clock_.now())return;
  if(profile_.rocket_scalar_memory)rocket_memory_prepare();
  f.fabric_fixture->drive(f.fabric_inputs,f.uncore_edges);f.fabric_prepared=true;
  rocket_fabric_evaluate();
}
void iris_timing_adapter::rocket_fabric_commit(){
  if(!profile_.rocket_memory_fabric)return;auto& f=rocket_frontend_;if(!f.fabric_prepared)return;
  const bool rocket=f.prepared,uncore=f.next_uncore_edge==clock_.now();
  if(profile_.rocket_scalar_memory)rocket_memory_revise_kills();
  rocket_fabric_evaluate();const auto& result=f.fabric_outputs;
  auto get=[&](const std::string&component,const std::string&field){return result.fabric[iris::fabric::MemoryFabric::output_index(component,field)].limbs[0];};
  if(rocket){
    if(profile_.rocket_scalar_memory)rocket_memory_commit_physical();
    const bool a=result.frontend.memory_request_valid&&get("rocket_tile","_tlMasterXbar_auto_anon_in_1_a_ready");
    const bool d=get("rocket_tile","_tlMasterXbar_auto_anon_in_1_d_valid");
    if(a){if(f.source_refill)throw std::logic_error("IRIS_ROCKET_FABRIC_OVERLAPPED_ICACHE_OWNER");
      f.source_refill=clock_.accept_physical({2,"source-Icache-TL-Get","rocket2.source-ICACHE-transaction",0,64,0,{},"saved-Iris-Frontend+source-fabric6227466f",false});f.source_refill_beats=0;
      f.refills.push_back({result.frontend.memory_request_address,clock_.now(),{*f.source_refill},0});}
    if(d){if(!f.source_refill)throw std::logic_error("IRIS_ROCKET_FABRIC_ICACHE_D_WITHOUT_ACCEPTED_A");
      f.refills.back().returned=++f.source_refill_beats;
      if(f.source_refill_beats==8){clock_.finish_physical(*f.source_refill);f.source_refill.reset();}}
  }
  if(uncore){const auto old=f.fabric_fixture->transactions().size();f.fabric_fixture->observe(result.fabric,f.uncore_edges);
    const auto& tx=f.fabric_fixture->transactions();
    for(size_t i=old;i<tx.size();++i)f.service_nodes.push_back(clock_.accept_physical({2,"explicit-external-service-transaction","fabric.external-test-service",0,uint64_t(1)<<tx[i].size,0,{},profile_.fabric_service_source,false}));
    for(auto i:f.fabric_fixture->completed_on_last_edge())clock_.finish_physical(f.service_nodes.at(i));
  }
  f.fabric->commit({rocket,uncore});f.fabric_prepared=false;
  if(uncore){++f.uncore_edges;f.next_uncore_edge=clock_.now()+profile_.fabric_uncore_divider;}
}
void iris_timing_adapter::write_rocket_fabric_json(std::ostream& out)const{
  if(!profile_.rocket_memory_fabric)return;const auto&f=rocket_frontend_;
  out<<",\"rocket_source_memory_fabric\":{\"implementation\":\"source-Frontend-IBuf-HellaArbiter-L1D-tile-width-CDC-NoC-L2-cork\",\"source_identity\":\"6227466fbb9a064a12f322928adb9e9be21ed3a403d5fa5895cb026fd6feeb42\",\"source_state_injected\":false,\"uncore_edges\":"<<f.uncore_edges<<",\"uncore_divider\":"<<profile_.fabric_uncore_divider<<",\"external_service\":\"explicit-synthetic-test-actor\",\"service_source\":"<<std::quoted(profile_.fabric_service_source)<<",\"synthetic_first_uncore_edges\":"<<profile_.fabric_first_edges<<",\"synthetic_gap_uncore_edges\":"<<profile_.fabric_gap_edges<<",\"physical_backing\":\"separate-from-Spike-mirror-ELF-PT_LOAD-and-accepted-outer-Put\",\"initial_elf\":"<<std::quoted(profile_.fabric_initial_elf)<<",\"scalar_data_CPU_path\":"<<std::quoted(profile_.rocket_scalar_memory?"experimental-source-EX-MEM-WB-scoreboard-lateRF":"unmodeled-refused")<<",\"source_memory_replays\":"<<f.memory_replays<<",\"early_load_retirements\":"<<f.early_load_retirements<<",\"late_RF_writes\":"<<f.late_rf_writes<<",\"full_internal_knownness_certified\":false,\"timing_certified\":false,\"ethan_image_association_verified\":false,\"external_transactions\":[";
  const auto&rows=f.fabric_fixture->transactions();for(size_t i=0;i<rows.size();++i){if(i)out<<',';const auto&r=rows[i];out<<"{\"node\":"<<f.service_nodes.at(i)<<",\"port\":"<<r.port<<",\"address\":"<<r.address<<",\"source\":"<<r.source<<",\"opcode\":"<<r.opcode<<",\"size\":"<<r.size<<",\"accepted_uncore_edge\":"<<r.accepted<<",\"finished_uncore_edge\":"<<(r.finished?std::to_string(r.finished):"null")<<'}';}out<<"]}";
}
