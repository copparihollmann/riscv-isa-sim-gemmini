#pragma once
#include "fased_backing_ledger_v1.hpp"
#include <fased_service.hpp>
#include <map>
#include <string>

namespace iris::fased_backing {
struct Inputs {
  Bits reset{};
  Bits ar_valid=known(1,0),aw_valid=known(1,0),w_valid=known(1,0);
  Request ar{},aw{};WBeat w{};
  Bits r_ready=known(1,0),b_ready=known(1,0);
};
struct Outputs {
  bool ar_ready=false,aw_ready=false,w_ready=false,r_valid=false,b_valid=false;
  std::uint64_t r_data=0;unsigned r_id=0,b_id=0;bool r_last=false;
  bool architectural_response_scope=false;
};
// Finite ideal-host external functional service, not full FASED ingress/egress.
// The unchanged archived LatencyPipe decides all ready/valid/due-edge timing.
// Caller supplies every accepted model-target edge; no CPU-cycle conversion.
class ServiceV2 {
  iris::fased::Model model_;
  Ledger ledger_;
  std::optional<Ledger>prepared_;
  std::vector<iris::fased::Bits>in_;
  std::vector<std::uint64_t>out_;
  std::map<std::string,unsigned>ii_,oi_;
  Outputs outputs_;
  Inputs held_input_;
  bool evaluated_=false,reset_seen_=false,evaluated_reset_=false,initialization_open_=true;

  static void require(bool value,const char*message){if(!value)throw std::runtime_error(message);}
  static std::uint64_t bits(Bits value,unsigned width){
    const auto m=mask(width);require(!(value.value&~m)&&!(value.known&~m),"IRIS_FASED_BACKING_SERVICE_EXCESS_WIDTH");
    require(value.known==m,"IRIS_FASED_BACKING_SERVICE_UNKNOWN_CONTROL_OR_METADATA");return value.value;
  }
  void set(const std::string&name,std::uint64_t value){auto&field=in_.at(ii_.at(name));field.value=value;}
  void axi(const std::string&name,std::uint64_t value){set("tNasti_io_tNasti_"+name,value);}
  std::uint64_t get(const std::string&name)const{return out_.at(oi_.at(name));}
  std::uint64_t axi(const std::string&name)const{return get("tNasti_io_tNasti_"+name);}

