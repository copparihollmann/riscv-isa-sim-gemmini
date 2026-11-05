#ifndef GEMMINI_EXECUTE_OPERAND_PIPELINE_HPP
#define GEMMINI_EXECUTE_OPERAND_PIPELINE_HPP
#include "execute_operand_counters.hpp"
#include <algorithm>
#include <deque>
#include <optional>
#include <vector>
#include <utility>
namespace gemmini_annotated_spike {
// Selected SyncReadMem -> Queue1(flow,pipe) -> Queue4(!flow,pipe),
// alongside Queue5_ComputeCntlSignals(!flow,pipe). No time-based readiness:
// one call represents one actual source edge, with actual external port and
// mesh handshakes. Request metadata is retained through every original slot.
class ExecuteOperandPipeline {
 public:
 using C=ExecuteOperandCounters;
 struct Response {unsigned operand,bank,row;std::uint64_t serial,owner;};
 struct Mesh {std::array<bool,3>ready;bool request_ready;};
 struct Edge {
   C::Signals source;
   std::array<bool,3>mesh_fire{};
   bool control_pop=false,request_fire=false,source_consumed=false;
   unsigned request_rows=0;std::uint64_t request_owner=0;
   std::vector<Response>reads,consumed;
 };
 struct Coverage {unsigned control_peak=0,response_peak=0,sram_peak=0;std::uint64_t reads=0,responses=0,control_stalls=0;};
 private:
 struct Control {C::Signals signals;std::array<std::optional<Response>,3>response;bool first;unsigned rows;std::uint64_t owner;};
 struct Bank {std::optional<Response>pending,queued;std::deque<Response>execute;};
 C counters_;std::vector<Bank>banks_;std::deque<Control>control_;
 std::uint64_t serial_=0,owner_=0;Coverage coverage_;
 static bool same(const Response&a,const Response&b){return a.serial==b.serial&&a.owner==b.owner&&a.operand==b.operand&&a.bank==b.bank&&a.row==b.row;}
 public:
 ExecuteOperandPipeline(C counters,unsigned banks):counters_(std::move(counters)){
   if(banks!=counters_.bank_count())throw std::invalid_argument("execute response banks differ from selected operand geometry");
   banks_.resize(banks);
 }
 const Coverage&coverage()const{return coverage_;}
 std::uint64_t source_owner()const{return owner_;}
 C::Signals offered()const{return counters_.signals({true,true,true},true);}
 bool source_consumed()const{return counters_.complete();}
 void begin(C counters,std::uint64_t owner){
   if(!source_consumed())throw std::logic_error("execute source command has not consumed its final row");
   if(counters.bank_count()!=counters_.bank_count()||counters.bank_rows()!=counters_.bank_rows())
     throw std::invalid_argument("execute source geometry changed while original responses may remain live");
   counters_=std::move(counters);owner_=owner;
 }
 bool empty()const{if(!control_.empty())return false;for(const auto&b:banks_)if(b.pending||b.queued||!b.execute.empty())return false;return true;}
 Edge step(const std::vector<bool>&port_ready,Mesh mesh){
   if(port_ready.size()!=banks_.size())throw std::invalid_argument("execute port readiness differs from selected bank count");
   Edge edge;std::vector<bool>dequeue(banks_.size(),false);
   if(!control_.empty()){
     const auto&c=control_.front();edge.control_pop=!c.first||mesh.request_ready;
     edge.request_rows=c.rows;edge.request_owner=c.owner;
     for(unsigned i=0;i<3;++i){
       bool data=true;
       if(c.response[i]){const auto&bank=banks_.at(c.response[i]->bank);data=!bank.execute.empty()&&same(bank.execute.front(),*c.response[i]);}
       edge.mesh_fire[i]=c.signals.fire[i]&&data&&mesh.ready[i];
       edge.control_pop=edge.control_pop&&(!c.signals.fire[i]||edge.mesh_fire[i]||!mesh.ready[i]);
     }
     if(edge.control_pop){
       edge.request_fire=mesh.request_ready&&(c.signals.fire[0]||c.signals.fire[1]||c.signals.fire[2]);
       for(unsigned i=0;i<3;++i)if(c.response[i]&&edge.mesh_fire[i]){
         auto bank=c.response[i]->bank;if(dequeue.at(bank))throw std::logic_error("two physical responses consumed from one actual bank");
         dequeue[bank]=true;edge.consumed.push_back(*c.response[i]);
       }
     }
   }
   // The pipeline's non-flow queues observe old contents. SRAM Queue1 may
   // flow its arriving synchronous response directly into the execute FIFO.
   std::vector<bool>read_ready(banks_.size(),false);
   for(unsigned i=0;i<banks_.size();++i){
     auto&b=banks_[i];const bool execute_ready=b.execute.size()<4||dequeue[i];
     if(dequeue[i]){b.execute.pop_front();++coverage_.responses;}
     if(b.queued){
       if(execute_ready){b.execute.push_back(*b.queued);b.queued.reset();}
       if(b.pending){if(b.queued)throw std::logic_error("original SRAM response Queue1 overflow");b.queued=b.pending;}
     }else if(b.pending){if(execute_ready)b.execute.push_back(*b.pending);else b.queued=b.pending;}
     b.pending.reset();read_ready[i]=!b.queued&&port_ready[i];
     coverage_.response_peak=std::max(coverage_.response_peak,unsigned(b.execute.size()));
     coverage_.sram_peak=std::max(coverage_.sram_peak,unsigned(bool(b.queued)));
   }
   const bool control_ready=control_.size()<5||edge.control_pop;
   if(edge.control_pop)control_.pop_front();
   if(!counters_.complete()){
     const auto offered=counters_.signals({true,true,true},control_ready);
     std::array<bool,3>ready{};
     for(unsigned i=0;i<3;++i)ready[i]=!offered.physical[i]||read_ready.at(offered.request[i].bank);
     const bool first=!counters_.started()[0]&&!counters_.started()[1]&&!counters_.started()[2];
     edge.source=counters_.step(ready,control_ready);edge.source_consumed=edge.source.last;
     if(!control_ready)++coverage_.control_stalls;
     if(control_ready){
       Control c{edge.source,{},first,counters_.total_rows(),owner_};
       for(unsigned i=0;i<3;++i)if(edge.source.physical[i]&&edge.source.fire[i]){
         const auto&r=edge.source.request[i];auto&b=banks_.at(r.bank);
         if(b.pending)throw std::logic_error("two execute requests use the same physical SRAM edge");
         Response response{i,r.bank,r.row,++serial_,owner_};b.pending=response;c.response[i]=response;edge.reads.push_back(response);++coverage_.reads;
       }
       control_.push_back(std::move(c));
     }
   }
   coverage_.control_peak=std::max(coverage_.control_peak,unsigned(control_.size()));
   if(control_.size()>5)throw std::logic_error("original execute control Queue5 overflow");
   return edge;
 }
};
// MeshWithDelays.scala95-145: one replaceable register for each A/B/D
// operand and one original request. Tags/row-count queue readiness is an
// external input; it must never be replaced by an unbounded request credit.
class MeshOperandRegisters {
 unsigned total_,row_=0;std::uint64_t owner_=0;bool request_=false;std::array<bool,3>written_{};
 public:
 explicit MeshOperandRegisters(unsigned total):total_(total){if(total<4||total>16)throw std::invalid_argument("selected mesh total_rows");}
 bool row_fire()const{return request_&&written_[0]&&written_[1]&&written_[2];}
 bool last()const{return row_fire()&&row_+1==total_;}
 bool busy()const{return request_;}
 unsigned row()const{return row_;}
 unsigned total_rows()const{return total_;}
 std::uint64_t owner()const{return owner_;}
 ExecuteOperandPipeline::Mesh signals(bool tag_ready=true)const{
   const bool next=row_fire(),req=(!request_||last())&&tag_ready;
   return {{{!written_[0]||next||req,!written_[1]||next||req,!written_[2]||next||req}},req};
 }
 void step(const ExecuteOperandPipeline::Edge&edge){
   const bool next=row_fire(),final=last();
   if(next){written_.fill(false);row_=row_+1==total_?0:row_+1;}
   if(edge.request_fire){request_=true;total_=edge.request_rows;owner_=edge.request_owner;}
   else if(final)request_=false;
   for(unsigned i=0;i<3;++i)if(edge.mesh_fire[i])written_[i]=true;
 }
};
}
#endif
