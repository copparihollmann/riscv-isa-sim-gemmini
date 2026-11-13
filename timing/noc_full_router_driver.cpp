#include "noc_full_router.hpp"
#include <charconv>
#include <chrono>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
using namespace iris::noc;
static std::uint64_t number(std::istringstream& s){std::string t;if(!(s>>t))throw std::invalid_argument("Incomplete full-router boundary");std::uint64_t v=0;auto r=std::from_chars(t.data(),t.data()+t.size(),v);if(r.ec!=std::errc{}||r.ptr!=t.data()+t.size())throw std::invalid_argument("Unsigned boundary integer required");return v;}
static std::uint8_t small(std::istringstream& s){auto v=number(s);if(v>255)throw std::invalid_argument("Boundary field exceeds8bits");return v;}
static bool flag(std::istringstream& s){auto v=number(s);if(v>1)throw std::invalid_argument("Boolean physical signal required");return v;}
static FullPayload payload(std::istringstream& s){FullPayload p;for(auto& w:p.words){auto v=number(s);if(v>0xffffffffULL)throw std::invalid_argument("Payload word exceeds32bits");w=v;}return p;}
static FullChannelFlit channel(std::istringstream& s){FullChannelFlit f;f.valid=flag(s);f.head=flag(s);f.tail=flag(s);f.payload=payload(s);f.flow={small(s),small(s),small(s),small(s),small(s)};f.vc=small(s);return f;}
static void emit(std::uint64_t v){std::cout<<' '<<v;}
static void emit(const FullPayload& p){for(auto w:p.words)emit(w);}
static void emit(const FullChannelFlit& f){emit(f.valid);emit(f.head);emit(f.tail);emit(f.payload);emit(f.flow.vnet);emit(f.flow.ingress_node);emit(f.flow.ingress_id);emit(f.flow.egress_node);emit(f.flow.egress_id);emit(f.vc);}
int main(int argc,char** argv){try{
 if(argc!=3||std::string(argv[1])!="--seed")throw std::invalid_argument("Explicit --seed N required; reset is supplied physically");std::istringstream ss(argv[2]);auto seed=number(ss);if(seed>0xffffffffULL)throw std::invalid_argument("Seed exceeds32bits");FullNode5Router router(seed);
 std::uint64_t nanos=0,steps=0;auto start=std::chrono::steady_clock::now();
 for(std::string line;std::getline(std::cin,line);){
  std::istringstream s(line);std::string op;if(!(s>>op))continue;
  if(op=="save"||op=="restore"){std::string path;if(!(s>>path))throw std::invalid_argument("Snapshot path required");if(op=="save")router.save(path);else router.restore(path);continue;}
  if(op!="step")throw std::invalid_argument("Only full physical steps and explicit source-bound snapshots supported");
  auto tb=number(s);FullRouterInputs i{};i.reset=flag(s);for(auto& f:i.from_network)f=channel(s);
  for(auto& f:i.from_local){f.valid=flag(s);f.head=flag(s);f.tail=flag(s);f.payload=payload(s);f.egress_id=small(s);}
  for(auto& c:i.downstream)c={small(s),small(s)};i.local_ready=flag(s);std::string extra;if(s>>extra)throw std::invalid_argument("Extra physical boundary fields");
  auto begin=std::chrono::steady_clock::now();auto o=router.step(i);nanos+=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-begin).count();++steps;
  std::cout<<tb;for(auto& f:o.to_network)emit(f);for(bool r:o.local_ready)emit(r);for(auto& c:o.upstream){emit(c.credit_return);emit(c.vc_free);}emit(o.to_local.valid);emit(o.to_local.head);emit(o.to_local.tail);emit(o.to_local.payload);for(auto v:o.va_stalls)emit(v);for(auto v:o.sa_stalls)emit(v);std::cout<<'\n';
 }
 const auto host=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();std::cerr<<"NODE5_COST {\"edges\":"<<steps<<",\"native_step_ns\":"<<nanos<<",\"host_total_ns\":"<<host<<",\"native_edges_per_second\":"<<(nanos?double(steps)*1e9/double(nanos):0)<<"}\n";return 0;
}catch(const std::exception& e){std::cerr<<"Full router refused: "<<e.what()<<'\n';return 2;}}
