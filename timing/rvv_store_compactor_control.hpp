#pragma once
#include <deque>
#include <stdexcept>
namespace iris::rvv_store {
// Control-only translation of aligned nf1 Compactor(forward=false), push=pop
// width, source depth-two nonflow/nonpipe DCEQueue. No numeric data model.
class CompactorControl {
 public:
 struct Inputs{bool reset,push_valid;unsigned push_bytes;bool pop_valid;unsigned pop_bytes;bool defined;};
 struct Outputs{bool push_ready,pop_ready,push_fire,pop_fire,qualified;};
 explicit CompactorControl(unsigned bytes):width_(bytes){if(bytes!=16&&bytes!=32)throw std::invalid_argument("IRIS_COMPACTOR_CONFIGURED_WIDTH_REQUIRED");}
 void evaluate(Inputs in){if(!in.defined||!in.push_bytes||in.push_bytes>width_||!in.pop_bytes||in.pop_bytes>width_)throw std::invalid_argument("IRIS_COMPACTOR_DEFINED_ALIGNED_COUNTS_REQUIRED");if(!initialized_&&!in.reset)throw std::logic_error("IRIS_COMPACTOR_ACTUAL_RESET_REQUIRED");in_=in;const unsigned front=q_.empty()?0:q_.front();const bool deq=!q_.empty()&&width_+(in.pop_valid?in.pop_bytes:0)>=bytes_+front;out_={q_.size()<2,bytes_+front>=in.pop_bytes,false,false,initialized_};out_.push_fire=in.push_valid&&out_.push_ready;out_.pop_fire=in.pop_valid&&out_.pop_ready;deq_=deq;prepared_=true;}
 Outputs sample()const{if(!prepared_)throw std::logic_error("IRIS_COMPACTOR_SAMPLE_WITHOUT_EVALUATE");return out_;}
 void commit(){if(!prepared_)throw std::logic_error("IRIS_COMPACTOR_COMMIT_WITHOUT_EVALUATE");if(in_.reset){q_.clear();bytes_=0;initialized_=true;}else{unsigned next=bytes_+(deq_?q_.front():0)-(out_.pop_fire?in_.pop_bytes:0);if(next>width_)throw std::logic_error("IRIS_COMPACTOR_COUNT_INVARIANT");bytes_=next;if(deq_)q_.pop_front();if(out_.push_fire)q_.push_back(in_.push_bytes);}prepared_=false;}
 unsigned buffered_bytes()const{unsigned n=bytes_;for(auto b:q_)n+=b;return n;}
 bool idle()const{return q_.empty()&&!bytes_;}
 private:unsigned width_,bytes_=0;std::deque<unsigned>q_;bool initialized_=false,prepared_=false,deq_=false;Inputs in_{};Outputs out_{};
};
}
