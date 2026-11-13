#include "saturn_timing_events.hpp"
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
using namespace iris::saturn;
int main(int argc,char**argv){try{
 if(argc!=5)throw std::invalid_argument("profile hart physical-input physical-output");
 const auto profile=std::string(argv[1])=="compute"?Profile::Compute128:Profile::Rocket256;const unsigned hart=std::stoul(argv[2]);PhysicalEventLedger ledger(profile,hart);std::ifstream ins(argv[3]),outs(argv[4]);std::string input,output;std::uint64_t command_checks=0,payload_checks=0,mix=1469598103934665603ULL,tl_mix=1469598103934665603ULL;auto hash=[&](std::uint64_t v){mix=(mix^v)*1099511628211ULL;};auto tl_hash=[&](std::uint64_t v){tl_mix=(tl_mix^v)*1099511628211ULL;};
 while(std::getline(ins,input)){
  std::istringstream in(input);std::string op;std::uint64_t edge;in>>op>>edge;if(op!="step"||edge!=ledger.edges())throw std::invalid_argument("Noncontinuous physical event input");ReferenceInputs i;std::uint64_t word;while(in>>word)i.words.push_back(word);
  do{if(!std::getline(outs,output))throw std::invalid_argument("Missing physical event output");}while(output.rfind("SATURN_FRAME ",0));std::istringstream values(output);values>>op>>word;if(word!=edge)throw std::invalid_argument("Event output edge mismatch");ReferenceOutputs o;while(values>>word)o.words.push_back(word);
  for(const auto&e:ledger.observe(i,o,42)){
   if(e.command){const auto&c=*e.command;if(c.hart!=hart||c.caller_config_epoch!=42)throw std::runtime_error("Lost caller attribution");++command_checks;for(auto v:{std::uint64_t(e.kind),e.edge,c.sequence,std::uint64_t(c.hart),c.pc,std::uint64_t(c.instruction),std::uint64_t(c.ex_fired),c.config.vl,c.config.vstart,std::uint64_t(c.config.sew),std::uint64_t(c.config.lmul_negative),std::uint64_t(c.config.lmul_magnitude),std::uint64_t(c.config.tile_rows.value_or(255)),std::uint64_t(c.config.tile_k.value_or(255)),std::uint64_t(42)})hash(v);}
   if(e.kind==EventKind::TLA||e.kind==EventKind::TLD){if(!e.beat||e.beat>e.total_beats||e.request_edge>e.edge||e.command)throw std::runtime_error("Invalid TL event owner");++payload_checks;for(auto v:{std::uint64_t(e.kind),e.edge,std::uint64_t(e.source),std::uint64_t(e.opcode),std::uint64_t(e.size),e.address,std::uint64_t(e.beat),std::uint64_t(e.total_beats),e.request_edge,e.byte_mask})tl_hash(v);for(unsigned w=0;w<4;++w){tl_hash(e.data[w]&e.data_defined_mask[w]);tl_hash(e.data_defined_mask[w]);}}
  }
 }
 while(std::getline(outs,output))if(output.rfind("SATURN_FRAME ",0)==0)throw std::invalid_argument("Extra physical output");
 if(ledger.pending_TL_sources())throw std::runtime_error("Unreturned physical source owners");
 std::cout<<"{\"edges\":"<<ledger.edges()<<",\"pending_TL_sources_at_end\":"<<ledger.pending_TL_sources()<<",\"command_identity_checks\":"<<command_checks<<",\"command_identity_mix64\":"<<mix<<",\"TL_event_checks\":"<<payload_checks<<",\"TL_owned_data_mask_mix64\":"<<tl_mix<<",\"source_events\":{";bool first=true;for(const auto&[k,v]:ledger.counts()){if(!first)std::cout<<',';first=false;std::cout<<'\"'<<k<<"\":"<<v;}std::cout<<"}}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
