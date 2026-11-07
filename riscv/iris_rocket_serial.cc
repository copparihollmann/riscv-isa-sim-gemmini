// New isolated native epoch. Every source domain advances at its real
// relative calendar edge; the remaining functional AXI/CBUS peers are explicit.
#include "../iris/pipeline/rocket_serial_peer.cpp"
#include "iris_timing_adapter.h"
#include "processor.h"
#include <algorithm>
#include <iomanip>
#include <limits>
#include <ostream>
namespace {
iris::fabric::Bits serial_known(unsigned width){iris::fabric::Bits b;for(unsigned n=0;n<width;++n)b.limbs[n/64]|=uint64_t(1)<<(n%64);return b;}
uint64_t serial_mask(unsigned width){return width==64?~uint64_t(0):(uint64_t(1)<<width)-1;}
}
void iris_timing_adapter::rocket_serial_initialize(){
  auto&f=rocket_frontend_;
  iris::frontend::RocketSerialPeer::Configuration cfg;
  cfg.seed=profile_.frontend_seed;cfg.frontend_reset_edges=profile_.frontend_reset_edges;cfg.system_reset_phases=profile_.serial_reset_phases;
  cfg.source_arguments={"iris-experimental-live-source-serial","+tilelink_timeout=0"};
  cfg.assertion_policy=iris::serial_memory::AssertionPolicy::SuppressOnlyWhileBothExternalResets;
  cfg.latency=profile_.serial_latency;cfg.expected_system_identity=profile_.serial_system_identity;cfg.expected_latency_identity=profile_.serial_latency_identity;
  f.serial=std::make_unique<iris::frontend::RocketSerialPeer>(cfg);
  f.serial_backing=std::make_unique<iris::frontend::SerialBacking>(profile_.fabric_initial_elf);
  f.arbiter_inputs.resize(f.serial->arbiter_input_fields().size());f.fabric_inputs.resize(f.serial->system_input_fields().size());
  for(unsigned i=0;i<f.arbiter_inputs.size();++i)f.arbiter_inputs[i].known=serial_known(f.serial->arbiter_input_fields()[i].width);
  for(unsigned i=0;i<f.fabric_inputs.size();++i)f.fabric_inputs[i].known=serial_known(f.serial->system_input_fields()[i].width);
  for(const auto&field:f.serial->latency_input_fields())f.latency_inputs.push_back({0,serial_mask(field.width)});
  f.axi_fixture=std::make_unique<iris::frontend::AxiFunctionalFixture>(cfg.latency.read_max_requests,cfg.latency.write_max_requests,
    [this](uint64_t address,unsigned bytes){return iris::frontend::AxiFunctionalFixture::Word{rocket_frontend_.serial_backing->read(address,bytes),serial_mask(bytes*8)};},
    [this](uint64_t address,unsigned bytes,uint64_t value,unsigned mask){rocket_frontend_.serial_backing->write(address,bytes,value,mask);});
  auto index_in=[this](const std::string&component,const std::string&field){return rocket_frontend_.serial->system_input_index(component,field);};
  auto index_out=[this](const std::string&component,const std::string&field){return rocket_frontend_.serial->system_output_index(component,field);};
  f.cbus_fixture=std::make_unique<iris::frontend::CbusFunctionalFixture>(index_in,index_out,profile_.fabric_first_edges,profile_.fabric_gap_edges,
    [this](uint64_t address,unsigned bytes){
      if(address>=0x10000&&address+bytes<=0x20000){const auto beat=cores_[2]->iris_frontend_read_beat(address&~uint64_t(7));
        if(!std::all_of(beat.known.begin(),beat.known.end(),[](auto k){return k==0xff;}))throw std::runtime_error("IRIS_ROCKET_SERIAL_UNKNOWN_ROM_BITS");
        return bytes==8?beat.value:(beat.value>>((address&7)*8))&serial_mask(bytes*8);}
      if(address>=0x80000000ULL)throw std::runtime_error("IRIS_ROCKET_SERIAL_DRAM_ROUTED_TO_CBUS");
      return cores_[2]->iris_fabric_external_io_read(address,bytes);
    },[this](uint64_t address,unsigned bytes,uint64_t value,uint64_t mask){
      if(address>=0x80000000ULL)throw std::runtime_error("IRIS_ROCKET_SERIAL_DRAM_ROUTED_TO_CBUS");
      cores_[2]->iris_fabric_external_io_write(address,bytes,value,mask);
    });
  clock_.configure_resource("rocket2.source-ICACHE-transaction",1);clock_.configure_resource("rocket2.source-scalar-cache",32);
  clock_.configure_resource("serial.source-AXI-read",16);clock_.configure_resource("serial.source-AXI-write",16);clock_.configure_resource("serial.synthetic-CBUS-service",64);
}
void iris_timing_adapter::rocket_serial_evaluate(){
  auto&f=rocket_frontend_;
  for(unsigned i=0;i<8;++i){const auto&p=f.inputs.pmp[i];auto set=[&](const std::string&name,uint64_t value){f.fabric_inputs[f.serial->system_input_index("rocket_cache","io_ptw_pmp_"+std::to_string(i)+"_"+name)].value=iris::fabric::Bits(value);};set("cfg_l",p.locked);set("cfg_a",p.mode);set("cfg_x",p.execute);set("cfg_w",p.write);set("cfg_r",p.read);set("addr",p.address);set("mask",p.mask);}
  const auto read=f.axi_fixture->read_payload();const auto write=f.axi_fixture->write_payload();
  auto set=[&](std::string_view name,uint64_t value){const auto fields=f.serial->latency_input_fields();for(unsigned i=0;i<fields.size();++i)if(name==fields[i].name){f.latency_inputs[i].value=value;return;}throw std::logic_error("source LP functional input missing");};
  set("tNasti_io_egressResp_rBits_data",read?read->data:0);set("tNasti_io_egressResp_rBits_id",read?read->id:0);set("tNasti_io_egressResp_rBits_last",read&&read->last);set("tNasti_io_egressResp_bBits_id",write.value_or(0));
  f.serial->evaluate({f.inputs,f.arbiter_inputs,f.fabric_inputs,f.latency_inputs});f.serial_outputs=f.serial->sample();
  f.fabric_outputs={f.serial_outputs.frontend,f.serial_outputs.arbiter,f.serial_outputs.system,f.serial_outputs.global_settle_iterations};f.outputs=f.serial_outputs.frontend;
}
void iris_timing_adapter::rocket_serial_prepare(){
  auto&f=rocket_frontend_;if(f.fabric_prepared)return;
  if(f.next_bringup_edge>clock_.now())return;
  if(f.next_bringup_edge<clock_.now()||f.next_serial_edge<clock_.now()||f.next_uncore_edge<clock_.now())throw std::logic_error("IRIS_ROCKET_SERIAL_SKIPPED_SOURCE_DOMAIN_EDGE");
  if(!f.prepared){
    f.inputs.custom_csr=0x208;f.inputs.might_request=f.might_request;f.inputs.progress=f.next_progress;
    const auto pmp=cores_[2]->iris_frontend_pmp();for(unsigned i=0;i<8;++i){const auto cfg=pmp[i].first;auto&o=f.inputs.pmp[i];o.locked=cfg&0x80;o.mode=(cfg>>3)&3;o.execute=cfg&4;o.write=cfg&2;o.read=cfg&1;o.address=pmp[i].second;const auto base=(o.address<<1)|(o.mode&1);o.mask=(((base&~(base+1))<<2)|3)&((uint64_t(1)<<35)-1);}
  }
  if(f.prepared&&profile_.rocket_scalar_memory)rocket_memory_prepare();
  f.cbus_fixture->drive(f.fabric_inputs,f.uncore_edges);f.fabric_prepared=true;rocket_serial_evaluate();
}
void iris_timing_adapter::rocket_serial_commit(){
  auto&f=rocket_frontend_;if(!f.fabric_prepared)return;
  const bool rocket=f.prepared,uncore=f.next_uncore_edge==clock_.now(),bringup=f.next_bringup_edge==clock_.now(),serial=f.next_serial_edge==clock_.now();
  if(rocket&&profile_.rocket_scalar_memory)rocket_memory_revise_kills();
  rocket_serial_evaluate();
  auto get=[&](const std::string&component,const std::string&field){return f.serial_outputs.system[f.serial->system_output_index(component,field)].limbs[0];};
  auto axi=[&](const std::string&name){return get("path","fased_axi4_mem_0_bits_"+name);};
  auto lp=[&](const std::string&name){const auto fields=f.serial->latency_output_fields();for(unsigned i=0;i<fields.size();++i)if("tNasti_io_"+name==fields[i].name)return f.serial_outputs.latency[i];throw std::logic_error("source LP output missing");};
  if(rocket){
    if(profile_.rocket_scalar_memory)rocket_memory_commit_physical();
    const bool a=f.outputs.memory_request_valid&&get("rocket_tile","_tlMasterXbar_auto_anon_in_1_a_ready"),d=get("rocket_tile","_tlMasterXbar_auto_anon_in_1_d_valid");
    if(a){if(f.source_refill)throw std::logic_error("IRIS_ROCKET_SERIAL_OVERLAPPED_ICACHE_OWNER");f.source_refill=clock_.accept_physical({2,"source-Icache-TL-Get","rocket2.source-ICACHE-transaction",0,64,0,{},"saved-Iris-Frontend+source-Serial-System-eb4cdd5a",false});f.source_refill_beats=0;f.refills.push_back({f.outputs.memory_request_address,clock_.now(),{*f.source_refill},0});}
    if(d){if(!f.source_refill)throw std::logic_error("IRIS_ROCKET_SERIAL_ICACHE_D_WITHOUT_ACCEPTED_A");f.refills.back().returned=++f.source_refill_beats;if(f.source_refill_beats==8){clock_.finish_physical(*f.source_refill);f.source_refill.reset();}}
  }
  if(uncore){const auto old=f.cbus_fixture->transactions().size();f.cbus_fixture->observe(f.serial_outputs.system,f.uncore_edges);const auto&rows=f.cbus_fixture->transactions();for(size_t i=old;i<rows.size();++i)f.service_nodes.push_back(clock_.accept_physical({2,"explicit-CBUS-functional-service","serial.synthetic-CBUS-service",0,uint64_t(1)<<rows[i].size,0,{},profile_.fabric_service_source,false}));for(auto i:f.cbus_fixture->completed_on_last_edge())clock_.finish_physical(f.service_nodes.at(i));}
  if(bringup){
    if(bool(f.axi_fixture->read_payload())!=bool(lp("tNasti_r_valid"))||bool(f.axi_fixture->write_payload())!=bool(lp("tNasti_b_valid")))throw std::runtime_error("IRIS_ROCKET_SERIAL_LP_FUNCTIONAL_EGRESS_OWNERSHIP");
    // Consume settled old responses before accepting new requests. New
    // functional egress selected below is first visible next target phase.
    if(lp("tNasti_r_valid")&&axi("r_ready")){const auto data=f.axi_fixture->read_payload();if(data->last){if(f.axi_read_nodes.empty())throw std::logic_error("AXI R has no graph owner");clock_.finish_physical(f.axi_read_nodes.front());f.axi_read_nodes.pop_front();}f.axi_fixture->consume_r();}
    if(lp("tNasti_b_valid")&&axi("b_ready")){if(f.axi_write_nodes.empty())throw std::logic_error("AXI B has no graph owner");clock_.finish_physical(f.axi_write_nodes.front());f.axi_write_nodes.pop_front();f.axi_fixture->consume_b();}
    auto request=[&](const std::string&channel){return iris::frontend::AxiFunctionalFixture::Request{axi(channel+"_bits_addr"),unsigned(axi(channel+"_bits_id")),unsigned(axi(channel+"_bits_len")),unsigned(axi(channel+"_bits_size")),unsigned(axi(channel+"_bits_burst"))};};
    if(axi("ar_valid")&&lp("tNasti_ar_ready")){const auto q=request("ar");f.axi_fixture->accept_ar(q);f.axi_read_nodes.push_back(clock_.accept_physical({2,"source-AXI-owned-read","serial.source-AXI-read",0,(uint64_t(q.len)+1)<<q.size,0,{},profile_.serial_system_identity+"+"+profile_.serial_latency_identity,false}));++f.axi_reads;}
    if(axi("aw_valid")&&lp("tNasti_aw_ready")){const auto q=request("aw");f.axi_fixture->accept_aw(q);f.axi_write_nodes.push_back(clock_.accept_physical({2,"source-AXI-owned-write","serial.source-AXI-write",0,(uint64_t(q.len)+1)<<q.size,0,{},profile_.serial_system_identity+"+"+profile_.serial_latency_identity,false}));++f.axi_writes;}
    if(axi("w_valid")&&lp("tNasti_w_ready"))f.axi_fixture->accept_w(axi("w_bits_data"),axi("w_bits_strb"),axi("w_bits_last"));
    if(lp("egressReq_r_valid"))f.axi_fixture->request_read_egress(lp("egressReq_r_bits"));if(lp("egressReq_b_valid"))f.axi_fixture->request_write_egress(lp("egressReq_b_bits"));
  }
  f.serial->commit({rocket,uncore,bringup,serial});f.fabric_prepared=false;
  if(uncore){++f.uncore_edges;f.next_uncore_edge=clock_.now()+2;}if(bringup){++f.bringup_edges;f.next_bringup_edge=clock_.now()+1;}if(serial){++f.serial_edges;f.next_serial_edge=clock_.now()+10;}
}
void iris_timing_adapter::write_rocket_serial_json(std::ostream&out)const{
  const auto&f=rocket_frontend_;const auto&p=profile_.serial_latency;
  out<<",\"rocket_source_memory_fabric\":{\"implementation\":\"source-Frontend-IBuf-HellaArbiter-L1D-CDC-NoC-L2-cork-MBUS-SerialTL-Bringup-FASED-LatencyPipe\",\"source_identity\":"<<std::quoted(profile_.serial_system_identity)<<",\"latency_source_identity\":"<<std::quoted(profile_.serial_latency_identity)<<",\"source_state_injected\":false,\"clock_units\":\"1GHz-saved-reference-virtual-phases\",\"clock_periods\":{\"rocket\":2,\"uncore\":2,\"bringup_LP\":1,\"serial\":10},\"uncore_edges\":"<<f.uncore_edges<<",\"bringup_edges\":"<<f.bringup_edges<<",\"serial_edges\":"<<f.serial_edges<<",\"LP_explicit_fixture_parameters\":{\"read_latency\":"<<p.read_latency<<",\"write_latency\":"<<p.write_latency<<",\"read_max_requests\":"<<p.read_max_requests<<",\"write_max_requests\":"<<p.write_max_requests<<"},\"AXI_functional_backing\":\"explicit-AR-snapshot-AW-W-owned-byte-strobes-conflicts-refused\",\"AXI_reads\":"<<f.axi_reads<<",\"AXI_writes\":"<<f.axi_writes<<",\"AXI_pending_reads\":"<<f.axi_fixture->read_count()<<",\"AXI_pending_writes\":"<<f.axi_fixture->write_count()<<",\"CBUS_service\":"<<std::quoted(profile_.fabric_service_source)<<",\"CBUS_first_uncore_edges\":"<<profile_.fabric_first_edges<<",\"CBUS_gap_uncore_edges\":"<<profile_.fabric_gap_edges<<",\"initial_elf\":"<<std::quoted(profile_.fabric_initial_elf)<<",\"source_memory_replays\":"<<f.memory_replays<<",\"early_load_retirements\":"<<f.early_load_retirements<<",\"late_RF_writes\":"<<f.late_rf_writes<<",\"full_FASED_functional_or_host_token_bridge\":false,\"full_internal_knownness_certified\":false,\"timing_certified\":false,\"ethan_image_association_verified\":false}";
}
