#ifndef SPIKE_TIMING_ROCKET_WRITEBACK_HPP
#define SPIKE_TIMING_ROCKET_WRITEBACK_HPP
#include <cstdint>
#include <optional>
#include <stdexcept>
namespace spike_timing {
// RocketCore.scala763-825 /1007-1015 and Multiplier.scala161-183.
// Inputs are actual WB/replayed-D$ response events, never an invented ROB or
// an ALU forwarding timestamp reinterpreted as a register-file write.
class RocketWriteback {
 public:
 using Cycle=std::uint64_t;
 struct Identity {std::uint64_t sequence,pc,bits;unsigned rd;};
 struct Divide {Identity instruction;Cycle accepted,valid;std::uint64_t lhs=0,rhs=0;};
 struct Normal {bool wb_reg_valid=false,wxd=false;};
 struct Replay {bool valid=false,has_data=false,xpu=false;Identity instruction{};};
 enum class Source {divide,rocc,vector,replayed_load};
 struct Write {Identity instruction;Source source;bool clears_scoreboard=true;std::optional<Divide>original_divide={};};
 private:
 std::optional<Divide>divide_;
 std::optional<Cycle>last_edge_,release_;
 static void identity(const Identity&i){if(i.rd>=32||(i.bits&3)!=3)throw std::invalid_argument("original scalar WB identity/rd");}
 public:
 bool divide_request_ready(Cycle at)const{return !divide_&&(!release_||at>=*release_);}
 bool divide_response_valid(Cycle at)const{return divide_&&at>=divide_->valid;}
 const std::optional<Divide>&pending_divide()const{return divide_;}
 void accept_divide(Divide request){
   identity(request.instruction);
   if(request.valid<=request.accepted||!divide_request_ready(request.accepted))throw std::logic_error("original single MulDiv request not ready");
   divide_=request;
 }
 std::optional<Write>edge(Cycle at,Normal normal,Replay replay,
                         std::optional<Identity>rocc={},std::optional<Identity>vector={}){
   if(at==UINT64_MAX||(last_edge_&&at<=*last_edge_))throw std::logic_error("scalar WB edge repeated, reversed or outside source clock bound");
   last_edge_=at;
   if(replay.valid&&replay.has_data&&replay.xpu){identity(replay.instruction);return Write{replay.instruction,Source::replayed_load};}
   // Source uses wb_wxd, not wb_wen: a replayed/exceptional normal WB slot
   // may still block long-latency response acceptance on this edge.
   if(normal.wb_reg_valid&&normal.wxd)return {};
   if(divide_response_valid(at)){
     const auto original=*divide_;divide_.reset();release_=at+1;
     return Write{original.instruction,Source::divide,true,original};
   }
   if(rocc){identity(*rocc);return Write{*rocc,Source::rocc};}
   if(vector){identity(*vector);return Write{*vector,Source::vector};}
   return {};
 }
};
}
#endif
