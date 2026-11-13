#pragma once
#include "iris_saturn_oracle.h"
#include "saturn_timing_live_bridge.hpp"
#include "../../../pipeline/empirical_engine.hpp"
#include "mmu.h"
#include <map>
#include <memory>
#include <optional>
struct iris_saturn_live_state {
 struct Command {reg_t pc;insn_fetch_t fetch;uint64_t rrd;iris::NodeId rrd_node;std::optional<iris::NodeId> front;bool accepted=false,retired=false,scalar=false;};
 std::unique_ptr<iris::saturn::SaturnLiveBridge>unit;
 std::unique_ptr<iris_saturn_oracle>oracle;
 iris::saturn::DefinedReferenceInputs inputs;
 iris::saturn::ReferenceOutputs outputs;
 std::map<std::string,unsigned>input_fields,output_fields;
 std::map<uint64_t,uint32_t>commands;
 std::map<iris::NodeId,iris_saturn_oracle::Intent>intents;
 std::optional<Command>command;
 uint64_t next_edge=0;
 bool prepared=false;uint64_t edges=0,accepted=0,retired=0,physical_vrf_bytes=0,physical_mrf_cells=0;
 std::string manifest_path,manifest_identity,elf_identity;
 std::map<std::string,uint64_t>counts;
};
