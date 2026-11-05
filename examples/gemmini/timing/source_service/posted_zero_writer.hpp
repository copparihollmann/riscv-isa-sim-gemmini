#ifndef GEMMINI_POSTED_ZERO_WRITER_HPP
#define GEMMINI_POSTED_ZERO_WRITER_HPP
#include <merlin_timing/posted_timeline.hpp>
#include <memory>
#include <vector>
#include <functional>
#include <optional>
#include <algorithm>
namespace gemmini_annotated_spike {
// Selected ZeroWriter request register and registered PixelRepeater (repeat1).
// No StreamReader, TLB, transaction tracker, TileLink or cache request exists.
class PostedZeroWriter {
 using Q=merlin_timing::PostedTimeline;using Cycle=merlin_timing::Cycle;
 public:
 struct Row{std::uint64_t address,mask;std::function<void(Cycle)> published;std::optional<merlin_timing::StageOrigin>origin={};};
 using Ready=std::function<bool(const Row&,Cycle)>;
 using Write=std::function<void(const Row&,Cycle)>;
 using Accepted=std::function<void(Cycle)>;
 using PortWrite=std::function<void(const Row&,Cycle,Accepted)>;
 private:
 struct Request{std::vector<Row>rows;std::size_t next=0;Cycle visible=0;Accepted accepted;};
 struct Pixel{Row row;Cycle visible;};
 Q&q_;Ready ready_;PortWrite write_;std::shared_ptr<Request>request_,waiting_;std::optional<Pixel>pixel_;bool port_pending_=false;
 std::optional<Cycle>scheduled_,settled_;std::size_t peak_=0;
 void kick(Cycle at){
   if(settled_==std::optional<Cycle>{at})++at;
   if(scheduled_&&*scheduled_<=at)return;
   scheduled_=at;q_.post_settled(at,{},[this,at](auto&,auto now){if(scheduled_!=std::optional<Cycle>{at})return;scheduled_.reset();tick(now);},Q::Kind::local_publish);
 }
 void tick(Cycle at){
   settled_=at;
   if(pixel_&&!port_pending_&&pixel_->visible<=at&&ready_(pixel_->row,at)){
     port_pending_=true;
     write_(pixel_->row,at,[this](Cycle accepted){
       if(!pixel_||!port_pending_){q_.fail("zero writer lost held local port owner");return;}
       pixel_.reset();port_pending_=false;advance(accepted);
     });return;
   }
   advance(at);
 }
 void advance(Cycle at){
   if(!pixel_&&request_&&request_->visible<=at){
     pixel_=Pixel{request_->rows.at(request_->next++),at+1};
     if(request_->next==request_->rows.size())request_.reset();
   }
   // Both RTL registers can replace on their final output fire. Newly
   // captured contents still become visible only on the following edge.
   if(!request_&&waiting_){request_=std::move(waiting_);request_->visible=at+1;auto accepted=std::move(request_->accepted);accepted(at);}
   peak_=std::max(peak_,std::size_t(bool(request_))+std::size_t(bool(pixel_)));
   if(request_||pixel_||waiting_)kick(at+1);
 }
 public:
 PostedZeroWriter(Q&q,Ready ready,PortWrite write):q_(q),ready_(std::move(ready)),write_(std::move(write)){
   if(!ready_||!write_)throw std::invalid_argument("zero writer requires original local port owners");
 }
 PostedZeroWriter(Q&q,Ready ready,Write write):PostedZeroWriter(q,std::move(ready),[write=std::move(write)](const Row&r,Cycle at,Accepted accepted){write(r,at);accepted(at);}){}
 void push(std::vector<Row>rows,Accepted accepted,Cycle at){
   if(rows.empty()||rows.size()>4||!accepted){q_.fail("zero writer original row geometry unavailable");return;}
   for(auto r:rows)if(!r.mask||(r.mask&~0xffffull)){q_.fail("zero writer invalid original column mask");return;}
   q_.post(at,{},[this,rows=std::move(rows),accepted=std::move(accepted)](auto&,auto now)mutable{
     // This is the one LoadController request held while req.ready is low,
     // not a new hardware queue or a second ZeroWriter input register.
     if(waiting_){q_.fail("multiple zero writer upstream request owners");return;}
     waiting_=std::make_shared<Request>(Request{std::move(rows),0,0,std::move(accepted)});kick(now);
   },Q::Kind::source_arrival);
 }
 std::size_t peak_registers()const{return peak_;}
 bool busy()const{return request_||pixel_||waiting_;}
};
}
#endif
