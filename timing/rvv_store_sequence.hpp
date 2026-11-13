#pragma once
#include <cstdint>
#include <optional>
#include <stdexcept>
namespace iris::rvv_store {
enum class Profile{Compute128,Rocket256};
struct Geometry {unsigned payload_bytes,VRF_groups,TL_requests,A_beats,wire_data_slot_bytes;};
Geometry aligned_geometry(Profile,unsigned payload_bytes,uint64_t address);
struct Command {
 uint32_t raw;unsigned vl,vstart,emul,vat,debug_id,vsew,mop;uint64_t token;
};
struct Inputs {
 bool reset,dispatch_valid;std::optional<Command> dispatch;
 bool data_ready,vrf_read_ready;uint64_t older_writes;unsigned vat_head;
 // These are physical peer/control inputs, not measured timing or state.
 bool environment_defined;
};
struct Payload {unsigned eg,eidx,eew,vat,debug_id;uint64_t byte_mask,read_intent,token;bool tail,oldest;};
struct Outputs {
 bool dispatch_ready,busy,read_request_valid,data_valid;bool control_defined=false;
 // Payload is deliberately absent while the source registers are unqualified.
 std::optional<Payload> payload;
 bool data_fire=false,dispatch_fire=false;
};
class Sequencer {
 public:
 explicit Sequencer(Profile p):profile_(p){if(p!=Profile::Compute128&&p!=Profile::Rocket256)throw std::invalid_argument("IRIS_STORE_SEQUENCE_UNKNOWN_CONFIGURED_PROFILE");}
 void evaluate(const Inputs&);Outputs sample()const;void commit();
 uint64_t edges()const{return edges_;}Profile profile()const{return profile_;}
 static const char*scope(){return "Configured unmasked unitstride nf1 StoreSequencer control only; queues/VRFbank arbiter/VMU/TL/CPU remain peers";}
 private:
 Profile profile_;bool active_=false,prepared_=false,reset_seen_=false;unsigned eidx_=0;
 uint64_t rintent_=0,edges_=0;std::optional<Command>command_;Inputs input_{};Outputs output_{};
 unsigned width()const{return profile_==Profile::Compute128?16:32;}
 unsigned groups()const{return profile_==Profile::Compute128?2:1;}
 void validate(const Command&)const;
};
}
