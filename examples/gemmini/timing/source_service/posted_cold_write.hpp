#ifndef GEMMINI_POSTED_COLD_WRITE_HPP
#define GEMMINI_POSTED_COLD_WRITE_HPP
#include "registered_transport.hpp"
#include <timing/write_transaction.hpp>
#include <array>
#include <set>
namespace gemmini_annotated_spike {
// Selected SourceA/C/E and SinkD ownership, independent of SourceD S4.
// Opt-in zero-offset requests execute after the first GrantData notice and
// read only accepted fill beats. Offset requests retain the source last-beat
// guard. GrantAck, complete outer data and inner publication remain distinct.
class PostedColdWrite {
 using Q=merlin_timing::PostedTimeline;using Token=Q::Token;using Cycle=merlin_timing::Cycle;
 public:
 enum class Port {sinkd_noop,sinkd_data,sourcec_read};
 using CachePort=std::function<void(std::uint64_t,Port,Cycle,Token)>;
 using Lower=std::function<void(Cycle,Cycle,Cycle,Token)>;
 using Bus=std::function<void(Cycle,Token)>;
 using Ready=std::function<void(Cycle)>;
 struct OwnedServices{CachePort port;Lower lower;Bus bus;};
 struct Fill {bool first_allowed=false;std::function<void(std::size_t,Cycle)>published;};
 private:
 struct Lease{std::uint64_t set;Token publication;Ready admitted;bool published=false,source_closed=true;};
 struct Miss{spike_timing::WriteMissV5 law;std::shared_ptr<Lease>lease;Ready ready,writeback;Lower lower_write;
   bool release_ack=false,grant_ack=false,private_closed=true,grant_last=false;
   std::optional<Fill>fill;
   std::vector<std::vector<Token>>read_dependencies;std::vector<Token>read_accepted,read_reusable;std::shared_ptr<OwnedServices>services;};
 struct D{unsigned kind;std::uint64_t address;std::size_t beats,next=0;bool grant;Ready done,acknowledged,first;std::function<void(std::size_t,Cycle)>published;std::optional<Token>upstream;bool early_ack=false;std::shared_ptr<OwnedServices>services;};
 struct C{std::shared_ptr<Miss>miss;std::size_t next=0;};
 struct ABeat{std::shared_ptr<Miss>miss;std::size_t beat;Token consumed;};
 struct ARead{std::shared_ptr<Miss>miss;Token consumed;};
 Q&q_;CachePort port_;Lower lower_;Bus bus_;
 PostedRegisteredTransport source_a_,source_c_,cork_cack_,cork_grant_,sink_d_,source_e_;
 std::size_t live_=0,peak_=0,sinks_=0,sink_peak_=0;
 std::map<std::uint64_t,std::shared_ptr<Lease>>leases_;
 std::map<std::uint64_t,std::shared_ptr<Miss>>misses_;
 std::deque<std::shared_ptr<Lease>>waiting_;std::array<std::deque<std::shared_ptr<D>>,3>d_;
 std::shared_ptr<D>current_d_;std::optional<Cycle>last_d_,last_admit_,wake_at_;
 bool d_scheduled_=false,d_inflight_=false;
 std::deque<std::shared_ptr<C>>c_wait_;bool c_busy_=false;std::optional<Cycle>c_wake_,last_c_;
 std::deque<ABeat>a_dirty_;std::deque<ARead>a_read_;std::shared_ptr<Miss>a_frame_;
 std::optional<Cycle>a_wake_,last_a_;bool a_inflight_=false;
 Token token(){auto t=q_.token();if(!t)throw std::runtime_error("cold write token budget");return *t;}
 void wake_later(Cycle at){
   if(wake_at_&&*wake_at_<=at)return;
   wake_at_=at;
   q_.post(at,{},[this,at](auto&,auto now){if(wake_at_!=std::optional<Cycle>{at})return;wake_at_.reset();wake(now);},Q::Kind::source_arrival);
 }
 void finish_lease(const std::shared_ptr<Lease>&l,Cycle at){
   if(!l->published||!l->source_closed)return;
   if(!live_||!leases_.erase(l->set)){q_.fail("cold write MSHR ownership underflow");return;}
   for(auto i=misses_.begin();i!=misses_.end();)if(i->second->lease==l)i=misses_.erase(i);else ++i;
   --live_;wake_later(at+1);
 }
 void close_source(const std::shared_ptr<Miss>&m,Cycle at){
   if(m->release_ack&&m->grant_ack&&m->private_closed&&m->grant_last){m->lease->source_closed=true;finish_lease(m->lease,at);}
 }
 void wake(Cycle at){
   if(waiting_.empty())return;
   if(last_admit_==std::optional<Cycle>{at}){wake_later(at+1);return;}
   for(auto i=waiting_.begin();i!=waiting_.end()&&live_<10;++i){auto l=*i;
     if(leases_.count(l->set))continue;
     waiting_.erase(i);++live_;peak_=std::max(peak_,live_);leases_.emplace(l->set,l);last_admit_=at;
     q_.post(at,{l->publication},[this,l](auto&,auto t){l->published=true;finish_lease(l,t);},Q::Kind::command_retire);
     l->admitted(at);if(!waiting_.empty())wake_later(at+1);break;
   }
 }
 void request_d(unsigned kind,std::uint64_t address,std::size_t beats,bool grant,Ready done,Ready acknowledged,Cycle at,std::optional<Token>upstream={},Ready first={},std::function<void(std::size_t,Cycle)>published={},bool early_ack=false,std::shared_ptr<OwnedServices>services={}){
   // Each of the ten physical MSHRs can own both a memory GrantData and
   // a dirty ReleaseAck in class0. These are software records for existing
   // owners, not extra MSHRs, sinks, TileLink credits or payload storage.
   const std::size_t custody=kind==0?2*10:10;
   if(kind>=d_.size()||!beats||beats>8||d_[kind].size()>=custody){q_.fail("cold write D transaction/custody bound");return;}
   d_[kind].push_back(std::make_shared<D>(D{kind,address,beats,0,grant,std::move(done),std::move(acknowledged),std::move(first),std::move(published),upstream,early_ack,std::move(services)}));kick_d(at);
 }
 void kick_d(Cycle at){
   if(d_scheduled_)return;
   d_scheduled_=true;
   q_.post(std::max(at,last_d_?*last_d_+1:at),{},[this](auto&,auto t){d_scheduled_=false;dispatch_d(t);},Q::Kind::response_beat);
 }
 void dispatch_d(Cycle at){
   if(d_inflight_)return;
   if(!current_d_)for(auto&pending:d_)if(!pending.empty()){
     if(pending.front()->grant&&sinks_==8)continue;
     current_d_=pending.front();pending.pop_front();
     if(current_d_->grant){++sinks_;sink_peak_=std::max(sink_peak_,sinks_);}break;
   }
   if(!current_d_)return;
   auto d=current_d_;d_inflight_=true;
   auto offer=[this,d](Cycle at){
     const auto beat=d->next;
     auto entered=sink_d_.push([this,d,beat](Cycle time,Token consumed){
       auto accepted=token();(d->services?d->services->port:port_)(d->address+beat*8,d->beats==1?Port::sinkd_noop:Port::sinkd_data,time,accepted);
       q_.post(time,{accepted},[this,d,beat,consumed](auto&,auto t){
         q_.complete(consumed);
         if(d->published)d->published(beat,t);
         if(!beat&&(d->first||d->early_ack))q_.post(t+1,{},[this,d](auto&,auto now){
           if(d->first)d->first(now);
           if(d->early_ack)acknowledge_grant(d,now);
         },Q::Kind::response_beat);
         if(beat+1==d->beats)q_.post(t+1,{},[this,d](auto&,auto now){
           d->done(now);
           if(d->grant&&!d->early_ack)acknowledge_grant(d,now);
         },Q::Kind::response_beat);
       },Q::Kind::response_beat);
     },at);
     q_.post(at,{entered},[this,d](auto&,auto t){
       d_inflight_=false;if(!d->next&&d->upstream)q_.complete(*d->upstream);last_d_=t;
       if(++d->next==d->beats)current_d_.reset();
       kick_d(t);
     },Q::Kind::response_beat);
   };
   // Real memory D owns its beat service before SinkD's registered queue.
   // Cork's internally synthesized Grant/ReleaseAck is not a DRAM data beat.
   if(d->kind==0&&d->beats>1){auto accepted=token();(d->services?d->services->bus:bus_)(at,accepted);
     q_.post(at,{accepted},[offer](auto&,auto t){offer(t);},Q::Kind::response_beat);
   }else offer(at);
 }
 void acknowledge_grant(const std::shared_ptr<D>&d,Cycle at){
   source_e_.push([this,d](Cycle t,Token consumed){
     if(!sinks_){q_.fail("cold write Cork sink underflow");return;}
     --sinks_;q_.complete(consumed);if(d->acknowledged)d->acknowledged(t);kick_d(t);
   },at);
 }
 void kick_a(Cycle at){
   if(a_wake_&&*a_wake_<=at)return;
   a_wake_=at;
   q_.post(std::max(at,last_a_?*last_a_+1:at),{},[this,at](auto&,auto t){if(a_wake_!=std::optional<Cycle>{at})return;a_wake_.reset();dispatch_a(t);},Q::Kind::source_arrival);
 }
 void dispatch_a(Cycle at){
   if(a_inflight_)return;
   if(!a_dirty_.empty()&&(!a_frame_||a_dirty_.front().miss==a_frame_)){
     auto beat=a_dirty_.front();a_dirty_.pop_front();if(!a_frame_)a_frame_=beat.miss;a_inflight_=true;
     auto accepted=token();(beat.miss->services?beat.miss->services->bus:bus_)(at,accepted);
     q_.post(at,{accepted},[this,beat](auto&,auto t){
       q_.complete(beat.consumed);last_a_=t;a_inflight_=false;kick_c(t+1);
       if(beat.beat==7){
         a_frame_.reset();auto returned=token();const auto&m=beat.miss;
         m->lower_write(m->law.release_latency,m->law.release_bus,t,returned);
         q_.post(t,{returned},[this,m](auto&,auto now){
           // A real memory response has Cork's highest D priority. It is a
           // ReleaseAck/no-data SinkD handshake, not a new data line fill.
           request_d(0,*m->law.evicted_line*64,1,false,[this,m](Cycle ack){
             if(m->writeback)m->writeback(ack);
             m->release_ack=true;close_source(m,ack);
           },{},now,{}, {},{},false,m->services);
         },Q::Kind::response_beat);
       }
       kick_a(t+1);
     },Q::Kind::source_arrival);return;
   }
   if(a_frame_||a_read_.empty())return;
   auto read=a_read_.front();a_read_.pop_front();q_.complete(read.consumed);last_a_=at;
   auto returned=token();(read.miss->services?read.miss->services->lower:lower_)(read.miss->law.fill_latency,read.miss->law.fill_bus,at,returned);
   q_.post(at,{returned},[this,m=read.miss](auto&,auto now){grant(m,0,8,now);},Q::Kind::response_beat);kick_a(at+1);
 }
 void grant(const std::shared_ptr<Miss>&m,unsigned kind,std::size_t beats,Cycle at,std::optional<Token>upstream={}){
   const bool early=m->fill&&m->fill->first_allowed&&beats>1;
   request_d(kind,m->law.line*64,beats,true,[this,m,early](Cycle t){
     m->grant_last=true;if(!early)m->ready(t);close_source(m,t);
   },[this,m](Cycle t){m->grant_ack=true;close_source(m,t);},at,upstream,
     early?m->ready:Ready{},m->fill?m->fill->published:std::function<void(std::size_t,Cycle)>{},bool(m->fill),m->services);
 }
 void acquire(const std::shared_ptr<Miss>&m,Cycle at){
   source_a_.push([this,m](Cycle t,Token consumed){
     if(!m->law.acquire_block){auto entered=cork_grant_.push([this,m](Cycle time,Token accepted){grant(m,2,1,time,accepted);},t);
       q_.post(t,{entered},[consumed](auto&q,auto){q.complete(consumed);},Q::Kind::source_arrival);
     }else{if(a_read_.size()>=10){q_.fail("cold outer Get custody bound");return;}a_read_.push_back({m,consumed});kick_a(t);}
   },at);
 }
 void kick_c(Cycle at){
   if(c_wake_&&*c_wake_<=at)return;
   c_wake_=at;
   q_.post(at,{},[this,at](auto&,auto t){if(c_wake_!=std::optional<Cycle>{at})return;c_wake_.reset();capture_c(t);},Q::Kind::source_arrival);
 }
 bool room_c(Cycle at)const{
   const auto edge=source_c_.previous_edge(0,at);
   return edge.begin==0||((edge.begin==1||edge.begin==2)&&!edge.enqueued);
 }
 void enqueue_c(const std::shared_ptr<C>&c,std::size_t beat,Cycle at){
   auto entered=source_c_.push([this,c,beat](Cycle t,Token consumed){
     if(c->miss->law.dirty_eviction){
       if(a_dirty_.size()>=12){q_.fail("SourceC payload custody bound");return;}
       a_dirty_.push_back({c->miss,beat,consumed});kick_a(t);
     }else{auto next=cork_cack_.push([this,m=c->miss](Cycle time,Token accepted){
       request_d(1,*m->law.evicted_line*64,1,false,[this,m](Cycle ack){m->release_ack=true;close_source(m,ack);},{},time,accepted,{}, {},false,m->services);
     },t);q_.post(t,{next},[this,consumed](auto&q,auto now){q.complete(consumed);kick_c(now+1);},Q::Kind::source_arrival);}
   },at);
   q_.post(at,{entered},[this](auto&,auto t){kick_c(t+1);},Q::Kind::source_arrival);
 }
 void read_c(const std::shared_ptr<C>&c,Cycle at){
   const auto beat=c->next;auto accepted=token();
   const auto dependencies=c->miss->read_dependencies.empty()?std::vector<Token>{}:c->miss->read_dependencies.at(beat);
   q_.post(at,dependencies,[this,c,beat,accepted](auto&,auto t){
     (c->miss->services?c->miss->services->port:port_)(*c->miss->law.evicted_line*64+beat*8,Port::sourcec_read,t,accepted);
   },Q::Kind::operand_consume);
   q_.post(at,{accepted},[this,c,beat](auto&,auto t){
     q_.complete(c->miss->read_accepted.at(beat));
     q_.post(t+1,{},[c,beat](auto&q,auto){q.complete(c->miss->read_reusable.at(beat));},Q::Kind::operand_consume);
     q_.post(t+2,{},[this,c,beat](auto&,auto now){enqueue_c(c,beat,now);},Q::Kind::response_beat);
     if(++c->next==8){c_busy_=false;kick_c(t+1);}else q_.post(t+1,{},[this,c](auto&,auto now){read_c(c,now);},Q::Kind::operand_consume);
   },Q::Kind::operand_consume);
 }
 void capture_c(Cycle at){
   if(c_busy_||c_wait_.empty())return;
   if(last_c_==std::optional<Cycle>{at}){kick_c(at+1);return;}
   if(!room_c(at)){if(source_c_.occupancy()<=2)kick_c(at+1);return;}
   auto c=c_wait_.front();c_wait_.pop_front();last_c_=at;
   // MSHR s_release is registered on SourceC request capture; Acquire can
   // issue next edge while old data/ReleaseAck is still independently owned.
   q_.post(at+1,{},[this,m=c->miss](auto&,auto t){acquire(m,t);},Q::Kind::source_arrival);
   if(c->miss->law.dirty_eviction){c_busy_=true;read_c(c,at);}
   else{q_.post(at+2,{},[this,c](auto&,auto t){enqueue_c(c,0,t);},Q::Kind::source_arrival);kick_c(at+1);}
 }
 public:
 PostedColdWrite(Q&q,CachePort port,Lower lower,Bus bus={}):q_(q),port_(std::move(port)),lower_(std::move(lower)),bus_(std::move(bus)),
 source_a_(q,{{2,false}}),source_c_(q,{{12,false}}),cork_cack_(q,{{2,false}}),cork_grant_(q,{{2,false}}),sink_d_(q,{{2,false}}),source_e_(q,{{2,false}}){
   if(!port_||!lower_)throw std::invalid_argument("cold write requires actual port/lower owners");
   if(!bus_)bus_=[this](Cycle,Token done){q_.complete(done);};
 }
 struct AdmissionStatus{std::size_t live,waiting;bool owns_set;};
 AdmissionStatus admission_status(std::uint64_t set)const{return {live_,waiting_.size(),leases_.count(set)!=0};}
 void admit(std::uint64_t set,Token publication,Ready admitted,Cycle at){
   // A pending record belongs to an already existing upstream transaction:
   // StreamReader16 + StreamWriter16 + at most two line children of the one
   // scalar CPU access. This is software custody, not a 34-entry hardware
   // queue. wake() still admits only the actual ten demand MSHRs, and each
   // producer retains its original source/payload credit while waiting.
   constexpr std::size_t upstream_owners=16+16+2;
   if(!admitted){q_.fail("cold write MSHR request custody bound");return;}
   // Native CPU requests also enter here outside timeline dispatch. Neither
   // their admission nor an older waiting device callback may execute on that
   // host stack. Offer the original request at its causal edge; the callback
   // still runs on that SAME edge when a real MSHR is available.
   q_.post(at,{},[this,set,publication,admitted=std::move(admitted)](auto&,auto now)mutable{
     if(waiting_.size()>=upstream_owners){q_.fail("cold write MSHR request custody bound");return;}
     waiting_.push_back(std::make_shared<Lease>(Lease{set,publication,std::move(admitted)}));wake(now);
   },Q::Kind::source_arrival);
 }
 void push(const spike_timing::WriteMissV5&law,Ready ready,Ready writeback,Lower lower_write,Cycle at,std::vector<std::vector<Token>>read_dependencies={},std::optional<Token>last_response={},std::optional<Fill>fill={},std::shared_ptr<OwnedServices>services={}){
   const auto lease=leases_.find(law.set);
   if(lease==leases_.end()){q_.fail("cold write source has no admitted MSHR");return;}
   if(law.dirty_eviction&&(!law.evicted_line||law.release_writes.empty()||!writeback||!lower_write)){
     q_.fail("dirty writeback requires distinct original DRAM publication owner");return;
   }
   auto m=std::make_shared<Miss>(Miss{law,lease->second,std::move(ready),std::move(writeback),std::move(lower_write),!law.evicted_line,false,!last_response,false,std::move(fill),std::move(read_dependencies),{}, {},std::move(services)});
   if(law.dirty_eviction)for(unsigned b=0;b<8;++b){m->read_accepted.push_back(token());m->read_reusable.push_back(token());}
   if(!misses_.emplace(law.line,m).second){q_.fail("duplicate cold target line owner");return;}
   if(last_response)q_.post(at,{*last_response},[this,m](auto&,auto t){m->private_closed=true;close_source(m,t);},Q::Kind::response_beat);
   m->lease->source_closed=false;
   if(!law.evicted_line)acquire(m,at);
   else{if(c_wait_.size()>=10){q_.fail("SourceC MSHR custody bound");return;}c_wait_.push_back(std::make_shared<C>(C{m}));kick_c(at);}
 }
 void push(const spike_timing::WriteMissV4&law,Ready ready,Cycle at){
   if(law.dirty_eviction){q_.fail("cold write dirty victim requires V5 owner");return;}
   spike_timing::WriteMissV5 extended;static_cast<spike_timing::WriteMissV4&>(extended)=law;push(extended,std::move(ready),{},{},at);
 }
 // SourceC's continuously valid higher-priority mask must remain visible
 // even while payload publication delays its SRAM acceptance. The actor
 // models that ownership as exact byte-chunk WAR edges, not a whole-release
 // drain: SourceDw may overwrite each8B chunk on the edge after its old
 // read accepted (the same edge's physical SRAM port remains occupied).
 std::vector<Token>write_dependencies(std::uint64_t address,std::uint64_t mask)const{
   const auto i=misses_.find(address/64);if(i==misses_.end()||i->second->read_accepted.empty())return {};
   std::vector<Token>out;
   for(unsigned b=0;b<16;++b)if(mask&(1ull<<b)){
     if(address%64+b>=64)throw std::invalid_argument("cold S4 write crosses original line");
     const auto t=i->second->read_reusable.at((address%64+b)/8);
     if(out.empty()||out.back().id!=t.id)out.push_back(t);
   }
   return out;
 }
 std::size_t peak_mshrs()const{return peak_;}std::size_t peak_sinks()const{return sink_peak_;}
 bool busy()const{return live_||sinks_||!waiting_.empty()||current_d_||!c_wait_.empty()||c_busy_||!a_dirty_.empty()||!a_read_.empty()||a_frame_||source_a_.busy()||source_c_.busy()||cork_cack_.busy()||cork_grant_.busy()||sink_d_.busy()||source_e_.busy();}
};
}
#endif
