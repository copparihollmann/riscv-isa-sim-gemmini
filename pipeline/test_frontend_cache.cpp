#include "frontend_cache.hpp"
#include <cassert>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>

using iris::frontend::ShuttleCache;
int main(int argc,char** argv) {
  if (argc!=2) throw std::invalid_argument("expected actual RTL transition input");
  std::array<ShuttleCache,2> cache;std::ifstream input(argv[1]);unsigned h,reset,beat,invalidate,bv0,bv1,av0,av1;uint64_t request,baddr,addr;unsigned bs,as,bt0,bt1,at0,at1;
  uint64_t rows=0,checks=0;
  auto compare=[&](const ShuttleCache& c,uint64_t address,unsigned state,unsigned v0,unsigned t0,unsigned v1,unsigned t1) {
    auto p=c.probe(address);
    if (c.replacement_state()!=state || p.state[0].valid!=bool(v0) || p.state[1].valid!=bool(v1) ||
        (v0 && p.state[0].tag!=t0) || (v1 && p.state[1].tag!=t1))
      throw std::runtime_error("actual RTL cache state differs at row="+std::to_string(rows));
    checks+=3+v0+v1;
  };
  while(input>>h>>reset>>request>>beat>>invalidate>>baddr>>bs>>bv0>>bt0>>bv1>>bt1>>addr>>as>>av0>>at0>>av1>>at1) {
    if (h>=2) throw std::invalid_argument("non-Shuttle hart in source cache corpus");
    if (!reset) compare(cache[h],baddr,bs,bv0,bt0,bv1,bt1);
    ShuttleCache::Edge e;e.reset=reset;e.data_beat=beat;e.invalidate=invalidate;
    if (request!=std::numeric_limits<uint64_t>::max()) e.accepted_refill=request;
    cache[h].clock(e);compare(cache[h],addr,as,av0,at0,av1,at1);++rows;
  }
  if (!input.eof() || rows<100000) throw std::runtime_error("truncated or malformed source cache corpus");
  // Source-priority corner cases, separate from the actual-trace proof.
  ShuttleCache c;const uint64_t address=0x80000300;
  c.clock({false,false,false,address});auto way=c.pending()->way;
  for(unsigned i=0;i<8;++i)c.clock({false,i==7,true,{}});
  assert(!c.probe(address).state[way].valid && c.probe(address).state[way].tag==address>>12);
  c.clock({});c.clock({false,true,false,address});
  for(unsigned i=0;i<8;++i)c.clock({false,false,true,{}});
  assert(c.probe(address).hit);
  c.clock({false,true,false,{}});assert(!c.probe(address).hit);
  bool rejected=false;try{c.clock({false,false,true,{}});}catch(const std::logic_error&){rejected=true;}assert(rejected);
  std::cout<<"PASS actual RTL cache rows="<<rows<<" checks="<<checks<<" plus invalidate/request controls\n";
}
