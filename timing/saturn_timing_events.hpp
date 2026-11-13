#pragma once
#include "saturn_timing.hpp"
#include <array>
#include <map>
#include <optional>
#include <string>
namespace iris::saturn {
// Observer metadata only. It never drives the unit, changes a cycle or declares
// a front token to be asynchronous instruction completion.
struct VectorConfigSnapshot {
 std::uint64_t vl=0,vstart=0;unsigned sew=0,lmul_magnitude=0;
 bool illegal=false,lmul_negative=false,mask_agnostic=false,tail_agnostic=false,alternate_format=false,tile_widen=false;
 std::optional<unsigned> tile_rows,tile_k;
};
struct CommandIdentity {
 unsigned hart=0;std::uint64_t sequence=0,pc=0;std::uint32_t instruction=0;
 bool ex_fired=false;VectorConfigSnapshot config;
 std::optional<std::uint64_t> caller_config_epoch;
};
enum class EventKind {EXCandidate,EXFire,MEMKill,COMFrontToken,COMRetireLate,COMInternalReplay,COMException,WBReplay,WBFrontRetire,WBException,ScalarResponse,FFlagsUpdate,TLA,TLD,HellaRequest,SharedFPURequest,SharedFPUResponse};
struct PhysicalEvent {
 EventKind kind;unsigned hart=0;std::uint64_t edge=0;
 std::optional<CommandIdentity> command;
 // Source PC/raw for late/replay outputs do not invent an owner sequence.
 std::optional<std::uint64_t> pc;std::optional<std::uint32_t> instruction;
 unsigned source=0,opcode=0,size=0,beat=0,total_beats=0,rd=0;
 std::uint64_t request_edge=0,address=0,byte_mask=0,value=0;
 bool floating=false;
 std::array<std::uint64_t,4> data{},data_defined_mask{};
 std::array<std::array<std::uint64_t,2>,3> recoded_operands{};
 unsigned rounding_mode=0,type_in=0,type_out=0;
 bool third_operand=false,swap23=false;
};
class PhysicalEventLedger {
 public:
 explicit PhysicalEventLedger(Profile,unsigned hart);
 // Actual-reset projection only; no implicit state/snapshot seeding. Call once
 // per settled pre-edge frame that the unit will commit. epoch is
 // optional caller-owned attribution metadata, never an RTL input or readiness.
 std::vector<PhysicalEvent> observe(const ReferenceInputs&,const ReferenceOutputs&,std::optional<std::uint64_t> epoch={});
 std::uint64_t edges()const{return edge_;}
 std::size_t pending_TL_sources()const{return pending_.size();}
 const std::map<std::string,std::uint64_t>& counts()const{return counts_;}
 static std::string_view name(EventKind);
 private:
 struct Owner{unsigned opcode,size,a_seen=0,d_seen=0,a_total,d_total;std::uint64_t address,edge;};
 Profile profile_;unsigned hart_;std::uint64_t edge_=0,next_id_=0;
 bool reset_seen_=false;
 std::optional<CommandIdentity>s1_,s2_;
 std::map<std::string,unsigned> input_,output_;
 std::map<unsigned,Owner> pending_;std::map<std::string,std::uint64_t>counts_;
 std::uint64_t get(const std::map<std::string,unsigned>&,const std::vector<std::uint64_t>&,const std::string&)const;
};
}
