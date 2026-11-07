// Source IBuf plus explicitly experimental demand-word/predictor integration.
#include "../iris/pipeline/fast_rocket_ibuf.cpp"
#include "../iris/pipeline/fast_rocket_packets_checked.cpp"
#include "iris_timing_adapter.h"
#include "processor.h"
#include <cstdlib>
#include <iomanip>
#include <stdexcept>
void iris_timing_adapter::rocket_packet_initialize(){
 if(cores_.size()!=3||cores_[2]->get_cfg().iris_bootrom_file.empty()||cores_[2]->get_state()->pc!=0x10000)
  throw std::runtime_error("IRIS_ROCKET_PACKET_REQUIRES_THREE_HART_PHYSICAL_RESET");
 rocket_packets_=std::make_unique<iris::frontend::FastRocketPackets>(profile_.harts[2].divider,0x10000);
 if(const auto*path=std::getenv("IRIS_ROCKET_PACKET_TRACE")){rocket_packet_trace_=std::make_unique<std::ofstream>(path);if(!*rocket_packet_trace_)throw std::runtime_error("IRIS_ROCKET_PACKET_TRACE_OPEN");}
}
bool iris_timing_adapter::rocket_packet_ready(reg_t pc,const insn_fetch_t&fetch){
 auto instruction=fetch.insn;const auto bytes=instruction.length();const auto raw=uint32_t(instruction.bits())&(bytes==2?65535:0xffffffffu);
 const bool ready=rocket_packets_->prepare(clock_.now(),pc,raw,bytes,
  [this](uint64_t address){const auto value=cores_[2]->iris_frontend_read_beat(address&~7ull);const unsigned offset=address&7;uint32_t mask=0;for(unsigned i=0;i<4;++i)mask|=uint32_t(value.known[offset+i])<<(8*i);return iris::frontend::FastRocketPackets::Word{uint32_t(value.value>>(8*offset)),mask};},
  [this](uint64_t pc,uint32_t raw,unsigned bytes){const auto expanded=iris::frontend::expand_source_rvc(raw);const auto u=iris::shuttle::decode_scalar(expanded,raw,iris::shuttle::FrontendSignals::sequential_fixture());return u.cfi()?empirical_predict_legacy(2,pc,u,bytes):pc+bytes;});
 rocket_packet_waiting_=!ready;return ready;
}
void iris_timing_adapter::rocket_packet_finish(){
 if(!rocket_packets_)return;auto edge=rocket_packets_->finish(clock_.now());if(!edge||!rocket_packet_trace_)return;auto&out=*rocket_packet_trace_;
 if(edge->word){const auto&w=*edge->word;out<<"{\"event\":\"word_accept\",\"hart\":2,\"cycle\":"<<edge->tick<<",\"id\":"<<w.id<<",\"address\":"<<w.address<<",\"data\":"<<w.data<<",\"known\":"<<w.known<<"}\n";}
 if(edge->instruction){const auto&i=*edge->instruction;out<<"{\"event\":\"instruction_accept\",\"hart\":2,\"cycle\":"<<edge->tick<<",\"pc\":"<<i.pc<<",\"raw\":"<<i.raw<<",\"bytes\":"<<i.bytes<<",\"prediction\":"<<i.prediction<<",\"words\":[";for(unsigned n=0;n<i.words.size();++n){if(n)out<<',';out<<i.words[n];}out<<"]}\n";}
 if(edge->kill)out<<"{\"event\":\"redirect\",\"hart\":2,\"cycle\":"<<edge->tick<<",\"reason\":"<<std::quoted(edge->reason)<<"}\n";
}
void iris_timing_adapter::rocket_packet_redirect(reg_t pc,const char*reason,unsigned priority){if(rocket_packets_){rocket_packets_->redirect(clock_.now(),pc,reason,priority);rocket_packet_waiting_=false;}}
void iris_timing_adapter::write_rocket_packet_json(std::ostream&out)const{
 if(!rocket_packets_)return;const auto&m=rocket_packets_->metrics();out<<",\"rocket_packet_flow\":{\"enabled\":true,\"source_IBuf\":true,\"complete_Rocket_frontend\":false,\"producer\":\"experimental-demand-four-byte-word-stream\",\"predictor\":\"legacy-two-bit-BHT-target-cache-fallback\",\"cache\":\"existing-empirical-Icache-service\",\"source_edges_evaluated\":"<<m.edges<<",\"words_accepted\":"<<m.words<<",\"instructions_accepted\":"<<m.instructions<<",\"partial_parcel_edges\":"<<m.partial_edges<<",\"source_redirect_edges\":"<<m.redirects<<",\"idle_hold_observations_not_cycles\":"<<m.held_observations<<",\"preclock_reset_edges\":2,\"calibrated\":false}";
}
