#include "execute_operand_pipeline.hpp"
#include <cassert>
#include <iostream>
#include <set>
using namespace gemmini_annotated_spike;
using C=ExecuteOperandCounters;
void run(bool same,bool stalls){
 ExecuteOperandPipeline source(C({C::Operand{0,16,false,true},C::Operand{},C::Operand{same?16u:4096u,16,false,true}},16,16,4096,4),4);
 MeshOperandRegisters mesh(16);unsigned clock=0,rows=0,requests=0,first=0,source_done=0;std::set<std::uint64_t>accepted,consumed;
 while(!source.source_consumed()||!source.empty()||mesh.busy()){
   if(mesh.row_fire()){if(!rows)first=clock;++rows;}
   auto signals=mesh.signals(!stalls||clock>=20); // no fake tag credit
   const bool available=!stalls||clock<2||clock>=12;
   auto edge=source.step({available,true,true,true},signals);
   for(auto r:edge.reads){assert(accepted.insert(r.serial).second);if(same)assert(r.bank==0);}
   for(auto r:edge.consumed){assert(accepted.count(r.serial)&&consumed.insert(r.serial).second);}
   requests+=edge.request_fire;if(edge.source_consumed)source_done=clock;
   mesh.step(edge);++clock;if(clock>=250)std::cerr<<"stuck same="<<same<<" stalls="<<stalls<<" rows="<<rows<<" requests="<<requests<<" reads="<<accepted.size()<<" responses="<<consumed.size()<<"\n";assert(clock<250);
 }
 assert(rows==16&&requests==1&&accepted==consumed&&accepted.size()==32);
 const auto&c=source.coverage();assert(c.control_peak<=5&&c.response_peak<=4&&c.sram_peak<=1&&c.reads==32&&c.responses==32);
 if(!stalls){assert(first==(same?4u:3u));assert(source_done==(same?31u:15u));assert(clock==(same?35u:19u));}
 else{assert(c.control_stalls>0&&source_done>31);}
}
void chained(bool same){
 ExecuteOperandPipeline source(C({C::Operand{0,16,false,true},C::Operand{},C::Operand{same?16u:4096u,16,false,true}},16,16,4096,4),4);
 MeshOperandRegisters mesh(16);unsigned clock=0,phase=0,first=0;std::array<unsigned,2>rows{};std::set<std::uint64_t>requests,responses;
 while(phase<2||!source.empty()||mesh.busy()){
   if(source.source_consumed()){
     if(phase==0){source.begin(C({C::Operand{},C::Operand{},C::Operand{0,0,true,true}},4,16,4096,4),1);phase=1;}
     else phase=2;
   }
   if(mesh.row_fire()){auto owner=mesh.owner();assert(owner<2);assert(mesh.row()==rows[owner]);if(owner==1&&!rows[owner])first=clock;++rows[owner];}
   auto edge=source.step({true,true,true,true},mesh.signals());
   for(auto r:edge.reads){assert(r.owner==0&&requests.insert(r.serial).second);}
   for(auto r:edge.consumed)assert(responses.insert(r.serial).second);
   mesh.step(edge);++clock;assert(clock<80);
 }
 assert(rows[0]==16&&rows[1]==4&&requests==responses&&requests.size()==32);
 assert(first==(same?35u:19u)); // prior tail lives through next source admission
}
int main(){for(bool same:{false,true}){for(bool stalls:{false,true})run(same,stalls);chained(same);}std::cout<<"original Queue5/Queue4/SRAM1 custody, finite mesh registers, exact response identity, chained original requests and bank/tag stalls PASS\n";}
