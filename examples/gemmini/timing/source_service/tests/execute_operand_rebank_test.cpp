#include "execute_operand_pipeline.hpp"
#include <cassert>
#include <iostream>
#include <map>
#include <set>
#include <tuple>
using namespace gemmini_annotated_spike;
using C=ExecuteOperandCounters;
using P=ExecuteOperandPipeline;

struct Observation {unsigned clocks,first,source_done;P::Coverage coverage;};
bool same_response(const P::Response&a,const P::Response&b){
 return a.operand==b.operand&&a.bank==b.bank&&a.row==b.row&&a.serial==b.serial&&a.owner==b.owner;
}
Observation run(unsigned banks,unsigned d_start,bool stalls,bool chained=false){
 const unsigned bank_rows=16384/banks;
 const auto counters=[&](){return C({C::Operand{0,16,false,true},C::Operand{},C::Operand{d_start,16,false,true}},16,16,bank_rows,banks);};
 P source(counters(),banks);MeshOperandRegisters mesh(16);
 unsigned clock=0,rows=0,first=0,source_done=0,phase=0,requests=0;
 std::map<std::uint64_t,P::Response>accepted,consumed;
 std::set<std::tuple<std::uint64_t,unsigned,unsigned>>requested_rows;
 std::map<std::uint64_t,unsigned>owner_rows;
 bool changed_geometry_refused=false;
 while(!source.source_consumed()||!source.empty()||mesh.busy()||(chained&&phase==0)){
   if(chained&&source.source_consumed()&&phase==0){source.begin(counters(),42);phase=1;}
   if(mesh.row_fire()){
     if(!rows)first=clock;
     assert(mesh.owner()==0||(chained&&mesh.owner()==42));
     assert(mesh.row()==owner_rows[mesh.owner()]++);++rows;
   }
   std::vector<bool>ports(banks,true);
   if(stalls&&clock>=4&&clock<18)ports[0]=false;
   const auto edge=source.step(ports,mesh.signals(!stalls||clock>=35));
   std::set<unsigned>edge_banks;
   for(const auto&r:edge.reads){
     assert(edge_banks.insert(r.bank).second&&r.bank<banks&&r.row<bank_rows&&ports[r.bank]);
     assert(r.owner==0||(chained&&r.owner==42));
     assert(r.operand==0||r.operand==2);
     const auto address=r.bank*bank_rows+r.row;
     assert((r.operand==0&&address<16)||(r.operand==2&&address>=d_start&&address<d_start+16));
     assert(requested_rows.emplace(r.owner,r.operand,address).second);
     assert(accepted.emplace(r.serial,r).second);
   }
   for(const auto&r:edge.consumed){
     assert(accepted.count(r.serial)&&same_response(accepted.at(r.serial),r));
     assert(consumed.emplace(r.serial,r).second);
   }
   requests+=edge.request_fire;
   if(edge.source_consumed){
     source_done=clock;
     if(!changed_geometry_refused){
       try{source.begin(C({},4,16,bank_rows/2,banks*2),99);}
       catch(const std::invalid_argument&){changed_geometry_refused=true;}
       assert(changed_geometry_refused);
     }
   }
   mesh.step(edge);assert(++clock<400);
 }
 assert(changed_geometry_refused&&owner_rows[0]==16&&(!chained||owner_rows[42]==16));
 assert(rows==(chained?32u:16u)&&requests==(chained?2u:1u));
 assert(accepted.size()==(chained?64u:32u)&&accepted.size()==consumed.size());
 assert(requested_rows.size()==accepted.size());
 for(const auto&entry:accepted)assert(same_response(entry.second,consumed.at(entry.first)));
 const auto&coverage=source.coverage();
 assert(coverage.control_peak<=5&&coverage.response_peak<=4&&coverage.sram_peak<=1);
 assert(coverage.reads==accepted.size()&&coverage.responses==consumed.size());
 if(stalls)assert(coverage.control_stalls>0&&coverage.control_peak==5&&coverage.response_peak==4);
 return {clock,first,source_done,coverage};
}

int main(){
 bool saw_sram_backpressure=false;
 for(unsigned banks:{2u,4u,8u})for(bool stalls:{false,true}){
   for(unsigned d_start:{4096u,8192u})for(bool chained:{false,true})
     saw_sram_backpressure|=run(banks,d_start,stalls,chained).coverage.sram_peak==1;
 }
 assert(saw_sram_backpressure);
 const auto old=run(4,4096,false),merged=run(2,4096,false),repaired=run(2,8192,false);
 const auto more=run(8,4096,false);
 assert(old.clocks==19&&old.first==3&&old.source_done==15);
 assert(merged.clocks==35&&merged.first==4&&merged.source_done==31);
 assert(repaired.clocks==old.clocks&&repaired.first==old.first&&repaired.source_done==old.source_done);
 assert(more.clocks==old.clocks);
 for(const auto&geometry:std::vector<std::pair<unsigned,unsigned>>{{0,4},{4096,0},{4096,3},{3000,4},{8,2},{4096,256},{0x80000000u,2}}){
   bool refused=false;try{C invalid({},4,16,geometry.first,geometry.second);}catch(const std::invalid_argument&){refused=true;}assert(refused);
 }
 bool refused=false;try{P invalid(C({},4,16,4096,4),2);}catch(const std::invalid_argument&){refused=true;}assert(refused);
 P source(C({},4,16,8192,2),2);refused=false;
 try{source.step({true,true,true,true},{{true,true,true},true});}catch(const std::invalid_argument&){refused=true;}assert(refused);
 assert(source.coverage().reads==0&&source.coverage().control_peak==0);
 std::cout<<"2/4/8-bank rebanking, merged/repaired placements, original response identities and finite backpressure PASS\n";
}