 public:
  ServiceV2(iris::fased::Parameters parameters,unsigned seed,std::vector<std::string>arguments,
          std::vector<Domain>domains,Visibility policy):model_(parameters,seed,std::move(arguments)),
          ledger_(std::move(domains),parameters.read_max_requests,parameters.write_max_requests,policy){
    for(auto field:model_.input_fields()){ii_.emplace(field.name,in_.size());in_.push_back({0,mask(field.width)});}
    for(auto field:model_.output_fields())oi_.emplace(field.name,oi_.size());
  }
  ServiceV2(const ServiceV2&)=delete;
  ServiceV2&operator=(const ServiceV2&)=delete;
  void initialize(std::uint64_t address,std::span<const Byte>data){require(initialization_open_&&!evaluated_,"IRIS_FASED_BACKING_SERVICE_LATE_INITIALIZATION_FORBIDDEN");ledger_.initialize(address,data);}
  void acknowledge_external_fence(){require(!evaluated_,"IRIS_FASED_BACKING_SERVICE_FENCE_DURING_HELD_PHASE");ledger_.acknowledge_external_fence();}
  const Ledger&ledger()const{return ledger_;}
  const char*source_identity()const{return model_.source_identity();}
  std::uint64_t committed_edges()const{return model_.committed_edges();}
  // A coupled fixed point may temporarily present old accepted requests. Only
  // source combinational control is evaluated here; no new ownership is yet
  // accepted. prepare() is mandatory after all peers have settled.
  void evaluate_control(const Inputs&input){
    evaluated_=false;prepared_.reset();initialization_open_=false;
    const bool reset=bits(input.reset,1),ar=bits(input.ar_valid,1),aw=bits(input.aw_valid,1),w=bits(input.w_valid,1);
    const bool rr=bits(input.r_ready,1),br=bits(input.b_ready,1);
    set("reset",reset);axi("ar_valid",ar);axi("aw_valid",aw);axi("w_valid",w);axi("r_ready",rr);axi("b_ready",br);
    for(auto pair:{std::pair<const char*,const Request*>{"ar",&input.ar},{"aw",&input.aw}}){
      const bool valid=pair.first[1]=='r'?ar:aw;const auto&r=*pair.second;
      axi(std::string(pair.first)+"_bits_len",valid?bits(r.len,8):0);
      axi(std::string(pair.first)+"_bits_burst",valid?bits(r.burst,2):0);
      axi(std::string(pair.first)+"_bits_id",valid?bits(r.id,4):0);
    }
    axi("w_bits_last",w?bits(input.w.last,1):0);
    const auto rp=ledger_.read_payload();const auto bp=ledger_.write_payload();
    set("tNasti_io_egressResp_rBits_data",rp?rp->data:0);
    set("tNasti_io_egressResp_rBits_last",rp&&rp->last);
    set("tNasti_io_egressResp_rBits_id",rp?rp->id:0);
    set("tNasti_io_egressResp_bBits_id",bp?*bp:0);
    model_.evaluate(in_);out_=model_.sample();
    outputs_={bool(axi("ar_ready")),bool(axi("aw_ready")),bool(axi("w_ready")),
              bool(axi("r_valid")),bool(axi("b_valid")),axi("r_bits_data"),unsigned(axi("r_bits_id")),
              unsigned(axi("b_bits_id")),bool(axi("r_bits_last")),!reset&&reset_seen_};
    held_input_=input;evaluated_reset_=reset;evaluated_=true;
  }
  void prepare(){
    require(evaluated_,"IRIS_FASED_BACKING_SERVICE_STALE_PREPARE");
    const auto&input=held_input_;
    const bool reset=evaluated_reset_,ar=input.ar_valid.value,aw=input.aw_valid.value,w=input.w_valid.value;
    const bool rr=input.r_ready.value,br=input.b_ready.value;
    const auto rp=ledger_.read_payload();const auto bp=ledger_.write_payload();
    try {
    auto next=ledger_;
    if(reset)next.reset(committed_edges());
    else {
      require(reset_seen_,"IRIS_FASED_BACKING_SERVICE_RESET_REQUIRED");
      require(bool(rp)==outputs_.r_valid&&bool(bp)==outputs_.b_valid,"IRIS_FASED_BACKING_SERVICE_RESPONSE_VALID_OWNER_MISMATCH");
      if(rp)require(outputs_.r_id==rp->id&&outputs_.r_data==rp->data&&outputs_.r_last==rp->last,"IRIS_FASED_BACKING_SERVICE_READ_PAYLOAD_OWNER_MISMATCH");
      if(bp)require(outputs_.b_id==*bp,"IRIS_FASED_BACKING_SERVICE_WRITE_PAYLOAD_OWNER_MISMATCH");
      Step accepted;
      if(ar&&outputs_.ar_ready)accepted.ar=input.ar;
      if(aw&&outputs_.aw_ready)accepted.aw=input.aw;
      if(w&&outputs_.w_ready)accepted.w=input.w;
      accepted.r_fire=outputs_.r_valid&&rr;accepted.b_fire=outputs_.b_valid&&br;
      if(get("tNasti_io_egressReq_r_valid"))accepted.read_egress=known(4,get("tNasti_io_egressReq_r_bits"));
      if(get("tNasti_io_egressReq_b_valid"))accepted.write_egress=known(4,get("tNasti_io_egressReq_b_bits"));
      next.advance(committed_edges(),accepted);
    }
    prepared_=std::move(next);
    }catch(...){evaluated_=false;prepared_.reset();throw;}
  }
  // Standalone convenience: supplied inputs already form a settled phase.
  void evaluate(const Inputs&input){evaluate_control(input);prepare();}
  Outputs sample()const{require(evaluated_,"IRIS_FASED_BACKING_SERVICE_STALE_SAMPLE");return outputs_;}
  std::uint64_t source_value(const std::string&name)const{require(evaluated_,"IRIS_FASED_BACKING_SERVICE_STALE_SAMPLE");return get(name);}
  void commit(){
    require(evaluated_&&bool(prepared_),"IRIS_FASED_BACKING_SERVICE_STALE_COMMIT");
    evaluated_=false;model_.commit();ledger_=std::move(*prepared_);prepared_.reset();reset_seen_|=evaluated_reset_;
    require(ledger_.committed_edges()==model_.committed_edges(),"IRIS_FASED_BACKING_SERVICE_CLOCK_DIVERGED");
  }
};
}
