#include "overlap_completion_entry_schedule.hpp"
#include <iostream>
#include <stdexcept>
using iris::opu_entry::Schedule;
static void require(bool b){if(!b)throw std::runtime_error("entry schedule control failed");}
int main(){unsigned checks=0;
 for(unsigned tm=1;tm<=32;++tm)for(unsigned tn=1;tn<=32;++tn){
  Schedule s;auto a=s.reserve(0,tm,tn,true,0);std::uint64_t macs=0;
  for(auto m:a){macs+=m.macs;require(m.array_accept_edge==m.sequencer_edge+1&&m.write_edge==m.sequencer_edge+3);++checks;}
  require(macs==tm*tn);++checks;
 }
 for(unsigned shape:{8,16,32})for(bool fp8:{false,true})for(bool rotate:{false,true}){
  Schedule s;std::uint64_t previous=0;
  for(unsigned n=0;n<64;++n){auto a=s.reserve(rotate?n%4:0,shape,shape,fp8,n);
   if(n&&shape<=16)require(a.front().sequencer_edge-previous==(fp8&&!rotate?3:1));
   previous=a.back().sequencer_edge;checks+=a.size();
  }
 }
 Schedule h;auto fp=h.reserve(0,16,16,true,0);auto integer=h.reserve(3,16,16,false,0);
 require(integer.front().sequencer_edge==fp.front().sequencer_edge+3);++checks;
 for(auto bad:{0U,33U}){bool rejected=false;try{Schedule s;s.reserve(0,bad,16,true,0);}catch(const std::invalid_argument&){rejected=true;}require(rejected);++checks;}
 std::cout<<"{\"pass\":true,\"checks\":"<<checks<<"}\n";
}
