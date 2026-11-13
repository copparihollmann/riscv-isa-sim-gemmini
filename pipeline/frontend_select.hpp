#pragma once
#include <cstdint>

namespace iris::frontend {
// The source next-PC/replay/clear multiplexer. Predictor, predecode, TLB and
// cache response are explicit peer interfaces, not timing constants. This
// primitive deliberately does not claim to implement those peers.
struct ShuttleFrontendSelect {
  struct Inputs {
    bool reset=false,jump_to_reset=false;
    uint64_t reset_vector=0x10000;
    bool s1_valid=false,s2_valid=false;
    uint64_t s1_pc=0,s2_pc=0;
    bool s1_replay=false,s2_replay=false;
    bool s2_access_fault=false,s2_page_fault=false,s2_tlb_miss=false;
    bool cache_response_valid=false,queue_enqueue_ready=false;
    uint64_t f1_predicted_next=0,f2_predicted_next=0;
    bool core_redirect_flush=false,core_redirect_valid=false;
    uint64_t core_redirect_pc=0;
  };
  struct Outputs {
    bool f0_valid=false,f0_replay=false,f1_clear=false,f2_clear=false;
    uint64_t f0_pc=0;
    bool enqueue_valid=false,next_s1_valid=false,next_s2_valid=false;
    bool update_previous_half=false,clear_previous_half=false;
  };
  static Outputs evaluate(const Inputs& in) {
    Outputs o;
    if(in.s1_valid) {o.f0_valid=true;o.f0_pc=in.f1_predicted_next;}
    const bool fault=in.s2_access_fault || in.s2_page_fault;
    if(in.s2_valid && (!in.cache_response_valid || !in.queue_enqueue_ready)) {
      o.f0_valid=!fault || in.s2_replay || in.s2_tlb_miss || !in.queue_enqueue_ready;
      o.f0_pc=in.s2_pc;o.f0_replay=in.cache_response_valid;o.f1_clear=true;
    } else if(in.s2_valid && in.queue_enqueue_ready) {
      o.update_previous_half=true;
      if(!in.s1_valid || in.s1_pc!=in.f2_predicted_next) {
        o.f1_clear=true;o.f0_valid=!(fault && !in.s2_replay);
        o.f0_pc=in.f2_predicted_next;o.f0_replay=false;
      }
    }
    if(in.core_redirect_flush) {
      o.f0_valid=in.core_redirect_valid;o.f0_pc=in.core_redirect_pc;
      o.f0_replay=false;o.f1_clear=true;o.f2_clear=true;
    }
    if(in.jump_to_reset) {
      o.f0_valid=true;o.f0_pc=in.reset_vector;o.f0_replay=false;
      o.f1_clear=true;o.f2_clear=true;
    }
    o.enqueue_valid=in.s2_valid && !o.f2_clear && (in.cache_response_valid || (fault && !in.s2_tlb_miss));
    o.next_s1_valid=!in.reset && o.f0_valid;
    o.next_s2_valid=!in.reset && in.s1_valid && !o.f1_clear;
    o.clear_previous_half=o.f2_clear;
    if(o.clear_previous_half)o.update_previous_half=false;
    return o;
  }
};
}
