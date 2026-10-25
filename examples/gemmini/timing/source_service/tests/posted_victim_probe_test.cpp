#include "posted_victim_probe.hpp"
#include <cassert>
#include <iostream>
#include <tuple>

using namespace gemmini_annotated_spike;
using Q=merlin_timing::PostedTimeline;
using Cycle=merlin_timing::Cycle;
using Actor=PostedVictimProbe;

Actor::Request request(bool dirty=false,bool llc_dirty=false) {
  // Public synthetic identity, source pins identify the reviewed RTL selection.
  Actor::Law law{"fir:6748b9756799c086a6fb06e6d80b4b052f2771f9eb1858c172e14dcf441ba149",
    1024,8,64,16,8,2,1,2,1};
  Actor::Guards guards{0,true,true,true,true,true};
  return {{0x1010,0x10,2,17},0x2010,false,llc_dirty,dirty,law,guards};
}
void finish(Q& q) {
  while(q.step(true)) {}
  assert(!q.progress().failed && q.progress().complete);
}
void clean(bool llc_dirty) {
  Q q({4096,4096,100000});
  Actor actor(q,[](auto,auto,auto,auto,auto){assert(false);});
  auto r=actor.push(request(false,llc_dirty),0);assert(r);
  assert(r->effective_dirty==llc_dirty && r->beat_publication.empty());
  assert(!q.completed(r->b_accepted));
  assert(q.advance(2,true));
  assert(q.completed(r->sourceb_request)==0 && q.completed(r->b_accepted)==0);
  assert(!q.completed(r->first_response));
  finish(q);
  assert(q.completed(r->first_response)==4 && q.completed(r->last_response)==4);
  assert(q.completed(r->metadata_done)==3 && q.completed(r->client_released)==4 && !actor.busy());
  for(unsigned i=0;i<8;++i) assert(r->read_dependencies(i).size()==1);
  bool refused=false;
  try{r->read_dependencies(8);}catch(const std::invalid_argument&){refused=true;}
  assert(refused);
}
void dirty(bool stall) {
  Q q({4096,4096,100000});
  std::vector<std::tuple<unsigned,std::uint64_t,Cycle>> offered;
  Actor actor(q,[&](auto beat,auto address,auto mask,Cycle at,auto stored){
    assert(mask==0xffff);
    offered.emplace_back(beat,address,at);
    if(stall && !beat)q.post(20,{},[stored](auto&q,auto){q.complete(stored);});
    else q.complete(stored);
  });
  auto input=request(true,false);
  auto r=actor.push(input,0);assert(r);
  assert(r->effective_dirty && r->beat_publication.size()==4);
  assert(offered.empty()); // No eager port booking or future publication.
  std::vector<std::optional<Cycle>> reads(8);
  for(unsigned i=0;i<8;++i) {
    auto deps=r->read_dependencies(i);
    assert(deps.size()==2 && deps[1].id==r->beat_publication[i/2].id);
    q.post(0,deps,[&,i](auto&,Cycle at){reads[i]=at;});
  }
  assert(q.advance(5,true));assert(offered.empty());
  if(stall) {
    assert(q.advance(17,true));
    // First MSHR response has happened while the queued bank write still waits.
    assert(q.completed(r->first_response)==7);
    assert(!q.completed(r->beat_publication[0]) && !q.completed(r->last_response));
    assert(!reads[0] && actor.busy());
  }
  finish(q);
  assert(offered.size()==4 && !actor.busy());
  for(unsigned i=0;i<4;++i) {
    assert(std::get<0>(offered[i])==i && std::get<1>(offered[i])==input.victim.line*64+i*16);
    const Cycle pub=stall?20+i:7+i;
    assert(q.completed(r->beat_publication[i])==pub);
    assert(reads[i*2]==pub && reads[i*2+1]==pub);
  }
  assert(q.completed(r->first_response)==7);
  assert(q.completed(r->last_response)==(stall?23:10));
  assert(q.completed(r->metadata_done)==(stall?22:9));
  assert(q.completed(r->client_released)==(stall?23:10));
}
void guard_refusals() {
  for(unsigned variant=0;variant<6;++variant) {
    Q q({4096,4096,100000});Actor actor(q,[](auto,auto,auto,auto,auto){assert(false);});
    auto in=request();
    switch(variant){
      case 0:in.guards.client_ready.reset();break;
      case 1:in.guards.cpu_s1_s2_closed=false;break;
      case 2:in.guards.grant_and_postgrant_closed=false;break;
      case 3:in.guards.release_and_releaseack_closed=false;break;
      case 4:in.guards.lrsc_closed=false;break;
      case 5:in.guards.private_data_and_metadata_ports_owned=false;break;
    }
    assert(!actor.push(in,0));
    assert(q.progress().failed && q.summary().peak_pending==0 && q.summary().unresolved_tokens==0);
    assert(q.reason().find("unknown Rocket readiness")!=std::string::npos);
  }
}
void identity_refusals() {
  for(unsigned variant=0;variant<8;++variant) {
    Q q({4096,4096,100000});Actor actor(q,[](auto,auto,auto,auto,auto){assert(false);});
    auto in=request();
    switch(variant){
      case 0:in.victim.set++;break;
      case 1:in.victim.way=8;break;
      case 2:in.victim.generation=0;break;
      case 3:in.target_line=in.victim.line;break;
      case 4:in.target_private_hit=true;break;
      case 5:in.target_line++;break;
      case 6:in.law.inner_beat_bytes=8;break;
      case 7:in.law.lookup_stages=3;break;
    }
    assert(!actor.push(in,0));assert(q.progress().failed && q.summary().peak_pending==0);
  }
  Q q({4096,4096,100000});Actor actor(q,[](auto,auto,auto,auto,auto){assert(false);});
  assert(actor.push(request(),0));assert(!actor.push(request(),0));
  assert(q.progress().failed && q.reason().find("duplicate")!=std::string::npos);
}
void sourceb_and_private_occupancy_are_distinct() {
  Q q({4096,4096,100000});
  Actor actor(q,[&](auto,auto,auto,Cycle,auto stored){q.complete(stored);});
  auto in=request(true);in.guards.client_ready=10;
  auto first=actor.push(in,0);assert(first);
  in.victim.line+=1024;in.target_line+=1024;in.victim.generation++;
  in.guards.client_ready=0;
  auto second=actor.push(in,0);assert(second);
  finish(q);
  assert(q.completed(first->sourceb_request)==0 && q.completed(first->b_accepted)==10);
  assert(q.completed(first->metadata_done)==19);
  // A new MSHR may capture SourceB after the prior B acceptance, while its
  // actual B transfer waits the same private controller's metadata completion.
  assert(q.completed(second->sourceb_request)==11);
  assert(q.completed(second->b_accepted)==20 && q.completed(second->metadata_done)==29);
  assert(actor.peak()==2 && !actor.busy());
}
int main() {
  clean(false);clean(true);dirty(false);dirty(true);
  guard_refusals();identity_refusals();sourceb_and_private_occupancy_are_distinct();
  std::cout<<"PASS clean/dirty upgrade, first/last/pub split, 4-to-8 beat dependencies, guards, identity, backpressure\n";
}
