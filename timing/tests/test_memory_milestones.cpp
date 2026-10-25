
#include "memory.hpp"
#include "merlin_timing/ready_response_arbiter.hpp"
#include <cassert>
#include <map>
int main(int argc,char **argv) {
  assert(argc==2);
  spike_timing::Model model(argv[1]);
  merlin_timing::Engine engine(model.max_values,model.resources);
  std::uint64_t next=0;
  std::map<std::string,std::uint64_t> features;
  spike_timing::MemorySystem memory(model,engine,[&](std::size_t n){auto p=next;next+=n;return p;},
      [&](const auto &k,auto n){features[k]+=n;},[](const auto &){});
  spike_timing::MemoryEffect effect{0x81000000,16,false};
  const auto first=memory.access({effect},"device");
  assert(first.latency && features.at("modeled.cache.l2.misses")==1);
  merlin_timing::MemoryRequestIdentityV1 request{1,effect.address,effect.bytes,14,7,0};
  merlin_timing::MemoryMilestonesV2 out;
  const auto before=features;
  assert(memory.last_observation(request,out));
  assert(out.fill && out.fill->generation==1 && out.request.return_source==14);
  assert(!out.source && !out.first_refill_beat && !out.last_refill_beat && !out.line_visible);
  assert(out.coverage==merlin_timing::MemoryMilestoneCoverage::unsupported);
  assert(out.unavailable.find("MSHR")!=std::string::npos);
  merlin_timing::MemoryMilestonesV1 legacy;
  assert(memory.last_observation(request,legacy));
  assert(legacy.fill==out.fill && legacy.coverage==out.coverage && legacy.unavailable==out.unavailable);
  const auto fill=*out.fill;
  for(int i=0;i<4;++i)assert(memory.last_observation(request,out));
  assert(features==before && engine.report().events==0); // no extra work/cache warming
  request.address+=16;assert(!memory.last_observation(request,out));request.address-=16;
  const auto second=memory.access({effect},"device");
  assert(second.latency && features.at("modeled.cache.l2.hits")==1);
  assert(memory.last_observation(request,out) && out.fill && *out.fill==fill);
  merlin_timing::ReadyResponseArbiter rr({12,16,16,1});
  assert(!rr.enqueue(out)); // native aggregate observation cannot authorize RR
  effect.write=true;memory.access({effect},"device");
  assert(!memory.last_observation(request,out)); // intervening write invalidates last record
}
