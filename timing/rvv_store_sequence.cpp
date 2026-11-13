#include "rvv_store_sequence.hpp"
#include <algorithm>
namespace iris::rvv_store {
Geometry aligned_geometry(Profile p,unsigned bytes,uint64_t address){
 if(p!=Profile::Compute128&&p!=Profile::Rocket256)throw std::invalid_argument("IRIS_STORE_SEQUENCE_UNKNOWN_CONFIGURED_PROFILE");
 const unsigned internal=p==Profile::Compute128?16:32,outer=p==Profile::Compute128?32:8;
 if(!bytes||bytes>256||address%internal)throw std::invalid_argument("IRIS_STORE_GEOMETRY_REQUIRES_PROBED_ALIGNED_PAYLOAD");
 const unsigned requests=(bytes+internal-1)/internal,beats=requests*((internal+outer-1)/outer);
 return {bytes,(bytes+internal-1)/internal,requests,beats,beats*outer};
}
void Sequencer::validate(const Command&c)const{
 if((c.raw&127)!=0x27||!(c.raw&(1u<<25))||(c.raw&(7u<<29))||(c.raw&(1u<<28))||((c.raw>>26)&3)||((c.raw>>20)&31)||c.mop||c.emul>3||c.vat>(profile_==Profile::Compute128?31:7)||c.debug_id>65535||c.vsew>3)
  throw std::invalid_argument("IRIS_STORE_SEQUENCE_OUTSIDE_UNMASKED_UNITSTRIDE_NF1");
 const unsigned encoded=(c.raw>>12)&7;if(encoded!=0&&encoded<5)throw std::invalid_argument("IRIS_STORE_SEQUENCE_INVALID_EEW");
 const unsigned eew=encoded&3,rd=(c.raw>>7)&31,vlmax=(32u<<c.emul)>>eew;
 if(!c.vl||c.vl>256||c.vl>vlmax||c.vstart>=c.vl||(rd&((1u<<c.emul)-1)))throw std::invalid_argument("IRIS_STORE_SEQUENCE_FRONTEND_LEGALITY_PRECONDITION");
}
void Sequencer::evaluate(const Inputs&i){
 if(!i.environment_defined)throw std::invalid_argument("IRIS_STORE_SEQUENCE_UNKNOWN_PEER_INPUT");
 if(profile_==Profile::Rocket256&&(i.older_writes>>32))throw std::invalid_argument("IRIS_STORE_SEQUENCE_OLDER_MASK_WIDTH");
 if(i.vat_head>(profile_==Profile::Compute128?31:7))throw std::invalid_argument("IRIS_STORE_SEQUENCE_VAT_WIDTH");
 if(i.dispatch_valid){if(!i.dispatch)throw std::invalid_argument("IRIS_STORE_SEQUENCE_MISSING_DISPATCH_PAYLOAD");validate(*i.dispatch);}
 if(!reset_seen_&&!i.reset)throw std::logic_error("IRIS_STORE_SEQUENCE_REQUIRES_ACTUAL_RESET");
 input_=i;output_={};output_.control_defined=reset_seen_;output_.busy=active_;output_.dispatch_ready=!active_;
 if(active_){
  const auto&c=*command_;const unsigned eew=(c.raw>>12)&3,rd=(c.raw>>7)&31,per=width()>>eew;
  const unsigned next=std::min(c.vl,((eidx_/per)+1)*per),eg=rd*groups()+((eidx_<<eew)/(profile_==Profile::Compute128?16:32));
  const uint64_t all=width()==32?0xffffffffULL:0xffffULL;const unsigned head=(eidx_<<eew)&(width()-1),tail=(next<<eew)&(width()-1);
  const uint64_t mask=(all<<head)&(tail?((1ULL<<tail)-1):all)&all;
  const bool last=next==c.vl;const uint64_t bit=1ULL<<eg;
  output_.read_request_valid=i.data_ready;output_.data_valid=!(bit&i.older_writes)&&i.vrf_read_ready;
  output_.data_fire=output_.data_valid&&i.data_ready;output_.dispatch_ready=last&&output_.data_fire;
  output_.payload=Payload{eg,eidx_,eew,c.vat,c.debug_id,mask,rintent_,c.token,last,c.vat==i.vat_head};
 }
 output_.dispatch_fire=i.dispatch_valid&&output_.dispatch_ready;prepared_=true;
}
Outputs Sequencer::sample()const{if(!prepared_)throw std::logic_error("IRIS_STORE_SEQUENCE_SAMPLE_BEFORE_EVALUATE");return output_;}
void Sequencer::commit(){
 if(!prepared_)throw std::logic_error("IRIS_STORE_SEQUENCE_COMMIT_BEFORE_EVALUATE");
 if(input_.reset){active_=false;command_.reset();rintent_=0;reset_seen_=true;}
 else if(output_.dispatch_fire){
  command_=input_.dispatch;active_=true;eidx_=command_->vstart;rintent_=0;const unsigned rd=(command_->raw>>7)&31,group=rd>>command_->emul;
  for(unsigned r=0;r<32;++r)if((r>>command_->emul)==group)for(unsigned g=0;g<groups();++g)rintent_|=1ULL<<(r*groups()+g);
 }else if(output_.data_fire){
  const auto p=*output_.payload;
  if(p.tail)active_=false;
  else{const unsigned next=std::min(command_->vl,((eidx_/(width()>>p.eew))+1)*(width()>>p.eew));if(((eidx_<<p.eew)/(profile_==Profile::Compute128?16:32))!=((next<<p.eew)/(profile_==Profile::Compute128?16:32)))rintent_&=~(1ULL<<p.eg);eidx_=next;}
 }
 ++edges_;prepared_=false;
}
}
