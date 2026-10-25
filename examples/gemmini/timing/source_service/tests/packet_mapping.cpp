
#include "packet_load.hpp"
#include <cassert>
#include <map>
#include <tuple>
#include <iostream>
using namespace gemmini_annotated_spike;
int main(){
 std::size_t geometries=0;
 for(auto rows:{1u,3u,16u})for(auto cols:{1u,15u,16u,17u,31u,32u,48u,64u,80u,127u})for(unsigned align=0;align<64;++align)for(auto pad:{0u,1u,17u}){
  const auto pitch=cols+pad;auto p=reader_packets(0x10000+align,rows,cols,pitch,16,64,127);assert(!p.empty());
  std::map<std::size_t,std::uint64_t> masks;std::map<std::size_t,unsigned> finals;std::map<std::uint64_t,unsigned> bytes;
  for(const auto &x:p){assert(x.outputs.size()<=5);unsigned sent=0;
   for(const auto &f:x.outputs){assert(f.source_offset==sent);assert(f.required_beat<x.bytes/16);
    const auto col=x.address+x.shift+sent-(0x10000+align+x.row*pitch);const auto dest=(col/16)*rows+x.row;
    assert(dest==f.destination);assert(f.bytes==std::min<std::uint64_t>(16-col%16,x.useful-sent));
    assert(f.required_beat==(x.shift+sent+std::min<std::uint64_t>(16,x.useful-sent)+15)/16-1);
    assert((masks[dest]&f.mask)==0);masks[dest]|=f.mask;finals[dest]+=f.destination_complete;
    for(unsigned b=0;b<f.bytes;++b){assert(f.mask&(1ull<<((col+b)%16)));++bytes[x.address+x.shift+sent+b];}sent+=f.bytes;
   }assert(sent==x.useful);
  }
  assert(bytes.size()==rows*cols);
  for(unsigned row=0;row<rows;++row)for(unsigned c=0;c<cols;++c)assert(bytes.at(0x10000+align+row*pitch+c)==1);
  for(unsigned band=0;band<(cols+15)/16;++band)for(unsigned row=0;row<rows;++row){auto d=band*rows+row;assert(masks[d]==((1ull<<std::min(16u,cols-band*16))-1));assert(finals[d]==1);}
  ++geometries;
 }
 assert(reader_packets(0,1,128,128,16,64,127).empty());assert(reader_packets(0,17,16,16,16,64,127).empty());
 auto packets=reader_packets(0x10000,3,80,80,16,64,127);PacketLoadStream stream(4,true);std::vector<std::tuple<std::size_t,bool,Cycle>> outputs;
 auto result=stream.schedule(packets,0,[](std::size_t,Cycle at){return Result{at,at,at+2,merlin_timing::UnknownReason::none};},[&](std::size_t row,bool last,Cycle at){outputs.emplace_back(row,last,at);return Result{at,at,at+1,merlin_timing::UnknownReason::none};});
 assert(result.complete&&result.requests_complete&&outputs.size()==15);
 assert(std::get<2>(outputs.front())<*result.complete-1); // first actual row publishes before last row
 std::map<std::size_t,unsigned>finals;for(auto [row,last,at]:outputs)finals[row]+=last;for(unsigned row=0;row<15;++row)assert(finals[row]==1);
 PacketLoadStream blocked(4,true);auto delayed=blocked.schedule(packets,0,[](std::size_t,Cycle at){return Result{at,at,at+2,merlin_timing::UnknownReason::none};},[](std::size_t,bool,Cycle at){auto start=std::max(at,Cycle{50});return Result{start,start,start+1,merlin_timing::UnknownReason::none};});assert(delayed.complete&&*delayed.complete>*result.complete);
 std::cout<<geometries<<" exact source-byte/mask geometries; finite multi-output stream and backpressure PASS\n";
}
