#include "frontend_select.hpp"
#include "frontend_queue.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <array>

using iris::frontend::ShuttleFrontendSelect;
int main(int argc,char**argv) {
  if(argc!=2)throw std::invalid_argument("actual RTL selector corpus required");
  std::ifstream input(argv[1]);std::array<uint64_t,28> r{};uint64_t rows=0,checks=0,replays=0,redirects=0;
  while(input>>r[0]) {
    for(unsigned i=1;i<r.size();++i)if(!(input>>r[i]))throw std::runtime_error("incomplete selector row");
    auto [reset,jump,s1v,s2v,s1pc,s2pc,r1,r2,ae,pf,miss,response,pred1,pred2,flush,rdval,rdpc,
          valid,enq,deq,mask,wantv,wantpc,wantr,wantclear,wantenq,next1,next2]=r;
    auto queue=reset?iris::frontend::ShuttleFetchQueue():iris::frontend::ShuttleFetchQueue({uint8_t(valid),uint8_t(enq),uint8_t(deq)});
    ShuttleFrontendSelect::Inputs in;
    in.reset=reset;in.jump_to_reset=jump;in.s1_valid=s1v;in.s2_valid=s2v;in.s1_pc=s1pc;in.s2_pc=s2pc;
    in.s1_replay=r1;in.s2_replay=r2;in.s2_access_fault=ae;in.s2_page_fault=pf;in.s2_tlb_miss=miss;
    in.cache_response_valid=response;in.queue_enqueue_ready=queue.enqueue_ready(mask);in.f1_predicted_next=pred1;in.f2_predicted_next=pred2;
    in.core_redirect_flush=flush;in.core_redirect_valid=rdval;in.core_redirect_pc=rdpc;
    const auto o=ShuttleFrontendSelect::evaluate(in);
    if(o.f0_valid!=bool(wantv) || o.f0_pc!=wantpc || o.f0_replay!=bool(wantr) || o.f1_clear!=bool(wantclear) || o.enqueue_valid!=bool(wantenq) || o.next_s1_valid!=bool(next1) || o.next_s2_valid!=bool(next2))
      throw std::runtime_error("actual selector mismatch row="+std::to_string(rows));
    ++rows;checks+=7;replays+=o.f0_replay;redirects+=flush;
  }
  if(!input.eof() || rows<160000 || !replays || !redirects)throw std::runtime_error("incomplete actual selector coverage");
  // A returning fault may be enqueued without a cache response when TLB
  // translation completed. A missing translation must replay instead.
  ShuttleFrontendSelect::Inputs x;x.s2_valid=true;x.s2_access_fault=true;x.queue_enqueue_ready=true;x.s2_pc=0x580000000;
  auto o=ShuttleFrontendSelect::evaluate(x);if(o.f0_valid || !o.enqueue_valid)throw std::runtime_error("fault-stop/source enqueue changed");
  x.s2_tlb_miss=true;o=ShuttleFrontendSelect::evaluate(x);if(!o.f0_valid || o.enqueue_valid)throw std::runtime_error("fault+TLB-miss replay changed");
  x.core_redirect_flush=true;x.core_redirect_valid=true;x.core_redirect_pc=0x80010000;x.jump_to_reset=true;
  o=ShuttleFrontendSelect::evaluate(x);if(o.f0_pc!=0x10000 || !o.f0_valid || !o.f2_clear || o.enqueue_valid)throw std::runtime_error("reset-jump priority changed");
  std::cout<<"PASS actual RTL frontend-select transitions="<<rows<<" checks="<<checks<<" replays="<<replays<<" redirects="<<redirects<<" plus fault/reset controls\n";
}
