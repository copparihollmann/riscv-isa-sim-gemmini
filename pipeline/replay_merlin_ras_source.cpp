#include "frontend_rtl_peer.hpp"
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
using Ref=iris::frontend::SavedShuttleFrontend;
int main(int argc,char**argv) {
  if(argc!=2)throw std::invalid_argument("physical-input capture required");
  std::ifstream input(argv[1],std::ios::binary);if(!input)throw std::runtime_error("capture open");
  Ref peer(1,16);uint64_t edges=0,checks=0;
  auto equal=[&](auto a,auto b,const char*name) {++checks;if(a!=b)throw std::runtime_error(std::string(name)+" edge="+std::to_string(edges));};
  while(true) {
    uint64_t header[4];Ref::Inputs in;Ref::Outputs expected;
    input.read(reinterpret_cast<char*>(header),sizeof(header));
    if(input.eof()&&input.gcount()==0)break;
    if(!input||header[0]!=edges||header[1]!=sizeof(in)||header[2]!=sizeof(expected))throw std::runtime_error("capture ABI/edge");
    input.read(reinterpret_cast<char*>(&in),sizeof(in));input.read(reinterpret_cast<char*>(&expected),sizeof(expected));
    if(!input)throw std::runtime_error("truncated input");
    auto actual=peer.evaluate(in);
    if(header[3]) {
      if(input.peek()!=std::char_traits<char>::eof())throw std::runtime_error("failure not final");
      std::cout<<"{\"pass\":true,\"continuous_edges\":"<<edges<<",\"qualified_output_checks\":"<<checks
        <<",\"failure_edge_evaluated\":true,\"source_RAS_knownness_observer_required\":true}\n";
      return 0;
    }
    equal(actual.memory_request_valid,expected.memory_request_valid,"A.valid");
    if(actual.memory_request_valid)equal(actual.memory_request_address,expected.memory_request_address,"A.address");
    for(unsigned lane=0;lane<2;++lane) {
      const auto&a=actual.queue[lane];const auto&b=expected.queue[lane];equal(a.valid,b.valid,"Q.valid");
      if(!a.valid)continue;
      equal(a.pc,b.pc,"Q.pc");equal(a.raw,b.raw,"Q.raw");equal(a.expanded,b.expanded,"Q.expanded");
      equal(a.compressed,b.compressed,"Q.rvc");equal(a.edge_instruction,b.edge_instruction,"Q.edge");
      equal(a.exception,b.exception,"Q.exception");if(a.exception)equal(a.exception_cause,b.exception_cause,"Q.cause");
      equal(a.prediction_valid,b.prediction_valid,"Q.prediction");if(a.prediction_valid)equal(a.predicted_pc,b.predicted_pc,"Q.target");
      equal(a.btb_valid,b.btb_valid,"Q.BTB");if(a.btb_valid)equal(a.btb_entry,b.btb_entry,"Q.BTBentry");
      equal(a.bht_history,b.bht_history,"Q.history");equal(a.bht_value,b.bht_value,"Q.BHTvalue");
      equal(a.small_forward_branch,b.small_forward_branch,"Q.SFB");equal(a.ras_head,b.ras_head,"Q.RAShead");
    }
    peer.commit();++edges;
  }
  throw std::runtime_error("no source failure edge");
}
