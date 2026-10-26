#ifndef SPIKE_TIMING_BITMANIP_ALU_TIMING_HPP
#define SPIKE_TIMING_BITMANIP_ALU_TIMING_HPP
#include "model.hpp"
#include <set>
#include <stdexcept>
namespace spike_timing {
// Optional selected Rocket ALU law, not a generic ISA latency. The reviewed
// decoder routes enabled Zba/Zbb/Zbs to the combinational integer ALU; its
// execute result/bypass feeds the next memory-stage register each cycle.
struct BitmanipAluService {
 static constexpr merlin_timing::Cycle latency=1,occupancy=1;
};
inline std::optional<BitmanipAluService> bitmanip_alu_service(const Model&model){
 const auto selected=model.document.get_child_optional("cpu.bitmanip_alu_service");if(!selected)return {};
 const std::set<std::string>expected{"schema","xlen","zba","zbb","zbs","execute_to_memory_stages",
   "initiation_interval","selected_isa_sha256","decode_source_sha256","alu_source_sha256","pipeline_source_sha256","rtl_sha256"};
 std::set<std::string>keys;for(const auto&e:*selected){if(!e.second.empty())throw std::invalid_argument("nested bitmanip ALU law");keys.insert(e.first);}
 const auto isa=model.document.get<std::string>("cpu.isa","");
 if(keys!=expected||selected->get<std::string>("schema")!="merlin.rocket_bitmanip_alu_service.v1"||
    selected->get<unsigned>("xlen")!=64||!selected->get<bool>("zba")||!selected->get<bool>("zbb")||!selected->get<bool>("zbs")||
    selected->get<unsigned>("execute_to_memory_stages")!=1||selected->get<unsigned>("initiation_interval")!=1||
    isa.find("_zba")==std::string::npos||isa.find("_zbb")==std::string::npos||isa.find("_zbs")==std::string::npos)
   throw std::invalid_argument("unsupported selected Rocket bitmanip ALU configuration");
 for(const auto*key:{"selected_isa_sha256","decode_source_sha256","alu_source_sha256","pipeline_source_sha256","rtl_sha256"})
   if(!is_digest(selected->get<std::string>(key)))throw std::invalid_argument("bitmanip ALU source identity unavailable");
 if(model.parameter("cpu.bitmanip.latency_cycles")||model.parameter("cpu.bitmanip.occupancy_cycles"))
   throw std::invalid_argument("source bitmanip ALU law conflicts with explicit prices");
 const auto&maps=model.document.get_child("cpu_execution_resources");const auto a=maps.find("cpu.bitmanip"),b=maps.find("cpu.integer");
 if(a==maps.not_found()||b==maps.not_found()||a->second.data()!=b->second.data())
   throw std::invalid_argument("bitmanip ALU law requires original integer resource");
 const auto id=model.resource(a->second.data());bool single=false;
 for(const auto&r:model.resources)if(id&&r.id==*id)single=r.capacity==1&&r.queue_capacity==0;
 if(!single)throw std::invalid_argument("bitmanip ALU law requires one unqueued integer ALU");
 return BitmanipAluService{};
}
}
#endif
