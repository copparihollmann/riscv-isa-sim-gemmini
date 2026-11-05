#include "execute_operand_counters.hpp"
#include <cassert>
#include <iostream>
#include <vector>
using namespace gemmini_annotated_spike;
using C=ExecuteOperandCounters;
C source(unsigned a_rows,unsigned d_rows,bool same){
 return C({C::Operand{0,a_rows,false,true},C::Operand{},C::Operand{same?16u:4096u,d_rows,false,true}},16,16,4096,4);
}
int main(){
 for(unsigned stride:{2u,3u}){
   C sampled({C::Operand{4090,16,false,true,stride},C::Operand{},C::Operand{4096,16,false,true}},16,16,4096,4);
   std::vector<unsigned>addresses;unsigned clocks=0;
   while(!sampled.complete()){
     const auto saved=sampled.counters();auto held=sampled.step({true,true,true},false);
     (void)held;assert(sampled.counters()==saved);
     auto s=sampled.step({true,true,true},true);
     if(s.physical[0]&&s.fire[0])addresses.push_back(s.request[0].bank*4096+s.request[0].row);
     assert(++clocks<=48);
   }
   assert(addresses.size()==16);
   for(unsigned i=0;i<16;++i)assert(addresses[i]==4090+i*stride);
 }
 for(unsigned mode=0;mode<3;++mode){
   bool refused=false;
   try{C invalid({C::Operand{mode==2?16380u:0u,16,false,true,mode==0?0u:3u},
                  C::Operand{0,16,false,true,mode==1?2u:1u},C::Operand{}},16,16,4096,4);}
   catch(const std::invalid_argument&){refused=true;}assert(refused);
 }
 for(bool same:{false,true})for(unsigned rows:{1,4,16}){
   auto c=source(rows,rows,same);unsigned cycle=0,a=0,d=0;std::vector<unsigned>ar,dr;
   while(!c.complete()){
     auto s=c.step({true,true,true},true);
     for(unsigned i:{0u,2u})if(s.physical[i]&&s.fire[i]){
       if(i==0){++a;ar.push_back(s.request[i].row);assert(cycle==(same?2:1)*(a-1));}
       else{++d;dr.push_back(s.request[i].row);assert(cycle==(same?2:1)*(16-rows+d-1)+(same?1:0));}
     }
     ++cycle;assert(cycle<=32);
   }
   assert(cycle==(same?32u:16u)&&a==rows&&d==rows);
   for(unsigned i=0;i<rows;++i){assert(ar[i]==i);assert(dr[i]==(same?16:0)+rows-1-i);}
   for(auto n:c.counters())assert(n==0);
 }
 // A blocked physical D read allows A/garbage B only one row ahead. A full
 // control queue freezes all counters, including otherwise-ready operands.
 auto stalled=source(16,16,true);auto first=stalled.step({true,true,true},true);
 assert(first.fire[0]&&!first.fire[2]);auto saved=stalled.counters();
 for(unsigned i=0;i<7;++i){auto s=stalled.step({true,true,false},true);assert(!s.fire[0]&&!s.fire[1]&&!s.fire[2]&&stalled.counters()==saved);}
 for(unsigned i=0;i<7;++i){stalled.step({true,true,true},false);assert(stalled.counters()==saved);}
 unsigned a=1,d=0;while(!stalled.complete()){auto s=stalled.step({true,true,true},true);a+=s.physical[0]&&s.fire[0];d+=s.physical[2]&&s.fire[2];}assert(a==16&&d==16);
 // Equal-counter priority also applies to B: one actual bank port, A>B>D.
 C all({C::Operand{0,16,false,true},C::Operand{16,16,false,true},C::Operand{32,16,false,true}},16,16,4096,4);
 unsigned clocks=0,requests=0;while(!all.complete()){auto s=all.step({true,true,true},true);unsigned n=0;for(unsigned i=0;i<3;++i)n+=s.physical[i]&&s.fire[i];assert(n==1);requests+=n;++clocks;assert(clocks<=48);}assert(clocks==48&&requests==48);
 bool refused=false;try{C bad({},1,16,4096,4);}catch(const std::invalid_argument&){refused=true;}assert(refused);
 std::cout<<"source A/B/D priority, padding, reverse D rows, one-ahead and actual control/SRAM backpressure PASS\n";
}
