#ifndef GEMMINI_POSTED_SOURCE_TIMELINE_HPP
#define GEMMINI_POSTED_SOURCE_TIMELINE_HPP
#include "provider.hpp"
#include "staged.hpp"
#include "registered_transport.hpp"
#include "posted_readout_frontend.hpp"
#include "posted_one_beat_writer.hpp"
#include "posted_source_d.hpp"
#include "posted_full_packet_writer.hpp"
#include "posted_cold_write.hpp"
#include "posted_victim_probe.hpp"
#include "posted_banked_store.hpp"
#include "posted_accumulator.hpp"
#include "posted_zero_writer.hpp"
#include "posted_read_allocation.hpp"
#include "execute_operand_pipeline.hpp"
#include "execute_mesh_tags.hpp"
#include <timing/write_transaction.hpp>
#include <timing/provider.hpp>
#include <timing/source_actor.hpp>
#include <merlin_timing/posted_engine_stage.hpp>
#include <merlin_timing/memory_milestones.hpp>
#include <deque>
#include <memory>
#include <map>
namespace gemmini_annotated_spike {
// Opt-in causal composition experiment. Source commands, native CPU requests,
// actual memory lookups and local-port commits share ONE dispatch clock. No
// command books a future bank before its source/data dependencies accept.
// Scalar memory service remains a conservative packet-completion bound; this
// implementation does NOT claim a source-closed inclusive-cache/MSHR schedule.
class PostedSourceObserver {
 using Q=merlin_timing::PostedTimeline;using Token=Q::Token;
 using Stage=merlin_timing::OwnedStage;
 struct Row {std::optional<Token> writer;std::vector<Token> readers;};
 struct Command {
   std::string kind;Stage original;std::optional<Cycle> occupancy;
   std::uint32_t funct;std::uint64_t rs1,rs2;std::optional<TransferPhase> phase;
   std::vector<Transfer> transfers;std::size_t group;
   Token start,consume,done;std::vector<Token> dependencies,output_dependencies;
   std::vector<ValueId> sp_reads,acc_reads,outputs;std::map<ValueId,Token> row_ready;
   std::map<ValueId,std::vector<Token>>row_dependencies;
   std::size_t local_store_remaining=0;
   std::optional<Token>store_output_done,store_credit_free;
   bool started=false,finished=false;
 };
 using ActorRole=spike_timing::SourceActorRoleV1;
 std::optional<spike_timing::SourceActorSinkV1>actor_sink_;
 std::map<std::uint64_t,ActorRole>actor_done_;
 void actor(ActorRole role,std::uint64_t id,Cycle at,bool begin){if(actor_sink_)actor_sink_->edge(actor_sink_->opaque,role,id,at,begin);}
 void actor_done(Token t,Cycle at){auto i=actor_done_.find(t.id);if(i!=actor_done_.end()){actor(i->second,t.id,at,false);actor_done_.erase(i);}}
 spike_timing::Services&s_;Q&q_;HardwareConfig h_;StagedConfig config_;ValueId base_;
 std::unique_ptr<PostedAccumulator>accumulator_ports_;
 std::vector<ResourceId>accumulator_banks_;std::uint64_t accumulator_bank_rows_=0;
 std::map<ValueId,Row> rows_;std::array<std::deque<std::shared_ptr<Command>>,3> queues_;
 std::array<std::vector<std::shared_ptr<Command>>,3> active_;
 std::array<std::optional<Token>,3> last_issue_;
 std::array<std::vector<std::shared_ptr<Command>>,3> controller_wait_;
 std::array<std::size_t,2>dma_active_{};bool ws_unit_=false;
 std::unique_ptr<PostedRegisteredTransport>reader_request_path_,reader_response_path_,shared_a_path_,shared_d_path_;
 std::unique_ptr<PostedReadoutFrontend>readout_frontend_;
 std::unique_ptr<PostedOneBeatWriter>one_beat_writer_;
 std::unique_ptr<PostedRegisteredTransport>full_acc_load_path_;
 std::optional<Cycle>last_sp_output_at_,last_mvin_response_at_;
 std::set<const void*>full_acc_last_pending_;
 std::unique_ptr<PostedZeroWriter>zero_writer_;
 std::unique_ptr<PostedOneBeatSourceD>source_d_;
 std::optional<spike_timing::WriteTransactionServiceV1>write_service_;
 std::optional<spike_timing::WriteTransactionServiceV2>write_service_v2_;
 std::optional<spike_timing::FullWritePacketServiceV3>full_packet_service_;
 std::optional<spike_timing::MaskedWriteServiceV8>masked_packet_service_;
 std::optional<spike_timing::MaskedWriteServiceV9>masked_packet_service_v9_;bool resident_dirty_put_retirement_=false;
 bool masked_packets_=false,ordered_dirty_puts_=false,store_request_release_=false,store_local_completion_=false;
 std::map<std::uint64_t,Token>pending_store_obligations_;
 std::optional<Cycle>last_store_completion_at_;
 struct PendingOrderedWrite{std::uint64_t line;Token published,consumed;};
 std::map<ValueId,PendingOrderedWrite>ordered_writes_;
 std::unique_ptr<PostedFullPacketWriter>full_packet_writer_;
 std::unique_ptr<PostedFullPacketSourceD>full_packet_source_d_;
 std::optional<spike_timing::ColdWriteServiceV4>cold_write_service_;
 std::optional<spike_timing::ColdWriteServiceV5>cold_write_service_v5_;
 std::optional<spike_timing::ColdWriteServiceV6>cold_write_service_v6_;
 std::unique_ptr<PostedVictimProbe>victim_probe_;
 std::optional<spike_timing::ReadAllocationServiceV7>read_allocation_service_v7_;
 std::shared_ptr<PostedSourceDPipeline>source_d_pipeline_;
 std::optional<Token>source_d_free_,source_d_last_read_response_;
 std::unique_ptr<PostedReadAllocationResponse>read_allocation_response_;bool read_input_retirement_=false,resident_get_retirement_=false,beat_forwarding_=false,deferred_read_lookup_=false,ws_first_row_=false,ws_total_rows_completion_=false,ws_garbage_preload_rows_=false;
 struct FillWindow{bool first_allowed;std::vector<Token>chunks;};
 std::map<std::uint64_t,merlin_timing::StageOrigin>victim_origins_;
 std::unique_ptr<PostedColdWrite>cold_write_;
 std::unique_ptr<PostedBankedStore>cache_ports_;
 std::uint64_t cold_cache_sets_=0;
 std::vector<ResourceId>cache_banks_;
 bool i8_readout_=false,identity_i8_accumulator_load_=false,ordered_pool_readout_=false;
 std::optional<Token>pool_writer_free_;
 std::optional<std::pair<std::uint64_t,std::uint64_t>>pool_register_;
 const Command*pool_register_owner_=nullptr;
 bool store_kind(const std::string&kind)const{return kind=="store"||(i8_readout_&&kind=="store_act1")||(ordered_pool_readout_&&(kind=="pool_store"||kind=="pool_store_act1"));}
 Token reader_request(PostedRegisteredTransport::Sink sink,Cycle at){
   if(!shared_a_path_)return reader_request_path_->push(std::move(sink),at);
   return reader_request_path_->push([this,sink=std::move(sink)](Cycle t,Token consumed)mutable{
     auto entered=shared_a_path_->push(std::move(sink),t);
     q_.post(t,{entered},[consumed](auto&q,auto){q.complete(consumed);},Q::Kind::source_arrival);
   },at);
 }
 Token reader_response(PostedRegisteredTransport::Sink sink,Cycle at){
   if(!shared_d_path_)return reader_response_path_->push(std::move(sink),at);
   return shared_d_path_->push([this,sink=std::move(sink)](Cycle t,Token consumed)mutable{
     auto entered=reader_response_path_->push(std::move(sink),t);
     q_.post(t,{entered},[consumed](auto&q,auto){q.complete(consumed);},Q::Kind::response_beat);
   },at);
 }
 Cycle inclusive_pipeline_extension_=0;bool memory_owned_reader_pipeline_=false;
 std::optional<merlin_timing::MemoryMilestoneQueryV2>lookup_query_;
 struct ReaderLease{std::size_t source=0;std::uint64_t generation=0,request=0;bool allocated=false;};
 std::array<bool,16>reader_slots_{};std::array<std::optional<Cycle>,16>reader_released_at_{};std::array<std::uint64_t,16>reader_generations_{};std::uint64_t reader_request_id_=0;
 void allocate_reader(const std::shared_ptr<ReaderLease>&lease){
   for(std::size_t i=0;i<reader_slots_.size();++i)if(!reader_slots_[i]&&reader_released_at_[i]!=std::optional<Cycle>{q_.now()}){
     if(reader_generations_[i]==UINT64_MAX||reader_request_id_==UINT64_MAX){fail("reader identity generation overflow");return;}
     reader_slots_[i]=true;lease->source=i;lease->generation=++reader_generations_[i];lease->request=++reader_request_id_;lease->allocated=true;actor(ActorRole::reader_slot,lease->request,q_.now(),true);return;
   }
   fail("reader accepted without source tracker credit");
 }
 void release_reader(const std::shared_ptr<ReaderLease>&lease){
   if(!lease||!lease->allocated||!reader_slots_.at(lease->source)||reader_generations_.at(lease->source)!=lease->generation){fail("reader source lease identity");return;}
   reader_slots_[lease->source]=false;reader_released_at_[lease->source]=q_.now();lease->allocated=false;actor(ActorRole::reader_slot,lease->request,q_.now(),false);
 }
 bool resident_lookup(const ReaderPacket&packet,const ReaderLease&lease,Cycle accepted){
   if(!lookup_query_||!lease.allocated){fail("registered reader requires exact native lookup observation");return false;}
   merlin_timing::MemoryRequestIdentityV1 request{lease.request,packet.address,packet.bytes,lease.source,lease.generation,accepted};
   merlin_timing::MemoryMilestonesV2 observed;
   if(!lookup_query_->last_observation(lookup_query_->opaque,&request,&observed) ||
      observed.detail_version!=2||observed.detail_size!=sizeof(observed)||!observed.lookup ||
      observed.request.request!=request.request||observed.request.address!=request.address||observed.request.bytes!=request.bytes||
      observed.request.return_source!=request.return_source||observed.request.return_generation!=request.return_generation||observed.request.accepted!=accepted ||
      !observed.lookup->read_hit_without_probe_or_eviction||observed.line_pending_at_lookup){
     fail("registered reader cache-stage law needs resident no-probe no-eviction ready-line lookup");return false;
   }
   return true;
 }
 bool registered_visibility_=false;std::array<std::size_t,3>controller_pending_{};
 std::optional<Token> pe_ready_;std::vector<Token> tags_;
 bool ws_operand_pipeline_=false,ws_tick_pending_=false;
 Cycle ws_next_tick_=0;
 std::optional<Cycle>ws_last_completion_;
 std::unique_ptr<ExecuteOperandPipeline>ws_feed_;
 MeshOperandRegisters ws_mesh_{16};ExecuteMeshTags ws_mesh_tags_;
 struct WsStream {std::shared_ptr<Command>command,paired;};
 std::map<std::uint64_t,WsStream>ws_streams_;
 std::map<std::uint64_t,std::shared_ptr<Command>>ws_tag_commands_;
 std::deque<std::pair<Cycle,std::shared_ptr<Command>>>ws_pending_completed_;
 std::map<std::uint64_t,Token>ws_pending_rows_;
 std::vector<std::shared_ptr<Command>> commands_;
 struct Coverage{std::size_t peak_reader=0,peak_q=0,peak_ring=0;std::uint64_t port_blocked=0,merger_blocked=0;} coverage_;
 bool physical(ValueId row)const{return row>=base_&&row<base_+h_.scratchpad_rows+h_.accumulator_rows;}
 bool sp(ValueId row)const{return row>=base_&&row<base_+h_.scratchpad_rows;}
 bool acc(ValueId row)const{return row>=base_+h_.scratchpad_rows&&physical(row);}
 static bool contains(const std::vector<ValueId>&v,ValueId row){return std::find(v.begin(),v.end(),row)!=v.end();}
 static std::optional<merlin_timing::StageOrigin> tag(const std::shared_ptr<Command>&c,const char*role){
   auto origin=c->original.origin;if(origin)origin->actor+="."+std::string(role);return origin;
 }
 void fail(const std::string&r){s_.unresolved("posted_source:"+r);q_.fail(r);}
 Token token(){auto t=q_.token();if(!t)throw std::runtime_error("posted source token allocation refused: "+q_.reason());return *t;}
 Cycle now(Cycle at=0)const{return std::max(at,q_.now());}
 bool ready(const std::vector<Token>&deps)const{for(auto t:deps)if(!q_.completed(t))return false;return true;}
 void once(Token t){if(!q_.completed(t))q_.complete(t);actor_done(t,q_.now());}
 void prune(std::size_t g){auto &v=active_[g];v.erase(std::remove_if(v.begin(),v.end(),[this](auto&c){return c->finished||q_.completed(c->done).has_value()||(c->kind=="compute_ws"&&q_.completed(c->consume).has_value());}),v.end());}
 void await(Token t){while(!q_.completed(t)&&!q_.progress().failed)if(!q_.step(true)){fail("blocked source dependency without a producer");break;}}
 void bank(Stage&stage,const std::vector<ValueId>&rows,Cycle duration){
   std::set<std::size_t> banks,acc_banks;bool accumulator=false;
   for(auto row:rows){if(sp(row))banks.insert((row-base_)/config_.scratchpad_bank_rows);else if(acc(row)){
     accumulator=true;if(!accumulator_banks_.empty())acc_banks.insert((row-base_-h_.scratchpad_rows)/accumulator_bank_rows_);
   }}
   for(auto b:banks){if(b>=config_.scratchpad_bank_resources.size()){fail("scratchpad bank outside selected facts");return;}
     stage.demands.push_back({config_.scratchpad_bank_resources[b],1,duration});}
   if(accumulator&&!accumulator_ports_){
     if(!accumulator_banks_.empty())for(auto b:acc_banks){
       if(b>=accumulator_banks_.size()){fail("accumulator bank outside selected LocalAddr geometry");return;}
       // Preserve the old conservative per-stage occupancy INSIDE each bank.
       // This only removes the artificial alias between independent memories;
       // it does not grant separate RMW/read/write throughput within a bank.
       stage.demands.push_back({accumulator_banks_[b],1,duration});
     }else{
       if(!config_.accumulator_storage_resource){fail("missing accumulator port");return;}
       stage.demands.push_back({*config_.accumulator_storage_resource,1,duration});
     }
   }
 }
 // A real scheduled stage, posted at source acceptance. The event's views are
 // copied and no Engine or cache state is touched until its callback dispatch.
 void stage(Stage work,std::vector<Token>deps,Token complete,std::function<void(const Result&)>accepted={}){
   const bool feed=work.origin&&work.origin->actor.size()>=5&&work.origin->actor.substr(work.origin->actor.size()-5)==".feed";
   if(accumulator_ports_&&((work.writes.size()==1&&acc(work.writes[0]))||(work.writes.empty()&&work.reads.size()==1&&acc(work.reads[0])) )){
     const bool write=!work.writes.empty();const auto row=write?work.writes[0]:work.reads[0];
     const bool rmw=write&&contains(work.reads,row);
     auto owned=std::make_shared<Stage>(std::move(work));const auto at=now(owned->earliest);
     q_.post(at,std::move(deps),[this,owned,row,write,rmw,complete,accepted=std::move(accepted)](auto&,auto t)mutable{
       accumulator_ports_->offer(row-base_-h_.scratchpad_rows,write,rmw,
         [this,owned](Cycle at){auto start=s_.engine.earliest_stage_start(owned->event(at));if(!start){fail("ACC row readiness unknown");return false;}return *start<=at;},
         [this,owned,complete,accepted=std::move(accepted)](Cycle at)mutable{
           const auto result=s_.engine.submit_detached(owned->event(at));
           if(result.start!=std::optional<Cycle>{at}||!result.ready){fail("ACC row admission changed");return;}
           if(accepted)accepted(result);
           q_.post(*result.ready,{},[this,complete](auto&,auto){once(complete);},Q::Kind::local_publish);
         },t,owned->origin&&owned->origin->actor.find(".acc_result_row")!=std::string::npos);
     },Q::Kind::operand_consume);return;
   }
   work.earliest=now(work.earliest);merlin_timing::PostedEngineStage::post(q_,s_.engine,std::move(work),std::move(deps),complete,
     [this,complete,feed,accepted=std::move(accepted)](const Result&r){
       if(feed&&r.start&&r.ready){actor(ActorRole::execute_feed,complete.id,*r.start,true);actor(ActorRole::execute_feed,complete.id,*r.ready,false);}
       if(r.ready)actor_done(complete,*r.ready);
       if(accepted)accepted(r);
     });
 }
 // RS acceptance and controller admission are DISTINCT. A CPU-posted
 // command is not visible as ExecuteController valid(1/2) until dependencies,
 // issue bandwidth and finite controller input capacity actually accept it.
 void request_issue(const std::shared_ptr<Command>&c,Cycle at){
   q_.post(now(at),c->dependencies,[this,c](auto&,auto time){try_issue(c,time);},Q::Kind::source_arrival);
 }
 void try_issue(const std::shared_ptr<Command>&c,Cycle at){
   const auto g=c->group;
   if(queues_[g].size()+controller_pending_[g]>=config_.controller_entries[g]){controller_wait_[g].push_back(c);return;}
   Stage issue;issue.origin=tag(c,"rs_issue");issue.earliest=at+(registered_visibility_?1:0);issue.latency=config_.issue_latency;
   issue.demands={{config_.issue_resources[g],1,config_.issue_occupancy}};
   auto accepted=token();
   stage(std::move(issue),{},accepted,[this,c,g](const auto&r){
     // Recheck the finite FIFO at the actual issue edge, not at the earlier
     // resource query. Other source actors may have filled it meanwhile.
     if(queues_[g].size()+controller_pending_[g]>=config_.controller_entries[g]){controller_wait_[g].push_back(c);return;}
     actor(static_cast<ActorRole>(std::size_t(ActorRole::load_rs_wait)+(g==0?0:g==2?1:2)),c->start.id,q_.now(),false);
     once(c->start);s_.feature("target.posted.issued",1);
     if(!registered_visibility_){queues_[g].push_back(c);schedule_next(g,*r.start);return;}
     // Entry.valid is registered before RS issue. A successful RS handshake
     // occupies downstream FIFO credit now; the non-flow controller head is
     // visible only after its actual queue pipeline, never on that same edge.
     ++controller_pending_[g];
     q_.post(*r.ready+(g==1?1:0),{},[this,c,g](auto&,auto visible){
       if(!controller_pending_[g]){fail("controller pending credit underflow");return;}
       --controller_pending_[g];queues_[g].push_back(c);schedule_next(g,visible);
     },Q::Kind::source_arrival);
   });
 }
 void schedule_next(std::size_t g,Cycle at){
   if(queues_[g].empty())return;
   auto c=queues_[g].front();
   if(g==1&&c->kind=="preload"&&queues_[g].size()<2)return;
   if(c->started)return;
   if((c->kind=="load"&&dma_active_[0]>=config_.dma_commands[0]) ||
      (store_kind(c->kind)&&dma_active_[1]>=config_.dma_commands[1]))return;
   c->started=true;
   q_.post(now(at),{},[this,c,g](auto&,auto time){
     if(c->kind=="load"){++dma_active_[0];load(c,time);}
     else if(c->kind=="preload")preload(c,time);
     else if(c->kind=="compute_ws")compute(c,time);
     else if(store_kind(c->kind)){++dma_active_[1];store(c,time);}
     else scalar(c,time);
   },Q::Kind::source_arrival);
 }
 void refill(std::size_t g,Cycle at){
   auto pending=std::move(controller_wait_[g]);controller_wait_[g].clear();
   for(auto c:pending)q_.post(now(at),{},[this,c](auto&,auto t){try_issue(c,t);},Q::Kind::source_arrival);
 }
 void pop(const std::shared_ptr<Command>&c,Cycle at){
   auto &v=queues_[c->group];if(v.empty()||v.front()!=c){fail("controller FIFO identity");return;}
   v.pop_front();refill(c->group,at);schedule_next(c->group,at);
 }
 void scalar(const std::shared_ptr<Command>&c,Cycle at){
   if(c->kind!="config"&&c->kind!="flush"){fail("unsupported posted primitive "+c->kind);return;}
   if(ws_operand_pipeline_&&c->group==1&&c->kind=="config"&&
      (ws_mesh_tags_.live_tag()||!ws_pending_completed_.empty()||ws_last_completion_==std::optional<Cycle>{at})){
     q_.post(at+1,{},[this,c](auto&,auto t){scalar(c,t);},Q::Kind::source_arrival);return;
   }
   if(!c->original.latency||!c->occupancy){fail("missing scalar price");return;}
   Stage work=c->original;work.earliest=at;work.latency=c->original.latency;
   work.demands={{config_.controller_resources[c->group],1,c->occupancy}};
   stage(std::move(work),{},c->done,[this,c](auto&r){
     q_.post(*r.ready,{},[this,c](auto&,auto t){once(c->consume);c->finished=true;pop(c,t);},Q::Kind::command_retire);
   });
 }
 void ws_kick(Cycle at){
   if(ws_tick_pending_)return;
   ws_tick_pending_=true;q_.post(std::max({at,q_.now(),ws_next_tick_}),{},[this](auto&,auto t){ws_tick(t);},Q::Kind::operand_consume);
 }
 void ws_tick(Cycle at){
   ws_tick_pending_=false;ws_next_tick_=at+1;
   std::optional<ExecuteMeshTags::Row>input;
   if(ws_mesh_.row_fire()){
     auto i=ws_streams_.find(ws_mesh_.owner());if(i==ws_streams_.end()){fail("mesh input stream owner lost");return;}
     input=ExecuteMeshTags::Row{ws_mesh_.owner(),ws_mesh_.row(),ws_mesh_.total_rows(),ws_mesh_.last()};
   }
   const auto mesh_edge=ws_mesh_tags_.edge(at,input);bool mesh_completion=false;
   for(const auto&out:mesh_edge.outputs){
     const auto stream=ws_streams_.find(out.owner);if(stream==ws_streams_.end()){fail("mesh output stream owner lost");return;}
     const auto c=stream->second.command;
     if(out.tag_owner){
       const auto tag=ws_tag_commands_.find(*out.tag_owner);
       if(tag==ws_tag_commands_.end()||c->kind!="compute_ws"){fail("mesh result requires its original preload/compute tag");return;}
       const auto expected=base_+h_.scratchpad_rows+(std::uint32_t(tag->second->rs2)&0x3fffffffu);
       if(out.row==0&&(c->outputs.size()!=std::min<std::uint64_t>(h_.dim,tag->second->rs2>>48)||c->outputs.size()>out.total)){
         fail("mesh result shape disagrees with original preload tag/total_rows");return;
       }
       if(out.row<c->outputs.size()){
         if(c->outputs[out.row]!=expected+out.row){fail("mesh result row disagrees with original preload C address");return;}
         Stage row;row.origin=tag_origin(c,"acc_result_row");row.earliest=at;row.latency=*config_.late_accumulator_write_pipeline;
         row.writes={c->outputs[out.row]};if(contains(c->acc_reads,c->outputs[out.row]))row.reads=row.writes;
         row.hold_reads_until_ready=true;
         const auto published=c->row_ready.at(c->outputs[out.row]);ws_pending_rows_.emplace(published.id,published);
         stage(std::move(row),c->row_dependencies[c->outputs[out.row]],published);
       }
       if(out.last){once(tag->second->done);tag->second->finished=true;ws_tag_commands_.erase(tag);mesh_completion=true;ws_last_completion_=at;}
     }else if(c->kind=="compute_ws"&&!c->outputs.empty()){
       fail("compute output has no original resident preload tag");return;
     }
     s_.feature("target.posted.execute_mesh_response_rows",1);
     if(out.last)ws_streams_.erase(stream);
   }
   // ExecuteController's mesh last-response has priority over the registered
   // two pending RS ids. Pending ids retain FIFO order and one completion/edge.
   if(!mesh_completion&&!ws_pending_completed_.empty()&&ws_pending_completed_.front().first<=at){
     auto c=ws_pending_completed_.front().second;ws_pending_completed_.pop_front();once(c->done);c->finished=true;ws_last_completion_=at;
   }
   // Output/EX completion is visible before the existing ACC/store settled
   // arbiters. SP read readiness instead sees actual higher-priority writes
   // already accepted on this edge. Keep those source decisions separate.
   q_.post_settled(at,{},[this,ready=mesh_edge.request_ready](auto&,auto t){ws_input_tick(t,ready);},Q::Kind::operand_consume);
 }
 void ws_input_tick(Cycle at,bool request_ready){
   std::array<bool,4>ports{true,true,true,true};
   if(!ws_feed_->source_consumed()){
     const auto offered=ws_feed_->offered();
     for(unsigned operand=0;operand<3;++operand)if(offered.physical[operand]){
       const auto&r=offered.request[operand];Stage read;read.earliest=at;read.latency=1;
       read.reads={base_+r.bank*config_.scratchpad_bank_rows+r.row};read.hold_reads_until_ready=true;bank(read,read.reads,1);
       const auto start=s_.engine.earliest_stage_start(read.event(at));if(!start){fail("execute SP row readiness unknown");return;}
       ports.at(r.bank)=*start<=at;
     }
     Stage busy;busy.origin=tag(ws_streams_.at(ws_feed_->source_owner()).command,"feed_controller_cycle");busy.earliest=at;busy.latency=0;busy.demands={{config_.controller_resources[1],1,1}};
     const auto r=s_.engine.submit_detached(busy.event(at));if(r.start!=std::optional<Cycle>{at}){fail("execute controller has another original owner");return;}
   }
   const auto source_owner=ws_feed_->source_owner();
   const auto edge=ws_feed_->step(ports,ws_mesh_.signals(request_ready));
   for(const auto&r:edge.reads){
     const auto owner=ws_streams_.find(r.owner);if(owner==ws_streams_.end()){fail("execute SP request owner lost");return;}
     Stage read;read.origin=tag_origin(owner->second.command,"sp_operand_row");read.earliest=at;read.latency=1;
     read.reads={base_+r.bank*config_.scratchpad_bank_rows+r.row};read.hold_reads_until_ready=true;bank(read,read.reads,1);
     const auto result=s_.engine.submit_detached(read.event(at));if(result.start!=std::optional<Cycle>{at}){fail("execute SP read admission changed on original edge");return;}
     s_.feature("target.posted.execute_sp_row_requests",1);
   }
   for(const auto&r:edge.consumed){(void)r;s_.feature("target.posted.execute_sp_row_responses",1);}
   if(edge.request_fire){
     const auto&stream=ws_streams_.at(edge.request_owner);const auto tag_command=stream.command->kind=="preload"?stream.command:stream.paired;
     std::optional<std::uint64_t>owner;if(tag_command&&std::uint32_t(tag_command->rs2)!=0xffffffffu)owner=tag_command->done.id;
     ws_mesh_tags_.accept(edge.request_owner,edge.request_rows,owner);
     s_.feature("target.posted.execute_mesh_requests",1);
   }
   ws_mesh_.step(edge);
   if(edge.source_consumed){
     const auto stream=ws_streams_.at(source_owner);auto c=stream.command,paired=stream.paired;
     if(c->kind=="compute_ws")ws_pending_completed_.push_back({at+1,c});
     if(c->kind=="preload"&&std::uint32_t(c->rs2)==0xffffffffu)ws_pending_completed_.push_back({at+1,c});
     if(paired&&std::uint32_t(paired->rs2)==0xffffffffu)ws_pending_completed_.push_back({at+1,paired});
     if(ws_pending_completed_.size()>2){fail("execute pending RS ids exceed actual two registers");return;}
     q_.post(at+1,{},[this,c,paired](auto&,auto t){
       once(c->consume);actor(ActorRole::execute_feed,c->consume.id,t,false);
       if(paired){once(paired->consume);auto&fifo=queues_[1];if(fifo.size()<2||fifo[0]!=c||fifo[1]!=paired){fail("paired finite operand FIFO identity");return;}fifo.pop_front();fifo.pop_front();refill(1,t);schedule_next(1,t);}
       else pop(c,t);
     },Q::Kind::operand_consume);
   }
   if(!ws_feed_->source_consumed()||!ws_feed_->empty()||ws_mesh_.busy()||ws_mesh_tags_.pending()||!ws_pending_completed_.empty())ws_kick(at+1);
   for(auto i=ws_pending_rows_.begin();i!=ws_pending_rows_.end();)if(q_.completed(i->second))i=ws_pending_rows_.erase(i);else ++i;
 }
 // Avoid hiding the command tag() helper behind the source tag iterator.
 static std::optional<merlin_timing::StageOrigin>tag_origin(const std::shared_ptr<Command>&c,const char*role){return tag(c,role);}
 void ws_begin(const std::shared_ptr<Command>&c,const std::shared_ptr<Command>&paired,Cycle at){
   using C=ExecuteOperandCounters;std::array<C::Operand,3>operands{};
   for(auto row:c->outputs)if(!acc(row)){fail("finite WS mesh output requires actual ACC row publication");return;}
   const auto operand=[](std::uint64_t packet,bool active){const bool garbage=std::uint32_t(packet)==0xffffffffu;return C::Operand{garbage?0u:std::uint32_t(packet),unsigned(std::min<std::uint64_t>(16,packet>>48)),garbage,active};};
   unsigned total;
   if(c->kind=="preload"){operands[2]=operand(c->rs1,true);total=operands[2].garbage?4:16;}
   else{operands[0]=operand(c->rs1,true);operands[1]=operand(c->rs2,true);operands[2]=paired?operand(paired->rs1,true):C::Operand{};
     total=paired&&!operands[2].garbage?16:std::max({operands[0].garbage?1u:operands[0].rows,operands[1].garbage?1u:operands[1].rows,4u});}
   C counters(operands,total,16,config_.scratchpad_bank_rows,4);
   if(!ws_feed_)ws_feed_=std::make_unique<ExecuteOperandPipeline>(std::move(counters),4);
   else ws_feed_->begin(std::move(counters),c->done.id);
   // The first stream starts with the component's owner0; all later source
   // ids are the original command's token, never a later CPU instruction.
   const auto owner=ws_feed_->source_owner();ws_streams_.emplace(owner,WsStream{c,paired});
   const auto tag_command=c->kind=="preload"?c:paired;if(tag_command&&std::uint32_t(tag_command->rs2)!=0xffffffffu){
     if(!(std::uint32_t(tag_command->rs2)&0x80000000u)){fail("finite WS preload C tag requires actual ACC storage");return;}
     ws_tag_commands_[tag_command->done.id]=tag_command;
   }
   if(c->kind=="preload")pe_ready_=c->consume;else if(paired)pe_ready_=paired->consume;
   actor(ActorRole::execute_feed,c->consume.id,at,true);ws_kick(at);
 }
 void preload(const std::shared_ptr<Command>&c,Cycle at){
   if(!c->occupancy || *c->occupancy!=h_.dim){fail("unsupported PRELOAD feed law");return;}
   if(ws_operand_pipeline_){ws_begin(c,{},at);return;}
   const auto total_rows=ws_garbage_preload_rows_&&std::uint32_t(c->rs1)==0xffffffffu?Cycle{4}:*c->occupancy;
   if(ws_garbage_preload_rows_&&std::uint32_t(c->rs1)==0xffffffffu){
     if(!c->sp_reads.empty()){fail("garbage PRELOAD has physical source rows");return;}
     s_.feature("target.posted.ws_garbage_preload_total_rows",total_rows);
   }
   Stage feed;feed.origin=tag(c,"feed");feed.earliest=at;feed.latency=total_rows+(ws_first_row_?0:1);feed.reads=c->sp_reads;feed.hold_reads_until_ready=true;
   feed.demands={{config_.controller_resources[1],1,*feed.latency}};bank(feed,feed.reads,total_rows);
   stage(std::move(feed),{},c->consume,[this,c](auto&r){
     // PRELOAD's data is consumed; its output tag remains until following
     // compute result. Keep that late token separate from the PE-ready token.
     q_.post(*r.ready,{},[this,c](auto&,auto t){pop(c,t);},Q::Kind::operand_consume);
   });
   pe_ready_=c->consume;tags_.push_back(c->done);
 }
 void compute(const std::shared_ptr<Command>&c,Cycle at){
   if(!pe_ready_ || !c->original.latency || !config_.late_accumulator_write_pipeline){fail("compute missing resident weights/source phase");return;}
   // Source ExecuteController requires ACTUAL valid command heads and no
   // live mesh-tag address hazard. This admitted WS subset has only SP inputs
   // and ACC outputs, so the tag-address hazard is structurally impossible.
   std::shared_ptr<Command> paired;
   auto &fifo=queues_[1];
   if(fifo.size()>=3 && fifo[1]->kind=="preload" && fifo[2]->kind=="compute_ws" && ready(fifo[1]->dependencies)){
     paired=fifo[1];
     for(auto d:paired->sp_reads)for(auto a:c->sp_reads)
       if((d-base_)/config_.scratchpad_bank_rows==(a-base_)/config_.scratchpad_bank_rows){
         if(!ws_operand_pipeline_){fail("MUL_PRE needs source same-bank operand arbitration");return;}
       }
     paired->started=true;s_.feature("target.posted.mul_pre",1);
   }
   if(ws_operand_pipeline_){ws_begin(c,paired,at);return;}
   const auto a_rows=std::min<std::uint64_t>(h_.dim,c->rs1>>48);
   const auto b_address=std::uint32_t(c->rs2);const auto b_rows=b_address==0xffffffffu?1:std::min<std::uint64_t>(h_.dim,c->rs2>>48);
   const bool paired_garbage=ws_garbage_preload_rows_&&paired&&std::uint32_t(paired->rs1)==0xffffffffu;
   const auto feed_rows=paired&&!paired_garbage?h_.dim:std::max<std::uint64_t>({a_rows,b_rows,4});
   const Cycle feed_cycles=feed_rows+(ws_first_row_?0:1);
   Stage feed;feed.origin=tag(c,"feed");feed.earliest=at;feed.latency=feed_cycles;feed.reads=c->sp_reads;if(paired)feed.reads.insert(feed.reads.end(),paired->sp_reads.begin(),paired->sp_reads.end());feed.hold_reads_until_ready=true;
   feed.demands={{config_.controller_resources[1],1,feed_cycles}};bank(feed,feed.reads,feed_rows);
   auto output_tags=tags_;tags_.clear();auto deps=std::vector<Token>{*pe_ready_};
   stage(std::move(feed),std::move(deps),c->consume,[this,c,output_tags,paired,feed_rows](auto&r){
     const auto duration=h_.dim+*config_.late_accumulator_write_pipeline;
     if(*c->original.latency<duration){fail("compute output source interval");return;}
     if(accumulator_ports_){
       auto rows=std::make_shared<std::vector<Token>>();
       auto offer=std::make_shared<std::function<void(std::size_t,Cycle)>>();std::weak_ptr<std::function<void(std::size_t,Cycle)>>weak=offer;
       // MeshWithDelays carries the actual total_rows through its tag FIFO.
       // Last response includes padded rows up to total_rows, not always DIM.
       const auto nominal_done=*r.start+*c->original.latency-(ws_total_rows_completion_?h_.dim-feed_rows:0);
       if(ws_total_rows_completion_)s_.feature("target.posted.ws_output_total_rows",feed_rows);
       *offer=[this,c,rows,weak,output_tags,nominal_done](std::size_t i,Cycle at){
         if(i==c->outputs.size()){
           q_.post(std::max(at,nominal_done),*rows,[this,c,output_tags](auto&,auto){once(c->done);c->finished=true;for(auto tag:output_tags)once(tag);},Q::Kind::command_retire);return;
         }
         Stage row;row.origin=tag(c,"acc_result_row");row.earliest=at;row.latency=*config_.late_accumulator_write_pipeline;
         row.writes={c->outputs[i]};if(contains(c->acc_reads,c->outputs[i]))row.reads=row.writes;
         row.hold_reads_until_ready=true;auto done=c->row_ready.at(c->outputs[i]);rows->push_back(done);
         auto next=weak.lock();if(!next){fail("ACC output stream lost owner");return;}
         stage(std::move(row),c->row_dependencies[c->outputs[i]],done,[this,next,i](const auto&result){q_.post(*result.start+1,{},[next,i](auto&,auto t){(*next)(i+1,t);},Q::Kind::source_arrival);});
       };
       // Mesh output is a registered row stream. Keep its selected first-row
       // availability and only replace the unsupported DIM+2 port hold.
       const auto first=*r.start+*c->original.latency-duration;
       q_.post(first,{},[offer](auto&,auto t){(*offer)(0,t);},Q::Kind::source_arrival);
     }else{
     Stage output;output.origin=tag(c,"acc_result");output.earliest=*r.start+*c->original.latency-duration;output.latency=duration;
     output.reads=c->acc_reads;output.writes=c->outputs;output.hold_reads_until_ready=true;
     auto access=output.reads;access.insert(access.end(),output.writes.begin(),output.writes.end());bank(output,access,duration);
     stage(std::move(output),c->output_dependencies,c->done,[this,c,output_tags](auto&out){
       q_.post(*out.ready,{},[this,c,output_tags](auto&,auto){c->finished=true;for(auto tag:output_tags)once(tag);},Q::Kind::command_retire);
     });
     }
     if(paired){pe_ready_=paired->consume;tags_.push_back(paired->done);}
     q_.post(*r.ready,{},[this,c,paired](auto&,auto t){
       if(paired){once(paired->consume);auto &fifo=queues_[1];if(fifo.size()<2||fifo[0]!=c||fifo[1]!=paired){fail("paired FIFO identity");return;}
         fifo.pop_front();fifo.pop_front();refill(1,t);schedule_next(1,t);
       }else pop(c,t);
     },Q::Kind::operand_consume);
   });
 }
 // Selected identity-scale path has REAL finite storage. A fragment
 // waits at the reader/merger output when Queue2 is full; no unbounded list of
 // future SP writes is mistaken for the ring3/pixel1 pipeline.
 struct Fragment{ValueId row;Token accepted,complete;std::function<void()>publish;std::optional<merlin_timing::StageOrigin> origin{};bool last_packet_output=false;
   std::vector<ValueId>repeat_rows{};std::function<void(ValueId)>publish_repeated{};bool i8_accumulator=false,accumulate=false;
   std::size_t next_identity_repeat=0,pending_identity_publications=0;};
 std::deque<std::shared_ptr<Fragment>> identity_q_,identity_ring_;
 std::shared_ptr<Fragment> identity_in_,identity_pixel_,identity_wait_;
 bool identity_tick_pending_=false,identity_acc_pending_=false;
 void identity_tick(Cycle at){
   identity_tick_pending_=false;
   const auto old_q=identity_q_.size(),old_ring=identity_ring_.size();
   if(identity_pixel_&&!identity_acc_pending_){
     Stage write;write.origin=identity_pixel_->origin;write.earliest=at;write.writes={identity_pixel_->row};const Cycle publication=identity_pixel_->i8_accumulator?2:1;write.latency=publication;
     if(identity_pixel_->accumulate){write.reads={identity_pixel_->row};write.hold_reads_until_ready=true;}
     bank(write,write.writes,1);
     if(accumulator_ports_&&identity_pixel_->i8_accumulator){
       auto fragment=identity_pixel_;identity_acc_pending_=true;
       stage(std::move(write),{},fragment->complete,[this,fragment](const auto&r){
         if(identity_pixel_!=fragment){fail("ACC identity pixel owner changed");return;}
         identity_pixel_.reset();identity_acc_pending_=false;
         if(fragment->last_packet_output)last_mvin_response_at_=*r.start;
         s_.feature("target.posted.identity_i8_accumulator_load_fragments",1);
         q_.post(*r.ready,{},[fragment](auto&,auto){fragment->publish();},Q::Kind::local_publish);
       });
     }else{
     auto event=write.event(at);
     const auto ready=s_.engine.earliest_stage_start(event);
     if(!ready){fail("identity SP write readiness unknown");return;}
     if(*ready>at){++coverage_.port_blocked;s_.feature("target.posted.modeled_identity_port_wait",1);}
     if(*ready==at){
       const auto result=s_.engine.submit_detached(event);
       if(result.start!=at||result.ready!=at+publication){fail("identity local publication changed at admission");return;}
       auto fragment=std::move(identity_pixel_);
       if(fragment->last_packet_output){last_mvin_response_at_=at;if(!fragment->i8_accumulator)last_sp_output_at_=at;}
       if(fragment->i8_accumulator)s_.feature("target.posted.identity_i8_accumulator_load_fragments",1);
       q_.post(at+publication,{},[this,fragment](auto&,auto){once(fragment->complete);fragment->publish();},Q::Kind::local_publish);
     }
   }
     }
   auto advance=[this,old_q,old_ring](auto&,auto at){
   if(!identity_pixel_&&!identity_ring_.empty()){
     identity_pixel_=identity_ring_.front();identity_ring_.pop_front();
   }
   // Completed-ring tail reads prior valid state: full does not recycle on
   // the same edge. The input register itself supports replacement on fire.
   if(identity_in_&&old_ring<3){
     if(identity_in_->repeat_rows.empty())identity_ring_.push_back(std::move(identity_in_));
     else{
       // VectorScalarMultiplier.in holds ONE original payload until repeats0.
       // Each in_fire creates one ring entry with the descending row tag;
       // full ring blocks it, and only its final emission frees the register.
       auto input=identity_in_;auto emitted=std::make_shared<Fragment>(*input);
       const auto row=input->repeat_rows.at(input->next_identity_repeat++);
       emitted->row=row;emitted->repeat_rows.clear();emitted->complete=token();
       emitted->last_packet_output=input->last_packet_output&&input->next_identity_repeat==input->repeat_rows.size();
       emitted->publish=[this,input,row]{
         input->publish_repeated(row);
         if(!--input->pending_identity_publications)once(input->complete);
       };
       identity_ring_.push_back(std::move(emitted));
       s_.feature("target.posted.input_scaler_repeated_row_emissions",1);
       if(input->next_identity_repeat==input->repeat_rows.size())identity_in_.reset();
     }
   }
   if(!identity_in_&&!identity_q_.empty()){identity_in_=identity_q_.front();identity_q_.pop_front();}
   // Default Queue2 is neither flow nor pipe. A previously FULL queue cannot
   // accept using its just-dequeued slot on that edge.
   if(identity_wait_&&old_q<2){auto fragment=std::move(identity_wait_);identity_q_.push_back(fragment);once(fragment->accepted);}
   coverage_.peak_q=std::max(coverage_.peak_q,identity_q_.size());coverage_.peak_ring=std::max(coverage_.peak_ring,identity_ring_.size());
   if(identity_wait_){++coverage_.merger_blocked;s_.feature("target.posted.modeled_merger_backpressure",1);}
   if(identity_wait_||!identity_q_.empty()||identity_in_||!identity_ring_.empty()||identity_pixel_)identity_kick(at+1);
   };
   if(accumulator_ports_)q_.post_settled(at,{},std::move(advance),Q::Kind::local_publish);else advance(q_,at);
 }
 void identity_kick(Cycle at){
   if(identity_tick_pending_)return;
   identity_tick_pending_=true;q_.post(now(at),{},[this](auto&,auto t){identity_tick(t);},Q::Kind::local_publish);
 }
 void identity_offer(std::shared_ptr<Fragment> fragment,Cycle at){
   q_.post(now(at),{},[this,fragment](auto&,auto t){
     if(identity_wait_){fail("more than one held BeatMerger output");return;}
     // Bypass a waiting slot only at this real acceptance edge; pipe stages
     // still see old state in the following cycle.
     if(identity_q_.size()<2){identity_q_.push_back(fragment);once(fragment->accepted);}
     else identity_wait_=fragment;
     identity_kick(t+1);
   },Q::Kind::response_beat);
 }
 // The separately instantiated full-ACC scaler has no scale arguments in
 // this selected source: Queue2 -> replaceable input register -> latency0
 // Pipeline. It does NOT traverse the input scaler ring or PixelRepeater.
 // The register remains occupied until the actual ACC write handshake.
 void full_acc_write(std::shared_ptr<Fragment> fragment,Token consumed,Cycle at,std::size_t repeat=0){
   const bool response_last=fragment->last_packet_output&&(fragment->repeat_rows.empty()||repeat+1==fragment->repeat_rows.size());
   if(response_last)full_acc_last_pending_.insert(fragment.get());
   // Scratchpad's spad_last suppresses the ACC DMA write on this edge even
   // though the SP output and ACC output use different local memories.
   if(last_sp_output_at_==std::optional<Cycle>{at} ||
      (identity_pixel_&&identity_pixel_->last_packet_output)){
     q_.post(at+1,{},[this,fragment,consumed,repeat](auto&,auto t){full_acc_write(fragment,consumed,t,repeat);},Q::Kind::local_publish);return;
   }
   const auto row=fragment->repeat_rows.empty()?fragment->row:fragment->repeat_rows.at(repeat);
   Stage write;write.origin=fragment->origin;write.earliest=at;write.writes={row};
   write.latency=2;bank(write,write.writes,1);
   if(accumulator_ports_){
     const bool last=fragment->repeat_rows.empty()||repeat+1==fragment->repeat_rows.size();auto complete=token();
     stage(std::move(write),{},complete,[this,fragment,consumed,repeat,row,last](const auto&r){
       if(last){once(consumed);if(fragment->last_packet_output){last_mvin_response_at_=*r.start;full_acc_last_pending_.erase(fragment.get());}}
       else q_.post(*r.start+1,{},[this,fragment,consumed,repeat](auto&,auto t){full_acc_write(fragment,consumed,t,repeat+1);},Q::Kind::local_publish);
       s_.feature("target.posted.full_accumulator_load_fragments",1);
       q_.post(*r.ready,{},[this,fragment,row,last](auto&,auto){
         if(fragment->repeat_rows.empty())fragment->publish();else fragment->publish_repeated(row);
         if(last)once(fragment->complete);
       },Q::Kind::local_publish);
     });return;
   }
   const auto event=write.event(at);
   const auto ready=s_.engine.earliest_stage_start(event);
   if(!ready){fail("full ACC overwrite port readiness unknown");return;}
   if(*ready>at){
     q_.post(*ready,{},[this,fragment,consumed,repeat](auto&,auto t){full_acc_write(fragment,consumed,t,repeat);},Q::Kind::local_publish);return;
   }
   const auto result=s_.engine.submit_detached(event);
   if(result.start!=at||result.ready!=at+2){fail("full ACC overwrite publication changed at admission");return;}
   const bool last=fragment->repeat_rows.empty() || repeat+1==fragment->repeat_rows.size();
   if(last){once(consumed);if(fragment->last_packet_output){last_mvin_response_at_=at;full_acc_last_pending_.erase(fragment.get());}} // register may replace only after repeats reaches0.
   else q_.post(at+1,{},[this,fragment,consumed,repeat](auto&,auto t){full_acc_write(fragment,consumed,t,repeat+1);},Q::Kind::local_publish);
   s_.feature("target.posted.full_accumulator_load_fragments",1);
   q_.post(at+2,{},[this,fragment,row,last](auto&,auto){
     if(fragment->repeat_rows.empty())fragment->publish();else fragment->publish_repeated(row);
     if(last)once(fragment->complete);
   },Q::Kind::local_publish);
 }
 void full_acc_offer(std::shared_ptr<Fragment>fragment,Cycle at){
   if(!full_acc_load_path_){fail("full ACC overwrite ingress source law absent");return;}
   auto entered=full_acc_load_path_->push([this,fragment](Cycle t,Token consumed){full_acc_write(fragment,consumed,t);},at);
   q_.post(at,{entered},[this,fragment](auto&,auto){once(fragment->accepted);},Q::Kind::response_beat);
 }
 struct Response{std::shared_ptr<Command>command;ReaderPacket packet;std::vector<Token>fragments;
   std::function<void(Cycle)>returned;std::function<void()>done;Cycle begin=0;std::size_t next=0;
   std::vector<Token>beats;std::optional<Token>merged;std::shared_ptr<ReaderLease>lease;};
 std::deque<std::shared_ptr<Response>> responses_;bool response_busy_=false;
 bool response_source_busy_=false;std::shared_ptr<Response>merging_response_;
 std::size_t reader_inflight_=0;Cycle reader_request_next_=0;
 std::deque<std::function<void(Cycle)>>reader_wait_;
 Token source_response_beat(const std::shared_ptr<Response>&response,std::size_t beat,Cycle at,bool source_driven=false){
   auto accepted=reader_response([this,response,beat](Cycle t,Token consumed){
     std::vector<Token>deps;
     if(merging_response_&&merging_response_!=response)deps.push_back(*merging_response_->merged);
     q_.post(t,std::move(deps),[this,response,beat,consumed](auto&,auto time){
       if(beat==0){
         if(merging_response_){fail("registered reader merger packet identity");return;}
         merging_response_=response;response->begin=time;response_fragment(response,time);
       }else if(merging_response_!=response){fail("registered reader beat ownership");return;}
       once(response->beats.at(beat));once(consumed);
       if(beat+1==response->beats.size()){
         if(!reader_inflight_){fail("reader transaction identity underflow");return;}
         --reader_inflight_;release_reader(response->lease);response->returned(time);
         if(!reader_wait_.empty()){auto continuation=std::move(reader_wait_.front());reader_wait_.pop_front();continuation(time);}
       }
     },Q::Kind::response_beat);
   },at);
   q_.post(at,{accepted},[this,response,beat,source_driven](auto&,auto t){
     if(source_driven)return;
     if(beat+1<response->beats.size())source_response_beat(response,beat+1,t+1);
     else{response_source_busy_=false;response_next(t+1);}
   },Q::Kind::response_beat);return accepted;
 }
 void response_next(Cycle at){
   if(reader_response_path_){
     if(response_source_busy_||responses_.empty())return;
     auto response=responses_.front();responses_.pop_front();response_source_busy_=true;
     response->merged=token();for(std::size_t b=0;b<response->packet.bytes/16;++b)response->beats.push_back(token());
     if(response->beats.empty()){fail("empty registered reader packet");return;}
     source_response_beat(response,0,now(at));return;
   }
   if(response_busy_||responses_.empty())return;
   response_busy_=true;auto response=responses_.front();responses_.pop_front();response->begin=now(at);
   // Shared native memory supplies only an aggregate completion bound. Ready
   // packets are drained FIFO here, explicitly PROVISIONAL rather than a
   // claimed source-closed MSHR/RR ordering. One actual Reader D beat port and
   // one BeatMerger are retained; stalled identity output blocks the merger.
   q_.post(response->begin+response->packet.bytes/16,{},[this,response](auto&,auto t){
     if(!reader_inflight_){fail("reader transaction identity underflow");return;}
     --reader_inflight_;response->returned(t);
     if(!reader_wait_.empty()){auto continuation=std::move(reader_wait_.front());reader_wait_.pop_front();continuation(t);}
   },Q::Kind::response_beat);
   response_fragment(response,response->begin);
 }
 void response_fragment(const std::shared_ptr<Response>&response,Cycle at){
   if(response->next==response->packet.outputs.size()){
     if(reader_response_path_){
       if(merging_response_!=response){fail("registered merger completion identity");return;}
       q_.post(at,{response->beats.back()},[this,response](auto&,auto){
         merging_response_.reset();once(*response->merged);auto done=std::move(response->done);done();
       },Q::Kind::response_beat);return;
     }
     response_busy_=false;auto done=std::move(response->done);done();response_next(std::max(at,response->begin+response->packet.bytes/16));return;
   }
   const auto fragment=response->packet.outputs[response->next++];auto c=response->command;
   if(fragment.destination>=c->phase->reader_destinations.size()){fail("packet destination mapping");return;}
   const auto row=c->phase->reader_destinations[fragment.destination];auto accepted=token(),complete=token();response->fragments.push_back(complete);
   auto item=std::make_shared<Fragment>(Fragment{row,accepted,complete,[this,c,row]{
     if(!--load_remaining_.at(c.get()).at(row))once(c->row_ready.at(row));
   },tag(c,(c->phase->full_accumulator_load||c->phase->identity_i8_accumulator_load)?"acc_load_write":"sp_write"),response->next==response->packet.outputs.size()});
   item->i8_accumulator=c->phase->identity_i8_accumulator_load;item->accumulate=item->i8_accumulator&&bool((c->rs2>>30)&1);
   if(c->phase->input_row_repeats){
     const auto count=c->phase->input_row_repeats+1;
     if(!c->phase->scratchpad_load || item->i8_accumulator || c->phase->full_accumulator_load ||
        count>16 || c->phase->reader_destinations.size()%count ||
        fragment.destination>=c->phase->reader_destinations.size()/count){fail("input repeated source row mapping");return;}
     item->repeat_rows.clear();
     for(std::size_t r=count;r>0;--r)item->repeat_rows.push_back(c->phase->reader_destinations[fragment.destination*count+r-1]);
     item->pending_identity_publications=count;
     item->publish_repeated=[this,c](ValueId target){if(!--load_remaining_.at(c.get()).at(target))once(c->row_ready.at(target));};
   }
   if(c->phase->full_accumulator_repeats){
     if(fragment.destination!=0 || c->phase->reader_destinations.size()!=c->phase->full_accumulator_repeats+1){fail("ACC repeated source row mapping");return;}
     for(std::size_t r=c->phase->reader_destinations.size();r>0;--r)item->repeat_rows.push_back(c->phase->reader_destinations[r-1]);
     item->publish_repeated=[this,c](ValueId target){if(!--load_remaining_.at(c.get()).at(target))once(c->row_ready.at(target));};
   }
   if(reader_response_path_){
     if(fragment.required_beat>=response->beats.size()){fail("registered reader required beat bounds");return;}
     const auto beat=response->beats[fragment.required_beat];
     q_.post(at,{beat},[this,item,beat,c](auto&,auto t){
       const auto visible=std::max(t,*q_.completed(beat)+1);
       if(c->phase->full_accumulator_load)full_acc_offer(item,visible);else identity_offer(item,visible);
     },Q::Kind::response_beat);
   }else if(c->phase->full_accumulator_load)full_acc_offer(item,std::max(at,response->begin+fragment.required_beat+1));
   else identity_offer(item,std::max(at,response->begin+fragment.required_beat+1));
   q_.post(at,{accepted},[this,response](auto&,auto t){
     // BeatMerger.scala: last_sending && bytesRead==request_size raises
     // req.ready on THIS io.out.fire edge. A following packet can supply its
     // first beat immediately. Only another output from this SAME packet
     // must wait one cycle; do not add a software continuation bubble.
     const bool last=response->next==response->packet.outputs.size();
     response_fragment(response,last?t:t+1);
   },Q::Kind::response_beat);
 }
 std::map<Command*,std::map<ValueId,std::size_t>>load_remaining_;
 // One original LoadController row request, followed by its original local
 // column fragments. ZeroWriter never allocates a memory transaction.
 void zero_load(const std::shared_ptr<Command>&c,Cycle at){
   if(!zero_writer_){fail("zero writer source law absent");return;}
   const auto geometry=*c->phase->zero_fill;const auto bands=(geometry.columns+15)/16;
   if(!geometry.rows||geometry.rows>16||!geometry.columns||geometry.columns>64||
      c->phase->reader_destinations.size()!=geometry.rows*bands){fail("zero writer local destination geometry");return;}
   std::vector<Token>published;
   for(auto row:c->phase->reader_destinations){if(!sp(row)){fail("zero writer non-SP destination");return;}published.push_back(c->row_ready.at(row));}
   q_.post(at,published,[this,c](auto&,auto end){once(c->consume);once(c->done);c->finished=true;--dma_active_[0];schedule_next(0,end);},Q::Kind::command_retire);
   auto issue=std::make_shared<std::function<void(std::size_t,Cycle)>>();
   *issue=[this,c,geometry,bands,issue](std::size_t index,Cycle time){
     std::vector<PostedZeroWriter::Row>rows;
     for(std::uint32_t band=0;band<bands;++band){
       const auto row=c->phase->reader_destinations.at(band*geometry.rows+index);
       const auto columns=std::min(16u,geometry.columns-band*16);
       rows.push_back({row,(std::uint64_t{1}<<columns)-1,[this,c,row,columns](Cycle t){
         s_.feature("target.posted.zero_local_writes",1);s_.feature("target.posted.zero_useful_bytes",columns);
         if(columns!=16)s_.feature("target.posted.zero_masked_local_writes",1);
         q_.post(t+1,{},[this,c,row](auto&,auto){once(c->row_ready.at(row));},Q::Kind::local_publish);
       },tag(c,"zero_write")});
     }
     zero_writer_->push(std::move(rows),[this,c,geometry,index,issue](Cycle t){
       s_.feature("target.posted.zero_row_requests",1);
       q_.post(t+1,{},[this,c,geometry,index,issue](auto&,auto next){
         if(index+1==geometry.rows){pop(c,next);*issue={};}else (*issue)(index+1,next);
       },Q::Kind::source_arrival);
     },time);
   };(*issue)(0,at);
 }
 void load(const std::shared_ptr<Command>&c,Cycle at){
   if(c->phase&&c->phase->zero_fill){zero_load(c,at);return;}
   if(!c->phase||(!c->phase->scratchpad_load&&!c->phase->full_accumulator_load&&!c->phase->identity_i8_accumulator_load)||c->phase->reader_packets.empty()){
     fail("posted LOAD requires source-bound local packet mapping");return;
   }
   if(c->phase->identity_i8_accumulator_load&&!identity_i8_accumulator_load_){fail("identity i8 ACC load law not selected");return;}
   if(c->phase->full_accumulator_load&&!full_acc_load_path_){fail("posted full ACC load law not selected");return;}
   struct State{std::size_t next=0,returned=0,merged=0;std::vector<Token>fragments;};
   auto state=std::make_shared<State>();
   for(const auto&p:c->phase->reader_packets)for(const auto&f:p.outputs){
     if(f.destination>=c->phase->reader_destinations.size()){fail("packet destination bounds");return;}
     if(c->phase->input_row_repeats){
       const auto count=c->phase->input_row_repeats+1;
       if(!c->phase->scratchpad_load || c->phase->full_accumulator_load || c->phase->identity_i8_accumulator_load ||
          count>16 || c->phase->reader_destinations.size()%count || f.destination>=c->phase->reader_destinations.size()/count){fail("input repeated packet destinations");return;}
       for(std::size_t r=0;r<count;++r)++load_remaining_[c.get()][c->phase->reader_destinations[f.destination*count+r]];
     }else if(c->phase->full_accumulator_repeats){
       if(f.destination!=0||c->phase->reader_destinations.size()!=c->phase->full_accumulator_repeats+1){fail("ACC repeated packet destinations");return;}
       for(auto row:c->phase->reader_destinations)++load_remaining_[c.get()][row];
     }else ++load_remaining_[c.get()][c->phase->reader_destinations[f.destination]];
   }
   auto issue=std::make_shared<std::function<void(Cycle)>>();
   *issue=[this,c,state,issue](Cycle time){
     const auto &packets=c->phase->reader_packets;
     if(state->next>=packets.size())return;
     if(reader_inflight_>=16){
       reader_wait_.push_back([issue](Cycle at){(*issue)(at);});return;
     }
     const auto packet=packets[state->next++];++reader_inflight_;coverage_.peak_reader=std::max(coverage_.peak_reader,reader_inflight_);
     const auto accepted=now(std::max(time,reader_request_next_)+2);reader_request_next_=accepted-1;
     auto lease=std::make_shared<ReaderLease>();
     auto admit=[this,c,state,packet,lease](Cycle accepted){
       std::function<void(Cycle)> deliver=[this,c,state,packet,lease](Cycle t){
         auto response=std::make_shared<Response>();response->command=c;response->packet=packet;response->lease=lease;
         response->returned=[state](Cycle){++state->returned;};
         response->done=[this,c,state,response]{
           state->fragments.insert(state->fragments.end(),response->fragments.begin(),response->fragments.end());
           if(++state->merged==c->phase->reader_packets.size())q_.post(q_.now(),state->fragments,[this,c](auto&,auto end){
             once(c->consume);once(c->done);c->finished=true;--dma_active_[0];load_remaining_.erase(c.get());schedule_next(0,end);
           },Q::Kind::command_retire);
         };responses_.push_back(response);response_next(t);
       };
       auto classify=[this,c,state,packet,lease,deliver=std::move(deliver)](Cycle accepted,std::optional<Token>preallocated)mutable{
       const auto effects=s_.memory({{packet.address,packet.bytes,false}});
       if(preallocated)s_.feature("target.posted.read_lookup_after_mshr_admission",1);
       if(read_allocation_service_v7_){spike_timing::ReadAllocationEffectsV7 allocation;
         if(read_allocation_service_v7_->take(read_allocation_service_v7_->opaque,&allocation)){
           PostedReadAllocationResponse::Sink sink;
           if(read_input_retirement_){
             std::uint64_t next=packet.address;
             for(const auto&a:allocation.allocations){if(a.inner_address!=next){fail("source D stream lost actual packet address order");return;}next+=a.inner_bytes;}
             if(next!=packet.address+packet.bytes){fail("source D stream bytes differ from original packet");return;}
             auto response=std::make_shared<Response>();response->command=c;response->packet=packet;response->lease=lease;
             response->merged=token();for(std::size_t b=0;b<packet.bytes/16;++b)response->beats.push_back(token());
             response->returned=[state](Cycle){++state->returned;};
             response->done=[this,c,state,response]{
               state->fragments.insert(state->fragments.end(),response->fragments.begin(),response->fragments.end());
               if(++state->merged==c->phase->reader_packets.size())q_.post(q_.now(),state->fragments,[this,c](auto&,auto end){
                 once(c->consume);once(c->done);c->finished=true;--dma_active_[0];load_remaining_.erase(c.get());schedule_next(0,end);
               },Q::Kind::command_retire);
             };
             sink=[this,response](std::size_t beat,Cycle t,Token accepted){
               if(beat>=response->beats.size()){fail("source D stream original beat bounds");return;}
               const auto entered=source_response_beat(response,beat,t,true);
               q_.post(t,{entered},[this,accepted](auto&q,auto){q.complete(accepted);s_.feature("target.posted.source_d_device_stream_beats",1);},Q::Kind::response_beat);
             };
             // Original row publication/merger completion remains the LOAD
             // consumer. SourceD does not replay the whole packet afterward.
             deliver=[](Cycle){};
           }
           auto callback=new std::function<void(Cycle)>(std::move(deliver));
           const auto origin=tag(c,"memory_get");if(!origin){delete callback;fail("read allocation lacks original actor origin");return;}
           if(!submit_read_allocations(allocation,*origin,accepted,callback,[](void*opaque,Cycle at){
             std::unique_ptr<std::function<void(Cycle)>>done(static_cast<std::function<void(Cycle)>*>(opaque));(*done)(at);
           },std::move(sink),preallocated))delete callback;
           return;
         }
       }
       // The existing native private-probe path may return one indivisible
       // aggregate effect rather than V7. Keep that original request and its
       // observed response stream. Its preallocated MSHR is conservatively
       // held through the last actually accepted client D beat below.
       if(preallocated)s_.feature("target.posted.deferred_read_aggregate_probe_bound",1);
       if(reader_request_path_&&!memory_owned_reader_pipeline_&&(!resident_lookup(packet,*lease,accepted)||effects.latency!=std::optional<Cycle>{1})){
         fail("registered reader aggregate cache composition is unsupported for this lookup");return;
       }
       if(!effects.latency){fail("native memory packet has unknown completion");return;}
       Stage memory;memory.origin=tag(c,"memory_get");memory.earliest=accepted;memory.latency=effects.latency;memory.reads=effects.reads;memory.writes=effects.writes;
       if(s_.number("diagnostics.posted_source_timeline.pending_memory_visibility")==std::optional<double>{1})memory.deferred_writes=effects.writes;
       memory.demands=effects.demands;memory.hold_reads_until_ready=true;memory.kind=Q::Kind::memory_accept;
       auto memory_done=token();
       stage(std::move(memory),{},memory_done,[this,c,state,packet,lease,preallocated](auto&r){
         q_.post(*r.ready+inclusive_pipeline_extension_,{},[this,c,state,packet,lease,preallocated](auto&,auto t){
           auto response=std::make_shared<Response>();response->command=c;response->packet=packet;response->lease=lease;
           response->returned=[this,state,preallocated](Cycle){++state->returned;if(preallocated)once(*preallocated);};
           response->done=[this,c,state,response]{
             state->fragments.insert(state->fragments.end(),response->fragments.begin(),response->fragments.end());
             if(++state->merged==c->phase->reader_packets.size()){
               q_.post(q_.now(),state->fragments,[this,c](auto&,auto end){
                 once(c->consume);once(c->done);c->finished=true;--dma_active_[0];load_remaining_.erase(c.get());schedule_next(0,end);
               },Q::Kind::command_retire);
             }
           };
           responses_.push_back(response);response_next(t);
         },Q::Kind::response_beat);
       });
       };
       if(deferred_read_lookup_){
         // Scheduler only reads the Directory when the original request
         // obtains its MSHR/set owner (or is reloaded from a secondary). Do
         // not mutate native tags/replacement while this request is waiting
         // for that finite owner. Original ReaderPacket never crosses a line.
         if(!cold_write_||!read_allocation_service_v7_||!packet.bytes||packet.bytes>64||
            packet.address/64!=(packet.address+packet.bytes-1)/64){fail("deferred read requires original one-line packet and finite source owner");return;}
         auto retired=token();typed_write_admit(packet.address,retired,[classify=std::move(classify),retired](Cycle at)mutable{classify(at,retired);},accepted,"device_read");
       }else classify(accepted,{});
     };
     if(reader_request_path_){
       auto entered=reader_request([this,admit=std::move(admit)](Cycle t,Token consumed){admit(t);once(consumed);},accepted);
       const bool last=state->next==packets.size();
       q_.post(accepted,{entered},[this,c,issue,last,lease](auto&,auto t){
         allocate_reader(lease);
         if(last)q_.post(t+1,{},[this,c,issue](auto&,auto end){pop(c,end);*issue={};},Q::Kind::command_retire);
         else (*issue)(t-1);
       },Q::Kind::memory_accept);
     }else{
       q_.post(accepted,{},[issue,admit=std::move(admit)](auto&,auto t){admit(t);(*issue)(t-1);},Q::Kind::memory_accept);
       // Original path preserved. The registered route consumes DMA metadata
       // only after the last real packet-reservation enqueue accepts.
       if(state->next==packets.size())q_.post(accepted+1,{},[this,c,issue](auto&,auto t){pop(c,t);*issue={};},Q::Kind::command_retire);
     }
   };
   (*issue)(at);
 }
 // The memory owner classifies useful bytes once. Its cache-slot/DRAM writes
 // remain pending until S4 publication, independently of the D-ACK token.
 // Do not give PostedEngineStage a premature write-completion token here.
 struct SourceRequestOwner{Token admitted;std::vector<Token>dependencies;};
 void masked_request_bound(Stage request,const std::vector<ValueId>&writes,Token request_ready,const SourceRequestOwner&owner){
   request.reads.insert(request.reads.end(),writes.begin(),writes.end());request.writes.clear();
   auto work=std::make_shared<Stage>(std::move(request));
   auto dispatch=std::make_shared<std::function<void(Cycle)>>();
   *dispatch=[this,work,admitted=owner.admitted,request_ready,dispatch](Cycle at){
     const auto event=work->event(at);auto start=s_.engine.earliest_stage_start(event);
     if(!start){fail("typed write source request dependency unknown");return;}
     if(*start>at){q_.post(*start,{},[dispatch](auto&,auto t){(*dispatch)(t);},Q::Kind::memory_accept);return;}
     const auto result=s_.engine.submit_detached(event);
     if(result.start!=std::optional<Cycle>{at}||!result.ready){fail("typed write source admission changed");return;}
     once(admitted);q_.post(*result.ready,{},[request_ready](auto&q,auto){q.complete(request_ready);},Q::Kind::memory_accept);*dispatch={};
   };
   q_.post(work->earliest,owner.dependencies,[dispatch](auto&,auto t){(*dispatch)(t);},Q::Kind::memory_accept);
 }
 void masked_request(Stage request,std::vector<ValueId>writes,Token request_ready,Token published){
   SourceRequestOwner owner{token(),{}};auto ownership=request.event(request.earliest);
   ownership.writes={writes.data(),writes.size()};
   if(!q_.bind_deferred_values(ownership,{writes.data(),writes.size()},owner.admitted,published,owner.dependencies))return;
   masked_request_bound(std::move(request),writes,request_ready,owner);
 }
 std::vector<Demand>cache_bank_demands(std::uint64_t address,std::uint64_t mask)const{
   std::vector<Demand>out;if(cache_banks_.empty())return out;
   const auto first=(address%64)/16*2;
   for(unsigned chunk=0;chunk<2;++chunk)if(mask&(0xffull<<(chunk*8)))out.push_back({cache_banks_.at(first+chunk),1,Cycle{1}});
   return out;
 }
 std::uint64_t cache_bank_mask(std::uint64_t address,std::uint64_t mask)const{
   std::uint64_t banks=0;const auto first=(address%64)/16*2;
   for(unsigned chunk=0;chunk<2;++chunk)if(mask&(0xffull<<(chunk*8)))banks|=1ull<<(first+chunk);
   return banks;
 }
 void cold_cache_port(std::uint64_t address,PostedColdWrite::Port port,Cycle at,Token accepted,bool granted=false,bool war_checked=false,std::optional<merlin_timing::StageOrigin>origin={}){
   if(port==PostedColdWrite::Port::sinkd_data&&cold_write_&&!war_checked){
     const auto reads=cold_write_->write_dependencies(address,0xff);
     if(!reads.empty()){q_.post(at,reads,[this,address,port,accepted,origin](auto&,auto t){
       cold_cache_port(address,port,t,accepted,false,true,origin);
     },Q::Kind::local_publish);return;}
   }
   if(!granted){
     cache_ports_->offer(port==PostedColdWrite::Port::sourcec_read?PostedBankedStore::Port::source_c:PostedBankedStore::Port::sink_d,
       1ull<<((address%64)/8),[this,address,port,accepted,origin](Cycle t){cold_cache_port(address,port,t,accepted,true,true,origin);},at);return;
   }
   Stage work;work.origin=origin;if(work.origin)work.origin->actor+=port==PostedColdWrite::Port::sourcec_read?".sourcec_sram":".sinkd_sram";work.earliest=at;work.latency=0;
   work.demands={{cache_banks_.at((address%64)/8),1,Cycle{1}}};
   const auto event=work.event(at);const auto start=s_.engine.earliest_stage_start(event);
   if(!start){fail("cold SinkD bank port unknown");return;}
   if(*start>at){fail("selected SRAM arbitration intersects an unowned reservation");return;}
   const auto result=s_.engine.submit_detached(event);
   if(result.start!=std::optional<Cycle>{at}||result.ready!=std::optional<Cycle>{at}){fail("cold SinkD port admission changed");return;}
   once(accepted);s_.feature(port==PostedColdWrite::Port::sourcec_read?"target.posted.cold_sourcec_read":
       port==PostedColdWrite::Port::sinkd_noop?"target.posted.cold_sinkd_noop":"target.posted.cold_sinkd_data",1);
 }
 void cold_outer_bus(Cycle at,Token accepted,std::optional<merlin_timing::StageOrigin>origin={}){
   Stage beat;beat.origin=origin;if(beat.origin)beat.origin->actor+=".outer_data_beat";beat.earliest=at;beat.latency=0;beat.demands={{s_.resource("memory.shared"),1,Cycle{1}}};
   const auto event=beat.event(at);const auto start=s_.engine.earliest_stage_start(event);
   if(!start){fail("cold outer beat service unknown");return;}
   if(*start>at){q_.post(*start,{},[this,accepted,origin](auto&,auto t){cold_outer_bus(t,accepted,origin);},Q::Kind::memory_accept);return;}
   const auto result=s_.engine.submit_detached(event);
   if(result.start!=std::optional<Cycle>{at}){fail("cold outer beat admission changed");return;}once(accepted);
 }
 void cold_lower(Cycle latency,Cycle bus,Cycle at,Token returned,std::optional<merlin_timing::StageOrigin>origin={}){
   if(latency<bus||bus>8){fail("cold lower service exceeds selected eight-beat source floor");return;}
   Stage lower;lower.origin=origin;if(lower.origin)lower.origin->actor+=".outer_startup_bound";lower.earliest=at;lower.latency=latency-bus;
   // The actual eight accepted 64-bit SinkD beats own memory.shared instead
   // of also charging the old <=8-cycle aggregate byte-service component.
   // Startup remains the original selected uncertain memory service; this
   // does not claim a source-closed DRAM scheduler or deploy-FPGA model.
   stage(std::move(lower),{},returned);
 }
 struct WritebackOwner{std::optional<merlin_timing::StageOrigin>origin;std::vector<ValueId>values;std::vector<Token>dependencies;Token admitted,published;};
 void writeback_start(const std::shared_ptr<WritebackOwner>&owner,Cycle latency,Cycle bus,Cycle at,Token returned){
   if(latency<bus||bus>8){fail("dirty lower service exceeds selected eight-beat source floor");return;}
   auto dispatch=std::make_shared<std::function<void(Cycle)>>();
   *dispatch=[this,owner,latency,bus,returned,dispatch](Cycle t){
     Stage ownership;ownership.origin=owner->origin;ownership.earliest=t;ownership.writes=owner->values;ownership.latency=0;
     const auto allowed=s_.engine.earliest_stage_start(ownership.event(t));
     if(!allowed){fail("dirty writeback prior memory ownership unknown");return;}
     if(*allowed>t){q_.post(*allowed,{},[dispatch](auto&,auto now){(*dispatch)(now);},Q::Kind::memory_accept);return;}
     // The pending writer belongs to ReleaseAck, not this startup bound.
     Stage service;service.origin=owner->origin;if(service.origin)service.origin->actor+=".dirty_writeback_startup_bound";service.earliest=t;service.reads=owner->values;service.hold_reads_until_ready=true;service.latency=latency-bus;
     const auto result=s_.engine.submit_detached(service.event(t));
     if(result.start!=std::optional<Cycle>{t}||!result.ready){fail("dirty writeback memory admission changed");return;}
     once(owner->admitted);q_.post(*result.ready,{},[returned](auto&q,auto){q.complete(returned);},Q::Kind::response_beat);*dispatch={};
   };
   q_.post(at,owner->dependencies,[dispatch](auto&,auto t){(*dispatch)(t);},Q::Kind::memory_accept);
 }
 void writeback_publication(const std::shared_ptr<WritebackOwner>&owner,Cycle at){
   Stage publication;publication.origin=owner->origin;if(publication.origin)publication.origin->actor+=".dirty_writeback_publication";publication.earliest=at;publication.writes=owner->values;publication.latency=0;
   const auto result=s_.engine.submit_detached(publication.event(at));
   if(result.start!=std::optional<Cycle>{at}||result.ready!=std::optional<Cycle>{at}){fail("dirty writeback ReleaseAck precedes prior memory owner");return;}
   once(owner->published);s_.feature("target.posted.dirty_writeback_publications",1);
 }
 void victim_bank_write(std::uint64_t address,Cycle at,Token stored,bool granted=false){
   if(!granted){cache_ports_->offer(PostedBankedStore::Port::sink_c,cache_bank_mask(address,0xffff),
     [this,address,stored](Cycle t){victim_bank_write(address,t,stored,true);},at);return;}
   const auto origin=victim_origins_.find(address/64);if(origin==victim_origins_.end()){fail("victim SRAM write lost original command");return;}
   Stage write;write.origin=origin->second;write.earliest=at;write.latency=0;write.demands=cache_bank_demands(address,0xffff);
   const auto result=s_.engine.submit_detached(write.event(at));
   if(result.start!=std::optional<Cycle>{at}||result.ready!=std::optional<Cycle>{at}){fail("victim SinkC intersects unowned SRAM reservation");return;}
   once(stored);s_.feature("target.posted.victim_sinkc_publications",1);
 }
 static std::optional<spike_timing::WriteMissV5>legacy_cold_miss(const std::optional<spike_timing::WriteMissV4>&miss){
   if(!miss)return {};
   spike_timing::WriteMissV5 extended;static_cast<spike_timing::WriteMissV4&>(extended)=*miss;return extended;
 }
 void typed_request(Stage request,std::vector<ValueId>writes,Token ready,Token published,
                    std::optional<spike_timing::WriteMissV5>miss,std::uint64_t address,std::optional<spike_timing::VictimProbeV6>victim={},bool read_owner=false,bool resident_read=false,std::optional<SourceRequestOwner>prebound={},std::shared_ptr<FillWindow>fill={}){
   const auto earliest=request.earliest;
   if(miss&&(!cold_write_||miss->set!=(address/64)%cold_cache_sets_)){fail("cold write native/source set identity mismatch");return;}
   std::shared_ptr<WritebackOwner>writeback;
   if(miss&&miss->dirty_eviction){
     if(miss->release_writes.empty()){fail("dirty victim lacks actual old-DRAM writer IDs");return;}
     for(auto value:miss->release_writes)if(std::find(writes.begin(),writes.end(),value)!=writes.end()){fail("dirty and new output publication owners alias");return;}
     writeback=std::make_shared<WritebackOwner>(WritebackOwner{request.origin,miss->release_writes,{},token(),token()});
     Stage ownership;ownership.earliest=earliest;ownership.writes=writeback->values;ownership.latency=0;
     if(!q_.bind_deferred_values(ownership.event(earliest),{writeback->values.data(),writeback->values.size()},writeback->admitted,writeback->published,writeback->dependencies))return;
   }
   const auto origin=request.origin;
   auto admit=[this,request=std::move(request),writes=std::move(writes),ready,published,miss,writeback,victim,origin,read_owner,resident_read,prebound,fill](Cycle at)mutable{
     request.earliest=at;auto local=miss?token():ready;
     if(prebound)masked_request_bound(std::move(request),writes,local,*prebound);
     else masked_request(std::move(request),std::move(writes),local,published);
     if(miss)q_.post(at,{local},[this,miss,ready,writeback,victim,origin,read_owner,resident_read,fill](auto&,auto t){
       if(resident_read){once(ready);return;}
       auto services=std::make_shared<PostedColdWrite::OwnedServices>();
       services->port=[this,origin](auto address,auto port,auto at,auto accepted){cold_cache_port(address,port,at,accepted,false,false,origin);};
       services->lower=[this,origin](auto latency,auto bus,auto at,auto returned){cold_lower(latency,bus,at,returned,origin);};
       services->bus=[this,origin](auto at,auto accepted){cold_outer_bus(at,accepted,origin);};
       PostedColdWrite::Ready completed;PostedColdWrite::Lower lower;
       if(writeback){completed=[this,writeback](Cycle at){writeback_publication(writeback,at);};
         lower=[this,writeback](Cycle latency,Cycle bus,Cycle at,Token returned){writeback_start(writeback,latency,bus,at,returned);};}
       std::optional<PostedColdWrite::Fill>progress;
       if(fill)progress=PostedColdWrite::Fill{fill->first_allowed,[this,fill](std::size_t beat,Cycle at){
         if(beat>=fill->chunks.size()){fail("outer fill beat lost original owner");return;}
         // SinkD publication and SourceD's SRAM read cannot consume the same
         // bank on one edge. The original registered bank exclusion is real.
         q_.post(at+1,{},[fill,beat](auto&q,auto){q.complete(fill->chunks.at(beat));},Q::Kind::local_publish);
       }};
       if(!victim){cold_write_->push(*miss,[this,ready](Cycle){once(ready);},std::move(completed),std::move(lower),t,{},{},std::move(progress),services);return;}
       if(!victim_probe_||(!read_owner&&!cold_write_service_v6_)||(read_owner&&!read_allocation_service_v7_)||!origin){fail("victim probe actor/source origin absent");return;}
       if(!victim_origins_.emplace(victim->line,*origin).second){fail("victim line already owns a source actor");return;}
       const auto sets=s_.number("memory.caches.l2.sets"),ways=s_.number("memory.caches.l2.ways");
       if(!sets||!ways){fail("victim cache geometry unavailable");return;}
       PostedVictimProbe::Request r;
       r.victim={victim->line,victim->set,victim->way,victim->generation};r.target_line=miss->line;
       r.target_private_hit=false;r.llc_dirty=victim->llc_dirty;r.private_dirty=victim->private_dirty;
       r.law={victim->source_identity,std::size_t(*sets),std::size_t(*ways),64,16,8,2,1,2,1};
       // Native V6 admission checks source topology, atomic/LRSC absence and
       // previous accepted CPU-data completion/post-grant guard. During this
       // actor the observer drives client_released before any later private
       // memory lookup. These booleans convey that explicit API contract.
       r.guards={victim->client_ready,true,true,true,true,true};
       const auto result=victim_probe_->push(r,t);if(!result)return;
       // A SinkC write accepted on an SRAM edge cannot be read from that
       // same bank by SourceC on the already-settled edge. Keep publication
       // at its true acceptance time and expose a separate next-edge read
       // eligibility token (BankedStore's registered bankSum exclusion).
       std::vector<Token>readable;
       for(auto publication:result->beat_publication){auto next=token();readable.push_back(next);
         q_.post(t,{publication},[next](auto&q,auto now){q.post(now+1,{},[next](auto&q,auto){q.complete(next);},Q::Kind::local_publish);},Q::Kind::local_publish);
       }
       std::vector<std::vector<Token>>reads;for(unsigned b=0;b<8;++b){
         reads.push_back({result->first_response});if(!readable.empty())reads.back().push_back(readable.at(b/2));
       }
       q_.post(t,{result->client_released},[this,victim,read_owner](auto&,auto now){
         const bool released=read_owner?read_allocation_service_v7_->client_released(read_allocation_service_v7_->opaque,&*victim,now):cold_write_service_v6_->client_released(cold_write_service_v6_->opaque,&*victim,now);
         if(!released)fail("native private controller release identity changed");
       },Q::Kind::command_retire);
       auto all=result->beat_publication;all.push_back(result->client_released);all.push_back(result->last_response);
       q_.post(t,std::move(all),[this,victim](auto&,auto){victim_origins_.erase(victim->line);},Q::Kind::completion);
       q_.post(t,{result->first_response},[this,miss,ready,completed=std::move(completed),lower=std::move(lower),reads=std::move(reads),last=result->last_response,progress=std::move(progress),services](auto&,auto now)mutable{
         cold_write_->push(*miss,[this,ready](Cycle){once(ready);},std::move(completed),std::move(lower),now,std::move(reads),last,std::move(progress),services);
       },Q::Kind::memory_accept);
     },Q::Kind::memory_accept);
   };
   admit(earliest);
 }
 void source_d_admit(Cycle at,std::function<void(Cycle,Token)>accepted,std::optional<Token>read_response={}){
   auto released=token();std::vector<Token>deps;
   if(masked_packets_||s_.number("memory.source_read_allocations.enabled")==std::optional<double>{1}){
     if(source_d_free_)deps.push_back(*source_d_free_);
     if(read_input_retirement_&&!source_d_pipeline_){
       // Only a homogeneous read stream uses the finite S2/S3 overlap law.
       // Stores retain the existing conservative S4 route, so transitions
       // wait the last read response rather than invent separate D ports.
       if(read_response)source_d_last_read_response_=read_response;
       else if(source_d_last_read_response_)deps.push_back(*source_d_last_read_response_);
     }
     auto reusable=token();source_d_free_=reusable;
     q_.post(at,{released},[reusable](auto&q,auto t){q.post(t+1,{},[reusable](auto&q,auto){q.complete(reusable);},Q::Kind::command_retire);},Q::Kind::command_retire);
   }
   q_.post(at,std::move(deps),[accepted=std::move(accepted),released](auto&,auto t){accepted(t,released);},Q::Kind::memory_accept);
 }
 void allocation_read_port(const merlin_timing::StageOrigin&origin,std::uint64_t address,Cycle at,Token accepted,Token ready,bool granted=false){
   if(!granted){cache_ports_->offer(PostedBankedStore::Port::source_d_read,cache_bank_mask(address,0xffff),
     [this,origin,address,accepted,ready](Cycle t){allocation_read_port(origin,address,t,accepted,ready,true);},at);return;}
   Stage work;work.origin=origin;work.earliest=at;work.latency=2;work.demands=cache_bank_demands(address,0xffff);
   const auto result=s_.engine.submit_detached(work.event(at));
   if(result.start!=std::optional<Cycle>{at}||result.ready!=std::optional<Cycle>{at+2}){fail("allocation SourceD read intersects unknown SRAM owner");return;}
   once(accepted);q_.post(at+2,{},[ready](auto&q,auto){q.complete(ready);},Q::Kind::response_beat);
   s_.feature("target.posted.allocation_source_d_reads",1);
 }
 void typed_write_admit(std::uint64_t address,Token published,PostedColdWrite::Ready accepted,Cycle at,const char*kind="original_read"){
   if(cold_write_){
     const auto set=(address/64)%cold_cache_sets_;const auto initial=cold_write_->admission_status(set);
     cold_write_->admit(set,published,[this,accepted=std::move(accepted),at,initial,label=std::string(kind)](Cycle t){
       // Actual callback edges and original queue state. Initial blocking
       // conditions are observations, not a claim that every wait cycle was
       // caused solely by that condition or by a physical hardware stall.
       const auto key="target.posted.mshr_admission."+label;
       s_.feature(key+".requests",1);s_.feature(key+".wait_cycles",t-at);
       if(initial.owns_set){s_.feature(key+".initial_same_set_requests",1);s_.feature(key+".initial_same_set_wait_cycles",t-at);}
       if(initial.live==10){s_.feature(key+".initial_full_requests",1);s_.feature(key+".initial_full_wait_cycles",t-at);}
       accepted(t);
     },at);
   }else accepted(at);
 }
 void cache_rmw_read(std::uint64_t address,Token accepted,Token ready,const std::shared_ptr<Command>&c,Cycle at,bool granted=false){
   if(cache_ports_&&!granted){cache_ports_->offer(PostedBankedStore::Port::source_d_read,cache_bank_mask(address,0xffff),
     [this,address,accepted,ready,c](Cycle t){cache_rmw_read(address,accepted,ready,c,t,true);},at);return;}
   Stage work;work.origin=tag(c,"masked_source_d_read");work.earliest=at;work.latency=2;work.demands=cache_bank_demands(address,0xffff);
   const auto event=work.event(at);const auto start=s_.engine.earliest_stage_start(event);
   if(!start){fail("SourceD SRAM read resource unknown");return;}
   if(*start>at){if(cache_ports_){fail("selected SourceD read intersects unowned SRAM reservation");return;}
     q_.post(*start,{},[this,address,accepted,ready,c](auto&,auto t){cache_rmw_read(address,accepted,ready,c,t);},Q::Kind::operand_consume);return;}
   const auto result=s_.engine.submit_detached(event);
   if(result.start!=std::optional<Cycle>{at}||result.ready!=std::optional<Cycle>{at+2}){fail("SourceD SRAM read admission changed");return;}
   once(accepted);q_.post(at+2,{},[ready](auto&q,auto){q.complete(ready);},Q::Kind::response_beat);
 }
 void sinkc_bank_write(const std::shared_ptr<Command>&c,std::uint64_t address,Cycle at,bool granted=false){
   if(cache_ports_&&!granted){cache_ports_->offer(PostedBankedStore::Port::sink_c,cache_bank_mask(address,0xffff),
     [this,c,address](Cycle t){sinkc_bank_write(c,address,t,true);},at);return;}
   Stage write;write.origin=tag(c,"sinkc_registered_bank_write");write.earliest=at;write.latency=0;
   write.demands=cache_bank_demands(address,0xffff);const auto result=s_.engine.submit_detached(write.event(at));
   if(result.start!=std::optional<Cycle>{at})fail("selected SinkC bank write intersects unowned SRAM reservation");
   else s_.feature("target.posted.masked_sinkc_beats",1);
 }
 void masked_probe(const std::shared_ptr<Command>&c,const spike_timing::WriteProbeV2&probe,std::uint64_t address,Token ready,Cycle at){
   const auto beats=probe.dirty?probe.line_bytes/probe.beat_bytes:1;
   const auto first=probe.lookup+(probe.dirty?probe.dirty_enter+probe.data_pipeline:0);
   const auto selected=address%probe.line_bytes==0?first:first+beats-1;
   Stage work;work.origin=tag(c,"masked_private_probe");work.earliest=at;work.latency=selected+1;
   work.demands={{probe.resource,1,probe.lookup+(probe.dirty?probe.dirty_enter+probe.data_pipeline+beats:1)+probe.metadata}};
   work.kind=Q::Kind::memory_accept;
   stage(std::move(work),{},ready,[this,c,probe,first,beats,address](const auto&r){
     if(!probe.dirty)return;
     for(Cycle beat=0;beat<beats;++beat)q_.post(*r.start+first+beat,{},[this,c,address,beat](auto&,auto accepted){
       // Actual C acceptance owns the payload in SinkC's registered Queue1.
       // BankedStore gives that next-edge write priority over SourceD reads.
       sinkc_bank_write(c,address/64*64+beat*16,accepted+1);
     },Q::Kind::response_beat);
   });
 }
 void masked_publication(const std::shared_ptr<Command>&c,std::vector<ValueId>writes,Token published,Token stored,Cycle at,
                         std::uint64_t address=0,std::uint64_t mask=0,bool granted=false,bool war_checked=false){
   if(cold_write_&&mask&&!war_checked){const auto reads=cold_write_->write_dependencies(address,mask);
     if(!reads.empty()){q_.post(at,reads,[this,c,writes=std::move(writes),published,stored,address,mask](auto&,auto t)mutable{
       masked_publication(c,std::move(writes),published,stored,t,address,mask,false,true);
     },Q::Kind::local_publish);return;}
   }
   if(cache_ports_&&mask&&!granted){cache_ports_->offer(PostedBankedStore::Port::source_d_write,cache_bank_mask(address,mask),
     [this,c,writes=std::move(writes),published,stored,address,mask](Cycle t)mutable{masked_publication(c,std::move(writes),published,stored,t,address,mask,true,true);},at);return;}
   Stage work;work.origin=tag(c,"masked_write_publication");work.earliest=at;work.writes=writes;work.latency=0;
   work.demands=cache_bank_demands(address,mask);
   const auto event=work.event(at);const auto start=s_.engine.earliest_stage_start(event);
   if(!start){fail("typed write storage publication dependency unknown");return;}
   if(*start>at){if(cache_ports_&&mask){fail("selected SourceD write intersects unowned SRAM reservation");return;}
     q_.post(*start,{},[this,c,writes=std::move(writes),published,stored,address,mask](auto&,auto t)mutable{
     masked_publication(c,std::move(writes),published,stored,t,address,mask);},Q::Kind::local_publish);return;}
   const auto result=s_.engine.submit_detached(event);
   if(result.start!=std::optional<Cycle>{at}||result.ready!=std::optional<Cycle>{at}){fail("typed write storage publication changed");return;}
   once(published);once(stored);
   if(!(std::uint32_t(c->rs2)&(1u<<29)))s_.feature("target.posted.masked_i8_storage_publications",1);
 }
 void masked_i8_packet(const std::shared_ptr<Command>&c,WriterPacket packet,Token completed,Cycle time,Token captured,PostedOneBeatWriter::Idle writer_idle={}){
       auto ack_done=token(),published=token();
       auto accepted=one_beat_writer_->push_transaction([this,c,packet,published](Cycle at,Token d_ready,Token d_accepted){
         typed_write_admit(packet.address,published,[this,c,packet,published,d_ready,d_accepted](Cycle at){
         spike_timing::WriteTransactionV1 request;request.address=packet.address;request.transaction_bytes=packet.bytes;
         request.beat_bytes=16;request.mask=packet.beat_masks.at(0);request.accepted=at;
         spike_timing::WriteTransactionEffectsV1 result;
         std::optional<spike_timing::WriteMissV5>miss;
         std::optional<spike_timing::VictimProbeV6>victim;
         std::optional<spike_timing::WriteProbeV2>probe;bool admitted=false;
         if(cold_write_&&cold_write_service_v6_){spike_timing::WriteTransactionEffectsV6 extended;
           admitted=cold_write_service_v6_->beat(cold_write_service_v6_->opaque,&request,&extended);
           result=std::move(extended.resident.base);probe=extended.resident.probe;miss=extended.miss;victim=extended.victim;
         }else if(cold_write_&&cold_write_service_v5_){spike_timing::WriteTransactionEffectsV5 extended;
           admitted=cold_write_service_v5_->beat(cold_write_service_v5_->opaque,&request,&extended);
           result=std::move(extended.resident.base);probe=extended.resident.probe;miss=extended.miss;
         }else if(cold_write_&&cold_write_service_){spike_timing::WriteTransactionEffectsV4 extended;
           admitted=cold_write_service_->beat(cold_write_service_->opaque,&request,&extended);
           result=std::move(extended.resident.base);probe=extended.resident.probe;miss=legacy_cold_miss(extended.miss);
         }else if(!cache_banks_.empty()&&write_service_v2_){spike_timing::WriteTransactionEffectsV2 extended;
           admitted=write_service_v2_->admit(write_service_v2_->opaque,&request,&extended);result=std::move(extended.base);probe=extended.probe;
         }else if(write_service_)admitted=write_service_->admit(write_service_->opaque,&request,&result);
         if(!admitted||!result.source_request.latency){
           fail("typed masked write refused: "+result.unavailable);return;
         }
         auto ready=token();Stage memory;memory.origin=tag(c,"masked_write_source_request");memory.earliest=at;
         memory.reads=result.source_request.reads;memory.latency=result.source_request.latency;memory.demands=result.source_request.demands;
         memory.hold_reads_until_ready=true;memory.kind=Q::Kind::memory_accept;
         auto writes=result.source_request.writes;
         typed_request(std::move(memory),writes,ready,published,miss,request.address,victim);
         auto source_ready=ready;
         if(probe){source_ready=token();q_.post(at,{ready},[this,c,probe,request,source_ready](auto&,auto t){masked_probe(c,*probe,request.address,source_ready,t);},Q::Kind::memory_accept);}
         q_.post(at,{source_ready},[this,c,request,result=std::move(result),writes=std::move(writes),published,d_ready,d_accepted](auto&,auto t)mutable{
           source_d_admit(t,[this,c,request,result=std::move(result),writes=std::move(writes),published,d_ready,d_accepted](Cycle time,Token released)mutable{
             PostedOneBeatSourceD::Read read;
             if(!cache_banks_.empty())read=[this,c,address=request.address](Cycle at,Token accepted,Token ready){cache_rmw_read(address,accepted,ready,c,at);};
             source_d_->push(request.address,result.sram_read_required,d_ready,d_accepted,
               [this,c,writes=std::move(writes),published,request,released](Cycle at,Token stored)mutable{
                 masked_publication(c,std::move(writes),published,stored,at,request.address,request.mask);
                 q_.post(at,{stored},[released](auto&q,auto){q.complete(released);},Q::Kind::command_retire);
               },time,std::move(read));
           });
         },Q::Kind::memory_accept);
         s_.feature("target.posted.masked_i8_rows",1);
         },at,"device_write");
       },time,ack_done,std::move(writer_idle));
       q_.post(time,{accepted},[captured](auto&q,auto){q.complete(captured);},Q::Kind::source_arrival);
       q_.post(time,{ack_done,published},[completed](auto&q,auto){q.complete(completed);},Q::Kind::command_retire);
 }
 void masked_i8_store(const std::shared_ptr<Command>&c,Cycle at){
   if(!source_d_||(!write_service_&&!write_service_v2_)||c->transfers.size()!=1||!c->phase||!config_.readout_stream||
      !(std::uint32_t(c->rs2)&(1u<<31))||(std::uint32_t(c->rs2)&(1u<<29))){fail("masked i8 source service absent or non-ACC input");return;}
   const auto transfer=c->transfers[0];auto packets=one_beat_writer_rows(transfer.address,transfer.rows,transfer.row_bytes,transfer.row_stride);
   if(!packets||transfer.rows!=c->acc_reads.size()){fail("masked i8 store requires original one-beat row packets");return;}
   std::vector<Token>done;
   for(std::size_t row=0;row<transfer.rows;++row){
     auto completed=token();done.push_back(completed);const auto packet=packets->at(row).front();
     readout_frontend_->push([this,c,row](Cycle time,Token accepted,Token ready){
       Stage read;read.origin=tag(c,"acc_read");read.earliest=time;read.reads={c->acc_reads[row]};read.latency=1;
       read.hold_reads_until_ready=true;bank(read,read.reads,1);read.kind=Q::Kind::operand_consume;
       stage(std::move(read),{},ready,[this,accepted](const auto&r){q_.post(*r.start,{},[accepted](auto&q,auto){q.complete(accepted);},Q::Kind::operand_consume);});
     },[this,c,packet,completed](Cycle time,Token captured){
       masked_i8_packet(c,packet,completed,time,captured);
     },at+1);
   }
   q_.post(at,done,[this,c](auto&,auto end){once(c->consume);once(c->done);c->finished=true;--dma_active_[1];pop(c,end);},Q::Kind::command_retire);
 }
 void aligned_i8_store(const std::shared_ptr<Command>&c,Cycle at){
   if(c->transfers.size()!=1||!c->phase||!config_.readout_stream||c->transfers[0].row_bytes!=16||
      c->transfers[0].address%16||c->transfers[0].row_stride%16||!(std::uint32_t(c->rs2)&(1u<<31))||
      (std::uint32_t(c->rs2)&(1u<<29))||c->transfers[0].rows>16||c->transfers[0].rows!=c->acc_reads.size()){
     fail("source i8 readout requires one full aligned client beat per original ACC row");return;
   }
   const auto transfer=c->transfers[0];std::vector<Token>done;
   for(std::size_t row=0;row<transfer.rows;++row){
     auto completed=token();done.push_back(completed);
     readout_frontend_->push([this,c,row](Cycle time,Token accepted,Token ready){
       Stage read;read.origin=tag(c,"acc_read");read.earliest=time;read.reads={c->acc_reads[row]};read.latency=1;
       read.hold_reads_until_ready=true;bank(read,read.reads,1);read.kind=Q::Kind::operand_consume;
       stage(std::move(read),{},ready,[this,accepted](const auto&r){q_.post(*r.start,{},[accepted](auto&q,auto){q.complete(accepted);},Q::Kind::operand_consume);});
     },[this,c,row,transfer,completed](Cycle time,Token captured){
       auto accepted=one_beat_writer_->push([this,c,row,transfer](Cycle at,Token response){
         auto effects=s_.memory({{transfer.address+row*transfer.row_stride,16,true}});
         if(!effects.latency){fail("source i8 write response service unknown");return;}
         Stage write;write.origin=tag(c,"memory_put_i8_full");write.earliest=at;
         // Selected Directory1/MSHR-plan1/SourceD2 is an uncontended
         // minimum ACK path, not a new per-command fee or a storage-publish
         // claim. Existing larger coherent/miss service is not added twice.
         write.latency=std::max<Cycle>(4,*effects.latency);write.reads=effects.reads;write.writes=effects.writes;
         write.demands=effects.demands;write.hold_reads_until_ready=true;write.kind=Q::Kind::memory_accept;
         if(s_.number("diagnostics.posted_source_timeline.pending_memory_visibility")==std::optional<double>{1})write.deferred_writes=effects.writes;
         stage(std::move(write),{},response);s_.feature("target.posted.i8_full_readout_rows",1);
       },time,completed);
       q_.post(time,{accepted},[captured](auto&q,auto){q.complete(captured);},Q::Kind::source_arrival);
     },at+1); // StoreController captures command before first DMA request.
   }
   q_.post(at,done,[this,c](auto&,auto end){once(c->consume);once(c->done);c->finished=true;--dma_active_[1];pop(c,end);},Q::Kind::command_retire);
 }
 void full_packet_request(const std::shared_ptr<Command>&c,WriterPacket packet,Token published,Cycle at,Token d_ready,Token d_accepted,
                          std::vector<Token>data,std::vector<Token>popped){
   const auto retired=resident_dirty_put_retirement_?token():published;
   typed_write_admit(packet.address,retired,[this,c,packet,published,retired,d_ready,d_accepted,data=std::move(data),popped=std::move(popped)](Cycle time)mutable{
     full_packet_request_owned(c,packet,published,retired,time,d_ready,d_accepted,std::move(data),std::move(popped));
   },at,"device_write");
 }
 void full_packet_request_owned(const std::shared_ptr<Command>&c,WriterPacket packet,Token published,Token retired,Cycle at,Token d_ready,Token d_accepted,
                                std::vector<Token>data,std::vector<Token>popped){
   spike_timing::FullWritePacketV3 request;request.address=packet.address;request.transaction_bytes=packet.bytes;request.beat_bytes=16;request.accepted=at;
   spike_timing::WriteTransactionEffectsV2 result;
   std::optional<spike_timing::WriteMissV5>miss;std::optional<spike_timing::VictimProbeV6>victim;bool admitted=false,early_retirement=false;
   if(resident_dirty_put_retirement_){
     if(!masked_packets_||!masked_packet_service_v9_){fail("resident dirty Put has no exact native V9 owner");return;}
     spike_timing::MaskedWritePacketV8 original;original.address=packet.address;original.transaction_bytes=packet.bytes;original.masks=packet.beat_masks;original.accepted=at;
     spike_timing::MaskedWriteEffectsV9 extended;admitted=masked_packet_service_v9_->packet(masked_packet_service_v9_->opaque,&original,&extended);
     early_retirement=extended.resident_dirty_no_probe;result=std::move(extended.original.resident);miss=extended.original.miss;victim=extended.original.victim;
     if(early_retirement&&(miss||victim||result.probe)){fail("native V9 resident dirty premise contradicts original transaction");return;}
   }else if(masked_packets_&&masked_packet_service_){
     spike_timing::MaskedWritePacketV8 original;original.address=packet.address;original.transaction_bytes=packet.bytes;
     original.masks=packet.beat_masks;original.accepted=at;spike_timing::WriteTransactionEffectsV6 extended;
     admitted=masked_packet_service_->packet(masked_packet_service_->opaque,&original,&extended);
     result=std::move(extended.resident);miss=extended.miss;victim=extended.victim;
   }else if(cold_write_&&cold_write_service_v6_){spike_timing::WriteTransactionEffectsV6 extended;
     admitted=cold_write_service_v6_->packet(cold_write_service_v6_->opaque,&request,&extended);result=std::move(extended.resident);miss=extended.miss;victim=extended.victim;
   }else if(cold_write_&&cold_write_service_v5_){spike_timing::WriteTransactionEffectsV5 extended;
     admitted=cold_write_service_v5_->packet(cold_write_service_v5_->opaque,&request,&extended);result=std::move(extended.resident);miss=extended.miss;
   }else if(cold_write_&&cold_write_service_){spike_timing::WriteTransactionEffectsV4 extended;
     admitted=cold_write_service_->packet(cold_write_service_->opaque,&request,&extended);result=std::move(extended.resident);miss=legacy_cold_miss(extended.miss);
   }else admitted=full_packet_service_->admit(full_packet_service_->opaque,&request,&result);
   if(!admitted||!result.base.source_request.latency){fail("typed raw packet refused: "+result.base.unavailable);return;}
   if(resident_dirty_put_retirement_&&!early_retirement)q_.post(at,{published},[this,retired](auto&,auto){once(retired);},Q::Kind::command_retire);
   auto ready=token();Stage memory;memory.origin=tag(c,"full_write_source_request");memory.earliest=at;
   memory.reads=result.base.source_request.reads;memory.latency=result.base.source_request.latency;memory.demands=result.base.source_request.demands;
   memory.hold_reads_until_ready=true;memory.kind=Q::Kind::memory_accept;auto writes=result.base.source_request.writes;
   std::optional<SourceRequestOwner>ordered;
   if(ordered_dirty_puts_&&early_retirement&&packet.full){
     ordered=SourceRequestOwner{token(),{}};
     std::vector<Q::OrderedWriterHandoff>handoffs;
     for(auto value:writes){auto prior=ordered_writes_.find(value);
       if(prior!=ordered_writes_.end()&&prior->second.line==request.address/64)
         handoffs.push_back({value,prior->second.published,prior->second.consumed});
     }
     auto ownership=memory.event(at);ownership.writes={writes.data(),writes.size()};
     if(!q_.bind_ordered_deferred_values(ownership,{writes.data(),writes.size()},ordered->admitted,published,ordered->dependencies,{handoffs.data(),handoffs.size()}))return;
     s_.feature("target.posted.ordered_dirty_put_value_handoffs",handoffs.size());
     for(auto value:writes){
       if(ordered_writes_.size()>=1048576&&!ordered_writes_.count(value)){fail("ordered writer software custody capacity");return;}
       ordered_writes_.insert_or_assign(value,PendingOrderedWrite{request.address/64,published,retired});
     }
     q_.post(at,{published},[this,writes,published](auto&,auto){for(auto value:writes){auto found=ordered_writes_.find(value);if(found!=ordered_writes_.end()&&found->second.published.id==published.id)ordered_writes_.erase(found);}},Q::Kind::local_publish);
   }
   typed_request(std::move(memory),writes,ready,published,miss,request.address,victim,false,false,ordered);auto source_ready=ready;
   if(result.probe){source_ready=token();q_.post(at,{ready},[this,c,probe=*result.probe,request,source_ready](auto&,auto t){masked_probe(c,probe,request.address,source_ready,t);},Q::Kind::memory_accept);}
   auto all_stored=std::make_shared<std::vector<Token>>();for(std::size_t beat=0;beat<data.size();++beat)all_stored->push_back(token());
   q_.post(at,{source_ready},[this,c,request,packet,data=std::move(data),popped=std::move(popped),d_ready,d_accepted,all_stored,retired,early_retirement](auto&,auto t){
     source_d_admit(t,[this,c,request,packet,data=std::move(data),popped=std::move(popped),d_ready,d_accepted,all_stored,retired,early_retirement](Cycle time,Token released){
       PostedFullPacketSourceD::Read read;
       // PutPartial needs the original full beat at S1 even when this beat's
       // byte mask is zero or full. Opcode is a property of the whole packet.
       if(masked_packets_&&!packet.full)read=[this,c,request](std::size_t beat,Cycle at,Token accepted,Token ready){cache_rmw_read(request.address+beat*16,accepted,ready,c,at);};
       const auto source_captured=full_packet_source_d_->push(data,popped,d_ready,d_accepted,[this,c,request,packet,all_stored](std::size_t beat,Cycle time,Token stored){
         const auto mask=packet.beat_masks.at(beat);
         if(mask)masked_publication(c,{},all_stored->at(beat),stored,time,request.address+beat*16,mask);
         else{once(all_stored->at(beat));once(stored);}
         s_.feature(masked_packets_?"target.posted.original_write_beats":"target.posted.full_raw_write_beats",1);
       },time,std::move(read),source_d_pipeline_?PostedFullPacketSourceD::Done{[this,released](Cycle){once(released);s_.feature("target.posted.source_d_write_input_releases",1);}}:PostedFullPacketSourceD::Done{});
       if(early_retirement)q_.post(time,{source_captured},[this,retired](auto&,auto){once(retired);s_.feature("target.posted.resident_dirty_put_mshr_request_releases",1);},Q::Kind::command_retire);
       if(!source_d_pipeline_)q_.post(time,*all_stored,[released](auto&q,auto){q.complete(released);},Q::Kind::command_retire);
     });
   },Q::Kind::memory_accept);
   // The admitted epoch forbids external shared-memory consumers. Coarse
   // native cache-line ownership closes after ALL actual S4 writes, not ACK.
   q_.post(at,*all_stored,[this,c,writes=std::move(writes),published](auto&,auto t)mutable{masked_publication(c,std::move(writes),published,token(),t);},Q::Kind::local_publish);
   s_.feature(masked_packets_?"target.posted.original_write_packets":"target.posted.full_raw_write_packets",1);
 }
 // StoreController counts the Scratchpad's local read-request responses.
 // These are distinct from StreamWriter D acknowledgements and SourceD S4.
 void begin_local_store(const std::shared_ptr<Command>&c,std::size_t requests){
   if(!store_local_completion_)return;
   if(!requests||c->local_store_remaining||c->store_output_done||pending_store_obligations_.size()+2>131072){fail("store local tracker software custody");return;}
   c->local_store_remaining=requests;c->store_output_done=token();c->store_credit_free=token();
   pending_store_obligations_.emplace(c->store_output_done->id,*c->store_output_done);
   pending_store_obligations_.emplace(c->store_credit_free->id,*c->store_credit_free);
 }
 void store_local_response(const std::shared_ptr<Command>&c,Cycle at){
   if(!store_local_completion_)return;
   if(!c->local_store_remaining){fail("store local response repeated or outside original request");return;}
   s_.feature("target.posted.store_local_request_responses",1);
   if(--c->local_store_remaining)return;
   // bytes_left is registered before asserting cmd_completed.valid.
   retire_local_store(c,at+1);
 }
 void retire_local_store(const std::shared_ptr<Command>&c,Cycle at){
   q_.post_settled(at,{},[this,c](auto&,auto t){
     // Controller.scala425-440: EX, then LD, then ST. Observe all ordinary
     // source completions on this edge before selecting the store response.
     bool higher=ws_operand_pipeline_&&ws_last_completion_==std::optional<Cycle>{t};
     for(const auto&other:commands_)if(other->group<2&&q_.completed(other->done)==std::optional<Cycle>{t}){higher=true;break;}
     if(higher||last_store_completion_at_==std::optional<Cycle>{t}){
       s_.feature("target.posted.store_completion_arbitration_wait_cycles",1);retire_local_store(c,t+1);return;
     }
     last_store_completion_at_=t;once(c->done);c->finished=true;s_.feature("target.posted.store_local_tracker_completions",1);
     // Registered entry.valid clears on the successful completion handshake.
     q_.post(t+1,{},[this,c](auto&,auto reused){
       if(!dma_active_[1]||!c->store_credit_free){fail("store local tracker credit ownership");return;}
       --dma_active_[1];once(*c->store_credit_free);pending_store_obligations_.erase(c->store_credit_free->id);schedule_next(2,reused);
     },Q::Kind::command_retire);
   },Q::Kind::command_retire);
 }

 void store_outputs_complete(const std::shared_ptr<Command>&c,Cycle at){
   if(store_local_completion_){
     if(!c->store_output_done){fail("store output completion without original obligation");return;}
     once(*c->store_output_done);pending_store_obligations_.erase(c->store_output_done->id);s_.feature("target.posted.store_output_completions",1);
   }else{once(c->consume);once(c->done);c->finished=true;--dma_active_[1];if(store_request_release_)schedule_next(2,at);else pop(c,at);}
 }
 void full_packet_store(const std::shared_ptr<Command>&c,Cycle at){
   if((!full_packet_service_&&!masked_packet_service_)||!c->phase||c->transfers.size()!=1||!config_.readout_stream||
      !(std::uint32_t(c->rs2)&(1u<<31))||(!masked_packets_&&!(std::uint32_t(c->rs2)&(1u<<29)))){fail("full packet writer requires original raw ACC readout");return;}
   const auto transfer=c->transfers[0];auto rows=masked_packets_?masked_writer_rows(transfer.address,transfer.rows,transfer.row_bytes,transfer.row_stride):full_writer_rows(transfer.address,transfer.rows,transfer.row_bytes,transfer.row_stride,16,64);
   if(!rows||rows->size()!=c->acc_reads.size()||rows->size()>16){fail("full packet raw row mapping unsupported");return;}
   for(const auto&row:*rows)if(row.empty()||row.size()>4){fail("full packet raw row packet bound");return;}
   begin_local_store(c,rows->size());
   std::vector<Token>done,requests;
   auto unread=std::make_shared<std::size_t>(rows->size());
   for(std::size_t row=0;row<rows->size();++row){
     auto completed=token();done.push_back(completed);auto packets=rows->at(row);
     auto request=readout_frontend_->push([this,c,row,unread](Cycle time,Token accepted,Token ready){
       if(store_request_release_)q_.post(time,{ready},[this,c,unread](auto&,auto){
         if(!*unread){fail("store local row consumption ownership");return;}
         if(!--*unread){once(c->consume);s_.feature("target.posted.store_local_row_consumptions",1);}
       },Q::Kind::operand_consume);
       Stage read;read.origin=tag(c,"acc_read");read.earliest=time;read.reads={c->acc_reads[row]};read.latency=1;
       read.hold_reads_until_ready=true;bank(read,read.reads,1);read.kind=Q::Kind::operand_consume;
       stage(std::move(read),{},ready,[this,c,accepted](const auto&r){q_.post(*r.start,{},[this,c,accepted](auto&q,auto t){q.complete(accepted);store_local_response(c,t);},Q::Kind::operand_consume);});
     },[this,c,packets=std::move(packets),completed](Cycle time,Token captured){
       std::vector<Token>packet_done;std::vector<std::size_t>beats;std::vector<PostedFullPacketWriter::Memory>memory;
       for(const auto&packet:packets){
         auto ack_done=token(),published=token();packet_done.push_back(ack_done);packet_done.push_back(published);beats.push_back(packet.bytes/16);
         memory.push_back([this,c,packet,published](Cycle at,Token d_ready,Token d_accepted,const auto&data,const auto&popped){full_packet_request(c,packet,published,at,d_ready,d_accepted,data,popped);});
       }
       std::vector<Token>acks;for(std::size_t i=0;i<packet_done.size();i+=2)acks.push_back(packet_done[i]);
       auto accepted=full_packet_writer_->push_row(std::move(beats),std::move(memory),time,std::move(acks));
       q_.post(time,{accepted},[captured](auto&q,auto){q.complete(captured);},Q::Kind::source_arrival);
       q_.post(time,std::move(packet_done),[completed](auto&q,auto){q.complete(completed);},Q::Kind::command_retire);
     },at+1);requests.push_back(request);
   }
   if(store_request_release_)q_.post(at,requests,[this,c,count=rows->size()](auto&,auto accepted){
     // StoreController releases its FIFO on final DMA req.fire. A singleton
     // visits sending_rows on the next edge before recognizing wrapped0.
     q_.post(accepted+(count==1?2:1),{},[this,c](auto&,auto t){s_.feature("target.posted.store_controller_request_releases",1);pop(c,t);},Q::Kind::source_arrival);
   },Q::Kind::source_arrival);
   q_.post(at,done,[this,c](auto&,auto end){store_outputs_complete(c,end);},Q::Kind::command_retire);
 }
 void pool_capture(const std::shared_ptr<Command>&c,PoolReadoutRequest request,WriterPacket packet,
                   Cycle at,Token captured,Token completed){
   const auto free=token();std::vector<Token>deps;if(pool_writer_free_)deps.push_back(*pool_writer_free_);pool_writer_free_=free;
   q_.post(at,std::move(deps),[this,c,request,packet,captured,completed,free](auto&,auto t){
     if((!request.pool&&pool_register_)||(request.pool&&(!pool_register_||
        *pool_register_!=std::make_pair(request.output_address,request.bytes)))){
       fail("pool reduction register request identity/order mismatch");return;
     }
     pool_register_=std::make_pair(request.output_address,request.bytes);pool_register_owner_=c.get();
     s_.feature("target.posted.pool_writer_captures",1);
     if(!request.store){
       once(captured);once(completed);
       q_.post(t+1,{},[free](auto&q,auto){q.complete(free);},Q::Kind::source_arrival);
     }else{
       pool_register_.reset();pool_register_owner_=nullptr;
       if(masked_packets_){
         const auto packets=*writer_packets(request.output_address,request.bytes,16,64);
         std::vector<Token>acks,done;std::vector<std::size_t>beats;std::vector<PostedFullPacketWriter::Memory>memory;
         for(const auto&original:packets){auto ack=token(),published=token();acks.push_back(ack);done.push_back(ack);done.push_back(published);beats.push_back(original.bytes/16);
           memory.push_back([this,c,original,published](Cycle at,Token ready,Token accepted,const auto&data,const auto&popped){full_packet_request(c,original,published,at,ready,accepted,data,popped);});
         }
         auto accepted=full_packet_writer_->push_row(std::move(beats),std::move(memory),t,std::move(acks),
           [this,free](Cycle at){q_.post(at,{},[free](auto&q,auto){q.complete(free);},Q::Kind::source_arrival);});
         q_.post(t,{accepted},[captured](auto&q,auto){q.complete(captured);},Q::Kind::source_arrival);
         q_.post(t,std::move(done),[completed](auto&q,auto){q.complete(completed);},Q::Kind::command_retire);
       }else masked_i8_packet(c,packet,completed,t,captured,[this,free](Cycle idle){
         q_.post(idle,{},[free](auto&q,auto){q.complete(free);},Q::Kind::source_arrival);
       });
     }
   },Q::Kind::source_arrival);
 }
 void pool_store(const std::shared_ptr<Command>&c,Cycle at){
   if(!ordered_pool_readout_||!c->phase||c->phase->pool_requests.empty()||!readout_frontend_||!source_d_||
      (!write_service_&&!write_service_v2_)||!one_beat_writer_){fail("ordered pool source actors unavailable");return;}
   const auto&requests=c->phase->pool_requests;
   // Validate every real final packet BEFORE publishing any modeled request.
   // Original masked multibeat TL transactions remain UNKNOWN; never split
   // them into fabricated one-beat transactions just to fit this consumer.
   for(const auto&r:requests)if(r.store){
     const auto packets=writer_packets(r.output_address,r.bytes,16,64);
     if(!packets||packets->empty()||packets->size()>4||(!masked_packets_&&(packets->size()!=1||packets->front().bytes!=16||packets->front().beat_masks.size()!=1))){
       fail("ordered pool final original packet geometry unsupported");return;
     }
   }
   begin_local_store(c,requests.size());
   struct Cursor{std::size_t next=0;std::vector<Token>done,consumed;};auto cursor=std::make_shared<Cursor>();
   auto feed=std::make_shared<std::function<void(Cycle)>>();std::weak_ptr<std::function<void(Cycle)>>weak=feed;
   *feed=[this,c,cursor,weak](Cycle t){
     const auto request=c->phase->pool_requests.at(cursor->next++);auto completed=token(),consumed=token();cursor->done.push_back(completed);cursor->consumed.push_back(consumed);
     WriterPacket packet;if(request.store)packet=writer_packets(request.output_address,request.bytes,16,64)->front();
     auto entered=readout_frontend_->push_ordered([this,c,request,consumed](Cycle time,Token accepted,Token ready){
       if(!request.local_row){once(accepted);once(ready);once(consumed);store_local_response(c,time);s_.feature("target.posted.pool_garbage_requests",1);return;}
       q_.post(time,{ready},[consumed](auto&q,auto){q.complete(consumed);},Q::Kind::operand_consume);
       Stage read;read.origin=tag(c,"pool_acc_read");read.earliest=time;read.reads={*request.local_row};read.latency=1;
       read.hold_reads_until_ready=true;bank(read,read.reads,1);read.kind=Q::Kind::operand_consume;
       stage(std::move(read),{},ready,[this,c,accepted](const auto&r){q_.post(*r.start,{},[this,c,accepted](auto&q,auto t){q.complete(accepted);store_local_response(c,t);},Q::Kind::operand_consume);});
       s_.feature("target.posted.pool_acc_reads",1);
     },[this,c,request,packet,completed](Cycle time,Token captured){pool_capture(c,request,packet,time,captured,completed);},t,!request.local_row);
     if(cursor->next<c->phase->pool_requests.size()){
       auto next=weak.lock();if(!next){fail("pool source cursor ownership lost");return;}
       q_.post(t,{entered},[next](auto&q,auto time){q.post(time+1,{},[next](auto&,auto now){(*next)(now);},Q::Kind::source_arrival);},Q::Kind::source_arrival);
     }else {
      if(store_request_release_)q_.post(t,{entered},[this,c,count=c->phase->pool_requests.size()](auto&,auto accepted){
        q_.post(accepted+(count==1?2:1),{},[this,c](auto&,auto t){s_.feature("target.posted.store_controller_request_releases",1);pop(c,t);},Q::Kind::source_arrival);
      },Q::Kind::source_arrival);
      q_.post(t,cursor->consumed,[this,c](auto&,auto){once(c->consume);},Q::Kind::operand_consume);
      q_.post(t,cursor->done,[this,c](auto&,auto end){
       if(pool_register_&&pool_register_owner_==c.get()){fail("pool command leaves uncommitted reduction register");return;}
       store_outputs_complete(c,end);
     },Q::Kind::command_retire);}
   };
   q_.post(at+1,{},[feed](auto&,auto t){(*feed)(t);},Q::Kind::source_arrival);
 }
 void store(const std::shared_ptr<Command>&c,Cycle at){
   if(c->kind=="pool_store"||c->kind=="pool_store_act1"){pool_store(c,at);return;}
   if(full_packet_writer_&&(masked_packets_||(std::uint32_t(c->rs2)&(1u<<29)))){full_packet_store(c,at);return;}
   // The typed SourceD route owns full as well as partial one-beat writes.
   // A full mask bypasses the SRAM read, but still traverses request admission,
   // A/D backpressure and independent S4 publication. Do not replace those
   // actors with the older aggregate minimum merely because the row is aligned.
   if(source_d_&&!(std::uint32_t(c->rs2)&(1u<<29))&&c->transfers.size()==1){
     masked_i8_store(c,at);return;
   }
   if(i8_readout_&&!(std::uint32_t(c->rs2)&(1u<<29))){aligned_i8_store(c,at);return;}
   if(c->transfers.size()!=1 || !c->phase || !config_.readout_stream ||
       c->original.reads.empty() || c->transfers[0].row_bytes%16 || c->transfers[0].address%16){
     fail("posted store requires full raw accumulator transactions");return;
   }
   if(!(std::uint32_t(c->rs2)&(1u<<31))||!(std::uint32_t(c->rs2)&(1u<<29))){fail("posted store supports raw full-width ACC only");return;}
   const auto transfer=c->transfers[0];
   if(transfer.rows>c->acc_reads.size() || transfer.row_bytes>64 || transfer.row_stride%16){fail("posted store row mapping");return;}
   std::vector<Token> results;
   for(std::size_t row=0;row<transfer.rows;++row){
     auto read_done=token();Stage read;read.origin=tag(c,"acc_read");read.earliest=at+row;read.reads={c->acc_reads[row]};
     read.hold_reads_until_ready=true;read.latency=1; // physical SRAM read ownership ends at response
     bank(read,read.reads,1);read.kind=Q::Kind::operand_consume;
     stage(std::move(read),{},read_done,[this,c,row,transfer](auto&r){
       q_.post(*r.ready+2+8+2,{},[this,c,row,transfer](auto&,auto time){
         auto effects=s_.memory({{transfer.address+row*transfer.row_stride,transfer.row_bytes,true}});
         if(!effects.latency){fail("store memory completion unknown");return;}
         Stage write;write.origin=tag(c,"memory_put");write.earliest=time;write.latency=effects.latency;write.reads=effects.reads;write.writes=effects.writes;
         if(s_.number("diagnostics.posted_source_timeline.pending_memory_visibility")==std::optional<double>{1})write.deferred_writes=effects.writes;
         write.demands=effects.demands;write.hold_reads_until_ready=true;write.kind=Q::Kind::memory_accept;
         // Per-row tokens were captured at admission in the caller below.
         stage(std::move(write),{},store_rows_.at(c.get()).at(row));
       },Q::Kind::memory_accept);
     });results.push_back(token());
   }
   store_rows_[c.get()]=results;
   q_.post(at,results,[this,c](auto&,auto time){once(c->consume);once(c->done);c->finished=true;--dma_active_[1];store_rows_.erase(c.get());pop(c,time);},Q::Kind::command_retire);
 }
 std::map<Command*,std::vector<Token>>store_rows_;
 public:
 void source_actors(const spike_timing::SourceActorSinkV1&sink){
   if(sink.version!=1||sink.size!=sizeof(sink)||!sink.edge||!sink.role)throw std::invalid_argument("source actor observation ABI mismatch");
   actor_sink_=sink;
   for(auto role:{ActorRole::load_command,ActorRole::store_command,ActorRole::execute_command,ActorRole::load_rs_wait,ActorRole::store_rs_wait,ActorRole::execute_rs_wait})sink.role(sink.opaque,role,0);
   sink.role(sink.opaque,ActorRole::execute_feed,1);
   if(reader_request_path_)sink.role(sink.opaque,ActorRole::reader_slot,16);
   if(one_beat_writer_||full_packet_writer_){sink.role(sink.opaque,ActorRole::writer_state,1);sink.role(sink.opaque,ActorRole::writer_slot,16);}
   if(one_beat_writer_)one_beat_writer_->source_actors(sink);
   if(full_packet_writer_)full_packet_writer_->source_actors(sink);
 }
 void read_allocations(const spike_timing::ReadAllocationServiceV7&service){
   if(service.version!=7||service.size!=sizeof(service)||service.snapshot_revision!=5||!service.opaque||!service.take||!service.client_released)
     throw std::invalid_argument("read allocation source service ABI mismatch");
   read_allocation_service_v7_=service;
 }
 Token submit_read_allocation(spike_timing::ReadAllocationV7 allocation,const merlin_timing::StageOrigin&origin,Cycle at,std::vector<Token>gates,PostedReadAllocationResponse::Sink sink={},std::optional<Token>*request_admitted=nullptr,std::optional<Token>preallocated={}){
   const auto pub=token(),ready=token();const auto effects=allocation.source_request;
   const bool resident_get=resident_get_retirement_&&allocation.device_resident_no_probe;
   if(resident_get&&(!sink||!allocation.resident||allocation.inner_acquire||allocation.victim||
      allocation.miss.evicted_line||allocation.miss.dirty_eviction||allocation.miss.acquire_block||
      allocation.miss.fill_latency||allocation.miss.fill_bus||allocation.miss.release_latency||
      allocation.miss.release_bus||!allocation.miss.release_writes.empty())){
     fail("resident Get early MSHR retirement lacks original no-probe device ownership");return pub;
   }
   // A resident no-probe Get has all MSHR no_wait predicates set from
   // allocation. Selected MSHR reloads when its SourceD request is captured,
   // independently of the later SRAM/D/value-publication completion.
   std::shared_ptr<FillWindow>fill;
   if(beat_forwarding_&&!allocation.resident&&allocation.miss.acquire_block){
     fill=std::make_shared<FillWindow>(FillWindow{allocation.inner_address%64==0,{}});
     for(unsigned b=0;b<8;++b)fill->chunks.push_back(token());
   }
   const auto cache_publication=fill?token():pub;
   const auto retired=resident_get?(preallocated?*preallocated:token()):cache_publication;
   if(preallocated&&!resident_get)q_.post(at,{cache_publication},[retired=*preallocated](auto&q,auto){q.complete(retired);},Q::Kind::command_retire);
   Stage request;request.origin=origin;request.earliest=at;request.reads=effects.reads;
   request.demands=effects.demands;request.latency=effects.latency;request.hold_reads_until_ready=true;
   auto writes=effects.writes;
   SourceRequestOwner owner{token(),{}};auto ownership=request.event(at);ownership.writes={writes.data(),writes.size()};
   if(!q_.bind_deferred_values(ownership,{writes.data(),writes.size()},owner.admitted,cache_publication,owner.dependencies))return pub;
   if(request_admitted)*request_admitted=owner.admitted;
   const auto admitted=token();owner.dependencies.insert(owner.dependencies.end(),gates.begin(),gates.end());owner.dependencies.push_back(admitted);
   if(preallocated)once(admitted);
   else typed_write_admit(allocation.miss.line*64,retired,[this,admitted](Cycle t){q_.post(t,{},[admitted](auto&q,auto){q.complete(admitted);},Q::Kind::memory_accept);},at);
   // Bind before posting: later original readers must see this real pending
   // cache owner even while the prefix or finite MSHR admission is waiting.
   typed_request(std::move(request),writes,ready,cache_publication,allocation.miss,allocation.miss.line*64,allocation.victim,true,allocation.resident,owner,fill);
   q_.post(at,{ready},[this,allocation,origin,writes=std::move(writes),pub,cache_publication,fill,retired,resident_get,sink=std::move(sink)](auto&,auto now)mutable{
     source_d_admit(now,[this,allocation,origin,writes=std::move(writes),pub,cache_publication,fill,retired,resident_get,sink=std::move(sink)](Cycle t,Token released)mutable{
       if(resident_get){once(retired);s_.feature("target.posted.resident_get_mshr_request_releases",1);}
       if(!read_allocation_response_)read_allocation_response_=std::make_unique<PostedReadAllocationResponse>(q_,read_input_retirement_,source_d_pipeline_);
       read_allocation_response_->push(allocation,[this,origin,fill](auto address,auto at,auto accepted,auto ready){
         if(!fill){allocation_read_port(origin,address,at,accepted,ready);return;}
         const auto chunk=(address%64)/8;
         q_.post(at,{fill->chunks.at(chunk),fill->chunks.at(chunk+1)},[this,origin,address,accepted,ready](auto&,auto t){allocation_read_port(origin,address,t,accepted,ready);},Q::Kind::operand_consume);
       },
         [this,origin,writes=std::move(writes),pub,cache_publication,fill,released](Cycle end)mutable{
           if(fill)once(pub);
           q_.post(end,fill?fill->chunks:std::vector<Token>{},[this,origin,writes=std::move(writes),pub,cache_publication,fill,released](auto&,auto end)mutable{
           Stage publication;publication.origin=origin;publication.earliest=end;publication.latency=0;publication.writes=writes;
           const auto result=s_.engine.submit_detached(publication.event(end));
           if(result.start!=std::optional<Cycle>{end}||result.ready!=std::optional<Cycle>{end}){fail("read allocation publication precedes original native owner");return;}
           once(cache_publication);if(!read_input_retirement_)once(released);s_.feature("target.posted.read_allocations_completed",1);
           },Q::Kind::local_publish);
         },t,read_input_retirement_?PostedReadAllocationResponse::Done{[this,released](Cycle){once(released);s_.feature("target.posted.source_d_read_input_releases",1);}}:PostedReadAllocationResponse::Done{},std::move(sink));
     },pub);
   },Q::Kind::memory_accept);return pub;
 }
 bool submit_read_allocations(const spike_timing::ReadAllocationEffectsV7&batch,const merlin_timing::StageOrigin&origin,Cycle at,
                              void*cookie,spike_timing::ReadAllocationReadyV7 completed,PostedReadAllocationResponse::Sink sink={},std::optional<Token>preallocated={},const std::vector<Token>*cpu_preallocated=nullptr){
   const auto limit=s_.number("limits.memory_entries").value_or(65536);
   if(batch.version!=7||batch.size!=sizeof(batch)||batch.snapshot_revision!=5||!batch.unavailable.empty()||!batch.source_request.latency||
      batch.response_stages!=2||batch.allocations.empty()||batch.allocations.size()>limit||!cold_write_||!read_allocation_service_v7_||!completed){
     fail("read allocation batch lacks partitioned original source ownership");return false;}
   if(preallocated&&batch.allocations.size()!=1){fail("preallocated packet does not have exactly one original cache owner");return false;}
   if(cpu_preallocated&&(preallocated||cpu_preallocated->size()!=batch.allocations.size())){fail("CPU preallocated requests differ from original allocation children");return false;}
   if(batch.parent_writebacks.size()>1){fail("private writeback prefix has multiple original publications");return false;}
   std::vector<ValueId>early_writes;
   for(const auto&phase:batch.parent_writebacks){
     if(batch.allocations.size()!=1||phase.before_child||phase.bytes!=64||phase.address%64||phase.writes.empty()){
       fail("private writeback publication lacks original singleton prefix phase");return false;
     }
     for(auto value:phase.writes){
       if(std::find(batch.source_request.writes.begin(),batch.source_request.writes.end(),value)!=batch.source_request.writes.end()){
         fail("private writeback prefix aliases late original parent publication");return false;
       }
       early_writes.push_back(value);
     }
   }
   std::sort(early_writes.begin(),early_writes.end());early_writes.erase(std::unique(early_writes.begin(),early_writes.end()),early_writes.end());
   for(const auto&a:batch.allocations){
     if(!a.source_request.latency){fail("read allocation child source effects unavailable");return false;}
     for(auto write:a.source_request.writes)
       if(std::find(batch.source_request.writes.begin(),batch.source_request.writes.end(),write)!=batch.source_request.writes.end()){
         fail("read allocation child aliases residual publication ownership");return false;
       }
   }
   const auto prefix=token(),published=token();
   Stage parent;parent.origin=origin;parent.earliest=at;parent.reads=batch.source_request.reads;
   parent.demands=batch.source_request.demands;parent.latency=batch.source_request.latency;parent.hold_reads_until_ready=true;
   auto prefix_published=prefix;
   if(early_writes.empty())masked_request(std::move(parent),batch.source_request.writes,prefix,published);
   else{
     prefix_published=token();SourceRequestOwner owner{token(),{}};
     auto ownership=parent.event(at);ownership.writes={early_writes.data(),early_writes.size()};
     if(!q_.bind_deferred_values(ownership,{early_writes.data(),early_writes.size()},owner.admitted,prefix_published,owner.dependencies))return false;
     ownership.reads={};ownership.writes={batch.source_request.writes.data(),batch.source_request.writes.size()};
     if(!q_.bind_deferred_values(ownership,ownership.writes,owner.admitted,published,owner.dependencies))return false;
     auto all_writes=early_writes;all_writes.insert(all_writes.end(),batch.source_request.writes.begin(),batch.source_request.writes.end());
     masked_request_bound(std::move(parent),all_writes,prefix,owner);
     q_.post(at,{prefix},[this,origin,early_writes,prefix_published](auto&,auto t){
       Stage publication;publication.origin=origin;publication.earliest=t;publication.latency=0;publication.writes=early_writes;
       auto result=s_.engine.submit_detached(publication.event(t));
       if(result.start!=std::optional<Cycle>{t}||result.ready!=std::optional<Cycle>{t}){fail("private writeback publication precedes original prefix");return;}
       once(prefix_published);s_.feature("target.posted.parent_writeback_prefix_publications",1);
     },Q::Kind::local_publish);
   }
   auto children=std::make_shared<std::vector<spike_timing::ReadAllocationV7>>(batch.allocations);
   // All child walks inherit the original parent prefix edge. A child fill
   // may read a coherence value that the *enclosing store* will publish at
   // final completion. Its previous owner was already consumed by the
   // prefix; waiting for that future enclosing publication would self-cycle.
   for(auto&a:*children){auto&reads=a.source_request.reads;
     reads.erase(std::remove_if(reads.begin(),reads.end(),[&](auto value){
       return std::find(batch.source_request.writes.begin(),batch.source_request.writes.end(),value)!=batch.source_request.writes.end();
     }),reads.end());
   }
   std::vector<Token>all{prefix_published};Token previous=prefix_published;
   std::size_t offset=0,child_index=0;
   for(auto&child:*children){
     const auto beats=child.inner_bytes/16;PostedReadAllocationResponse::Sink local;
     if(sink)local=[sink,offset](std::size_t beat,Cycle t,Token accepted){sink(offset+beat,t,accepted);};
     std::optional<Token>admitted;
     const auto lease=cpu_preallocated?std::optional<Token>{cpu_preallocated->at(child_index++)}:preallocated;
     const auto done=submit_read_allocation(std::move(child),origin,at,{previous},std::move(local),&admitted,lease);
     all.push_back(done);previous=beat_forwarding_?admitted.value_or(done):done;offset+=beats;
   }
   // One CPU memory completion, not one callback/instruction per allocation.
   q_.post(at,std::move(all),[this,origin,writes=batch.source_request.writes,published,cookie,completed](auto&,auto t){
     Stage publication;publication.origin=origin;publication.earliest=t;publication.latency=0;publication.writes=writes;
     const auto result=s_.engine.submit_detached(publication.event(t));
     if(result.start!=std::optional<Cycle>{t}||result.ready!=std::optional<Cycle>{t}){fail("read allocation parent publication precedes original owner");return;}
     once(published);completed(cookie,t);s_.feature("target.posted.read_allocation_batches_completed",1);
   },Q::Kind::memory_accept);return true;
 }
 bool submit_cpu_read(const spike_timing::CpuReadAdmissionV10&request,const merlin_timing::StageOrigin&origin,Cycle at,
                      void*cookie,spike_timing::ClassifyCpuReadV10 classify,spike_timing::ReadAllocationReadyV7 completed){
   if(request.version!=10||request.size!=sizeof(request)||!classify||!completed||!cold_write_||!deferred_read_lookup_||
      request.line_addresses.empty()||request.line_addresses.size()>2||
      (request.line_addresses.size()==2&&(request.line_addresses[1]!=request.line_addresses[0]+64||cold_cache_sets_<2))){
     fail("CPU deferred lookup lacks selected scalar request ownership");return false;
   }
   auto addresses=request.line_addresses;auto retired=std::make_shared<std::vector<Token>>();
   for(auto address:addresses){if(address%64){fail("CPU deferred lookup has unaligned original line");return false;}retired->push_back(token());}
   using Offer=std::function<void(std::size_t,Cycle)>;
   auto offer=std::make_shared<Offer>();std::weak_ptr<Offer>weak=offer;
   *offer=[this,addresses=std::move(addresses),retired,origin,cookie,classify,completed,weak](std::size_t i,Cycle t){
     auto next=weak.lock();if(!next){fail("CPU deferred lookup lost request owner");return;}
     if(i<addresses.size()){
       typed_write_admit(addresses[i],retired->at(i),[next,i](Cycle admitted){(*next)(i+1,admitted);},t,"cpu_read");return;
     }
     spike_timing::ReadAllocationEffectsV7 batch;const auto status=classify(cookie,t,&batch);
     if(status==spike_timing::CpuReadLookupStatusV10::retry){
       // The native private controller may have accepted a real probe while
       // the LLC request waited. Keep these actual leases until its observed
       // completion; polling changes no hardware capacity or release edge.
       q_.post(t+1,{},[next,i](auto&,auto now){(*next)(i,now);},Q::Kind::memory_accept);return;
     }
     if(status!=spike_timing::CpuReadLookupStatusV10::accepted||batch.allocations.size()!=addresses.size()){
       fail("CPU deferred lookup differs from original private miss requests");return;
     }
     for(std::size_t j=0;j<addresses.size();++j)if(batch.allocations[j].miss.line*64!=addresses[j]){
       fail("CPU deferred lookup changed original line order");return;
     }
     s_.feature("target.posted.cpu_read_lookup_after_mshr_admission",addresses.size());
     submit_read_allocations(batch,origin,t,cookie,completed,{},{},retired.get());
   };
   (*offer)(0,at);return true;
 }
 void masked_writes(const spike_timing::MaskedWriteServiceV9&service){
   if(service.version!=9||service.size!=sizeof(service)||!service.opaque||!service.packet)throw std::invalid_argument("native dirty Put ABI mismatch");
   masked_packet_service_v9_=service;
 }
 void masked_writes(const spike_timing::MaskedWriteServiceV8&service){
   if(service.version!=8||service.size!=sizeof(service)||!service.opaque||!service.packet)throw std::invalid_argument("original masked packet ABI mismatch");
   masked_packet_service_=service;
 }
 void full_write_packets(const spike_timing::FullWritePacketServiceV3&service){
   if(service.version!=3||service.size!=sizeof(service)||!service.opaque||!service.admit){fail("invalid full packet write service");return;}
   full_packet_service_=service;
 }
 void cold_writes(const spike_timing::ColdWriteServiceV4&service){
   if(service.version!=4||service.size!=sizeof(service)||!service.beat||!service.packet)
     throw std::invalid_argument("cold write service ABI mismatch");
   cold_write_service_=service;
 }
 void cold_writes(const spike_timing::ColdWriteServiceV5&service){
   if(service.version!=5||service.size!=sizeof(service)||!service.opaque||!service.beat||!service.packet)
     throw std::invalid_argument("cold write V5 service ABI mismatch");
   cold_write_service_v5_=service;
 }
 void cold_writes(const spike_timing::ColdWriteServiceV6&service){
   if(service.version!=6||service.size!=sizeof(service)||!service.opaque||!service.beat||!service.packet||!service.client_released)
     throw std::invalid_argument("cold write V6 service ABI mismatch");
   cold_write_service_v6_=service;
 }
 void write_transactions(const spike_timing::WriteTransactionServiceV1&service){
   if(service.version!=1||service.size!=sizeof(service)||!service.opaque||!service.admit){fail("invalid typed write service");return;}
   write_service_=service;
 }
 void write_transactions(const spike_timing::WriteTransactionServiceV2&service){
   if(service.version!=2||service.size!=sizeof(service)||!service.opaque||!service.admit){fail("invalid typed probe write service");return;}
   write_service_v2_=service;
 }
 void memory_lookup_query(const merlin_timing::MemoryMilestoneQueryV2&query){
   if(query.version!=2||query.size!=sizeof(query)||!query.opaque||!query.last_observation){fail("invalid native lookup query");return;}
   lookup_query_=query;
 }
 PostedSourceObserver(spike_timing::Services&s,Q&q,HardwareConfig h,StagedConfig config,ValueId base):s_(s),q_(q),h_(h),config_(std::move(config)),base_(base){
   if(h_.source_zero_writer){
     if(!h_.first_layer_optimizations||h_.dim!=16||h_.element_bytes!=1||
        s_.number("target.hardware.zero_writer_request_register_entries")!=std::optional<double>{1}||
        s_.number("target.hardware.zero_writer_pixel_register_entries")!=std::optional<double>{1}||
        s_.number("target.hardware.zero_writer_max_columns")!=std::optional<double>{64})
       throw std::invalid_argument("zero writer requires selected request1/pixel1 SP geometry");
     zero_writer_=std::make_unique<PostedZeroWriter>(q_,[this](const auto&row,Cycle at){
       if(last_mvin_response_at_==std::optional<Cycle>{at}||!full_acc_last_pending_.empty()||
          (identity_pixel_&&identity_pixel_->last_packet_output))return false;
       Stage write;write.origin=row.origin;write.earliest=at;write.writes={row.address};write.latency=1;bank(write,write.writes,1);
       const auto ready=s_.engine.earliest_stage_start(write.event(at));if(!ready){fail("zero writer SP readiness unknown");return false;}return *ready==at;
     },[this](const auto&row,Cycle at){
       Stage write;write.origin=row.origin;write.earliest=at;write.writes={row.address};write.latency=1;bank(write,write.writes,1);
       const auto result=s_.engine.submit_detached(write.event(at));
       if(result.start!=at||result.ready!=at+1){fail("zero writer local publication changed at admission");return;}
       row.published(at);
     });
   }
   if(const auto banked=s_.number("target.scheduling.source_banked_accumulator_bounds")){
     const auto count=s_.number("target.hardware.accumulator_bank_count");
     const auto rows=s_.number("target.hardware.accumulator_bank_rows");
     if(*banked!=1||!count||!rows||*count<1||*count>16||*rows<1||
        *count!=std::floor(*count)||*rows!=std::floor(*rows)||*rows>h_.accumulator_rows||
        (*count)*(*rows)!=h_.accumulator_rows||
        s_.number("target.hardware.accumulator_localaddr_contiguous_banks")!=std::optional<double>{1})
       throw std::invalid_argument("banked accumulator bound needs exact selected LocalAddr/memory geometry");
     accumulator_bank_rows_=static_cast<std::uint64_t>(*rows);
     if(accumulator_bank_rows_&(accumulator_bank_rows_-1))
       throw std::invalid_argument("LocalAddr accumulator bank rows must be a power of two");
     for(unsigned b=0;b<static_cast<unsigned>(*count);++b){
       const auto id=s_.resource("accelerator.storage.accumulator.bank."+std::to_string(b));
       if((config_.accumulator_storage_resource&&id==*config_.accumulator_storage_resource)||
          std::find(accumulator_banks_.begin(),accumulator_banks_.end(),id)!=accumulator_banks_.end())
         throw std::invalid_argument("independent accumulator bank resources must not alias");
       accumulator_banks_.push_back(id);
     }
   }
   if(const auto selected=s_.number("target.scheduling.source_accumulator_row_ports")){
     if(*selected!=1||accumulator_banks_.empty()||
        s_.number("target.hardware.accumulator_two_port_storage")!=std::optional<double>{1}||
        config_.late_accumulator_write_pipeline!=std::optional<Cycle>{2})
       throw std::invalid_argument("ACC row ports require selected two-port latency2 memories");
     accumulator_ports_=std::make_unique<PostedAccumulator>(q_,accumulator_banks_.size(),accumulator_bank_rows_);
   }
   if(const auto selected=s_.number("target.scheduling.source_memory_beat_forwarding")){
     if(*selected!=1||s_.number("memory.source_read_allocations.enabled")!=std::optional<double>{1}||
        s_.number("target.hardware.mshr_zero_offset_grant_wormhole")!=std::optional<double>{1}||
        s_.number("target.hardware.sinkd_first_last_response")!=std::optional<double>{1})
       throw std::invalid_argument("beat forwarding requires selected MSHR zero-offset and SinkD first/last source law");
     beat_forwarding_=true;
   }
   if(const auto input=s_.number("target.scheduling.source_d_read_input_retirement")){
     if(*input!=1||s_.number("memory.source_read_allocations.enabled")!=std::optional<double>{1}||
        s_.number("target.hardware.source_d_s2_entries")!=std::optional<double>{1}||
        s_.number("target.hardware.source_d_s3_entries")!=std::optional<double>{1}||
        s_.number("target.hardware.source_d_read_sram_stages")!=std::optional<double>{2}||
        s_.number("target.hardware.source_d_s1_last_input_retires_busy")!=std::optional<double>{1})
       throw std::invalid_argument("SourceD input retirement needs selected finite s2/s3 and actual last-input law");
     read_input_retirement_=true;
   }
   if(const auto first=s_.number("target.scheduling.source_ws_first_row_bypass")){
     if(*first!=1||s_.number("target.hardware.execute_waiting_state_can_fire_first_row")!=std::optional<double>{1}||
        s_.number("target.hardware.execute_last_row_pops_in_compute")!=std::optional<double>{1})
       throw std::invalid_argument("WS first-row service requires selected combinational waiting-state feed and last-row pop");
     ws_first_row_=true;
   }
   if(const auto selected=s_.number("target.scheduling.source_ws_total_rows_completion")){
     if(*selected!=1||!ws_first_row_||!accumulator_ports_||
        s_.number("target.hardware.execute_ws_minimum_total_rows")!=std::optional<double>{4}||
        s_.number("target.hardware.mesh_last_uses_actual_total_rows")!=std::optional<double>{1}||
        s_.number("target.hardware.execute_completion_at_mesh_last_response")!=std::optional<double>{1})
       throw std::invalid_argument("WS output completion requires actual registered total_rows/tag last-response law");
     ws_total_rows_completion_=true;
   }
   if(const auto selected=s_.number("target.scheduling.source_ws_garbage_preload_total_rows")){
     if(*selected!=1||!ws_total_rows_completion_||
        s_.number("target.hardware.execute_ws_garbage_preload_uses_actual_total_rows")!=std::optional<double>{1})
       throw std::invalid_argument("garbage PRELOAD requires selected WS total_rows gating and unchanged mesh tags");
     ws_garbage_preload_rows_=true;
   }
   if(const auto selected=s_.number("target.scheduling.source_ws_operand_pipeline")){
     if(*selected!=1||!ws_garbage_preload_rows_||!accumulator_ports_||config_.scratchpad_bank_resources.size()!=4||
        config_.scratchpad_bank_rows!=4096||config_.late_accumulator_write_pipeline!=std::optional<Cycle>{2})
       throw std::invalid_argument("finite WS operands require selected source storage and output pipeline");
     for(const auto&fact:std::array<std::pair<const char*,double>,8>{{{"execute_control_queue_entries",5},{"execute_sp_response_queue_entries",4},{"execute_sram_response_queue_entries",1},{"execute_mesh_tag_queue_entries",6},{"execute_mesh_matmul_ids",5},{"execute_mesh_tile_latency",0},{"execute_mesh_output_delay",1},{"execute_mesh_shifter_banks",1}}})
       if(s_.number(std::string("target.hardware.")+fact.first)!=std::optional<double>{fact.second})
         throw std::invalid_argument("finite WS operands differ from selected generated source geometry");
     ws_operand_pipeline_=true;
   }
   if(const auto deferred=s_.number("target.scheduling.source_deferred_read_lookup")){
     if(*deferred!=1||!read_input_retirement_||
        s_.number("target.scheduling.source_cold_write_misses")!=std::optional<double>{1}||
        s_.number("target.hardware.scheduler_directory_read_at_mshr_allocation")!=std::optional<double>{1})
       throw std::invalid_argument("deferred read lookup requires selected Scheduler Directory allocation and original read packets");
     deferred_read_lookup_=true;
   }
   if(const auto shared=s_.number("target.scheduling.source_d_shared_pipeline")){
     if(*shared!=1||!read_input_retirement_||
        s_.number("target.scheduling.source_masked_packet_readout")!=std::optional<double>{1}||
        s_.number("target.hardware.source_d_s4_entries")!=std::optional<double>{1})
       throw std::invalid_argument("shared SourceD requires original masked packets and selected finite S2/S3/S4 registers");
     source_d_pipeline_=std::make_shared<PostedSourceDPipeline>(q_);
   }
   if(const auto resident=s_.number("target.scheduling.source_resident_get_request_retirement")){
     if(*resident!=1||!read_input_retirement_||
        s_.number("target.hardware.mshr_resident_get_no_wait_at_source_d_request")!=std::optional<double>{1})
       throw std::invalid_argument("resident Get MSHR retirement requires selected no_wait/request-capture law");
     resident_get_retirement_=true;
   }
   if(const auto visible=s_.number("target.scheduling.source_controller_visibility")) {
     if(*visible!=1)throw std::invalid_argument("invalid registered controller visibility selection");
     registered_visibility_=true;
   }
   if(registered_visibility_ && (config_.issue_latency!=std::optional<Cycle>{1} ||
      s_.number("target.hardware.source_rs_valid_registered_stages")!=std::optional<double>{1} ||
      s_.number("target.hardware.source_controller_visibility_stages.load")!=std::optional<double>{1} ||
      s_.number("target.hardware.source_controller_visibility_stages.execute")!=std::optional<double>{2} ||
      s_.number("target.hardware.source_controller_visibility_stages.store")!=std::optional<double>{1}))
     throw std::invalid_argument("registered controller visibility requires selected RS and queue-stage facts");
   if(const auto selected=s_.number("target.scheduling.source_reader_registered_path")){
     if(*selected!=1 || s_.number("parameters.memory.l2.hit_cycles")!=std::optional<double>{1})
       throw std::invalid_argument("registered reader requires selected scalar lookup contract");
     const std::map<std::string,double>required={
       {"reader_tracker_entries",16},{"reader_tracker_first_free",1},
       {"reader_translation_queue_stages",2},{"reader_translation_queue_entries",1},{"reader_translation_queue_pipe",1},{"reader_translation_queue_flow",0},
       {"reader_tl_buffer_stages",3},{"reader_tl_buffer_entries",2},{"reader_tl_buffer_pipe",0},{"reader_tl_buffer_flow",0},
       {"inclusive_hit_directory_stages",1},{"inclusive_hit_plan_stages",1},{"inclusive_hit_source_d_stages",2}};
     for(const auto&fact:required)if(s_.number("target.hardware."+fact.first)!=std::optional<double>{fact.second})
       throw std::invalid_argument("registered reader missing selected transport/cache stage facts");
     reader_request_path_=std::make_unique<PostedRegisteredTransport>(q_,std::vector<PostedRegisteredTransport::Spec>{{1,true},{1,true},{2,false},{2,false},{2,false}});
     reader_response_path_=std::make_unique<PostedRegisteredTransport>(q_,std::vector<PostedRegisteredTransport::Spec>{{2,false},{2,false},{2,false}});
     // Existing scalar cache lookup contributes one cycle. Directory result,
     // registered MSHR plan and SourceD s2/s3 contribute four total, including
     // that cycle. This is latency, not a four-cycle initiation interval.
     inclusive_pipeline_extension_=3;
     if(const auto owner=s_.number("target.scheduling.source_reader_memory_owned_cache_pipeline")){
       if(*owner!=1 || s_.number("memory.device_read_pipeline.enabled")!=std::optional<double>{1} ||
          s_.number("memory.device_read_pipeline.directory_stages")!=std::optional<double>{1} ||
          s_.number("memory.device_read_pipeline.mshr_plan_stages")!=std::optional<double>{1} ||
          s_.number("memory.device_read_pipeline.source_d_stages")!=std::optional<double>{2} ||
          s_.number("memory.device_read_pipeline.scalar_lookup_cycles")!=std::optional<double>{1})
         throw std::invalid_argument("reader requires selected native-owned cache stage composition");
       memory_owned_reader_pipeline_=true;inclusive_pipeline_extension_=0;
     }
   }
   if(const auto selected=s_.number("target.scheduling.source_aligned_i8_readout")){
     if(*selected!=1||!registered_visibility_||!memory_owned_reader_pipeline_||!config_.readout_stream||
        s_.number("target.hardware.normalizations")!=std::optional<double>{0}||
        s_.number("target.hardware.relu_same_accumulator_scale_pipeline")!=std::optional<double>{1}||
        s_.number("target.assumptions.accumulator_readout_translation_hits")!=std::optional<double>{1})
       throw std::invalid_argument("source aligned i8 readout requires selected passthrough/scale and translation contract");
     const auto &r=*config_.readout_stream;
     if(r.dispatch!=2||r.norm_metadata!=6||r.norm_passthrough!=2||r.scale_metadata!=6||r.issue_metadata!=5||r.scale_stages!=8||r.transactions!=16||r.beat_bytes!=16)
       throw std::invalid_argument("source aligned i8 readout queue geometry differs from selected source");
     shared_a_path_=std::make_unique<PostedRegisteredTransport>(q_,std::vector<PostedRegisteredTransport::Spec>{{2,false},{2,false}});
     shared_d_path_=std::make_unique<PostedRegisteredTransport>(q_,std::vector<PostedRegisteredTransport::Spec>{{2,false},{2,false}});
     reader_request_path_=std::make_unique<PostedRegisteredTransport>(q_,std::vector<PostedRegisteredTransport::Spec>{{1,true},{1,true},{2,false}});
     reader_response_path_=std::make_unique<PostedRegisteredTransport>(q_,std::vector<PostedRegisteredTransport::Spec>{{2,false}});
     readout_frontend_=std::make_unique<PostedReadoutFrontend>(q_,r);
     one_beat_writer_=std::make_unique<PostedOneBeatWriter>(q_,*shared_a_path_,*shared_d_path_);i8_readout_=true;
     s_.feature("target.posted.i8_full_readout_rows",0);
   }
   if(const auto selected=s_.number("target.scheduling.source_identity_i8_accumulator_load")){
     if(*selected!=1||!h.source_identity_i8_accumulator_load||!h.source_identity_ingress||
        s_.number("target.hardware.i8_acc_load_identity_scale")!=std::optional<double>{1}||
        s_.number("target.hardware.i8_acc_load_signed_extension")!=std::optional<double>{1}||
        s_.number("target.hardware.i8_acc_load_mask_byte_expansion")!=std::optional<double>{4}||
        s_.number("target.hardware.accumulator_two_port_storage")!=std::optional<double>{1}||
        config_.late_accumulator_write_pipeline!=std::optional<Cycle>{2})
       throw std::invalid_argument("identity i8 ACC load requires selected shared scaler and signed expansion/write2 facts");
     identity_i8_accumulator_load_=true;s_.feature("target.posted.identity_i8_accumulator_load_fragments",0);
   }
   if(const auto selected=s_.number("target.scheduling.source_full_accumulator_load")){
     if(*selected!=1||!h.source_full_accumulator_load||!reader_request_path_||!memory_owned_reader_pipeline_||
        s_.number("target.hardware.full_acc_load_separate_scaler")!=std::optional<double>{1}||
        s_.number("target.hardware.full_acc_load_scale_args_present")!=std::optional<double>{0}||
        s_.number("target.hardware.full_acc_load_input_queue_entries")!=std::optional<double>{2}||
        s_.number("target.hardware.full_acc_load_input_register_entries")!=std::optional<double>{1}||
        s_.number("target.hardware.full_acc_load_scale_pipeline_stages")!=std::optional<double>{0}||
        s_.number("target.hardware.accumulator_two_port_storage")!=std::optional<double>{1}||
        config_.late_accumulator_write_pipeline!=std::optional<Cycle>{2})
       throw std::invalid_argument("full ACC overwrite requires selected separate identity Queue2/register1, two-port write pipeline2");
     full_acc_load_path_=std::make_unique<PostedRegisteredTransport>(q_,std::vector<PostedRegisteredTransport::Spec>{{2,false},{1,true}});
     s_.feature("target.posted.full_accumulator_load_fragments",0);
   }
   if(const auto selected=s_.number("target.scheduling.source_masked_i8_readout")){
     if(*selected!=1||!h.source_masked_i8_readout||!i8_readout_||
        s_.number("target.hardware.source_d_client_beat_bytes")!=std::optional<double>{16}||
        s_.number("target.hardware.source_d_write_chunk_bytes")!=std::optional<double>{8}||
        s_.number("target.hardware.source_d_sram_read_stages")!=std::optional<double>{2}||
        s_.number("target.assumptions.source_d_no_external_banked_store_stalls")!=std::optional<double>{1})
       throw std::invalid_argument("masked i8 readout requires selected SourceD one-beat/8-byte SRAM chunks/read2 and no external port stall domain");
     source_d_=std::make_unique<PostedOneBeatSourceD>(q_,[this](bool read){s_.feature(read?
       "target.posted.masked_i8_sram_reads":"target.posted.masked_i8_sram_bypasses",1);});
     for(const auto*name:{"target.posted.masked_i8_rows","target.posted.masked_i8_sram_reads","target.posted.masked_i8_sram_bypasses","target.posted.masked_i8_storage_publications"})s_.feature(name,0);
   }
   if(const auto selected=s_.number("target.scheduling.source_masked_probe_sinkc")){
     if(*selected!=1||!source_d_||s_.number("target.hardware.source_d_banked_store_banks")!=std::optional<double>{8}||
        s_.number("target.hardware.sinkc_data_queue_stages")!=std::optional<double>{1}||
        s_.number("target.hardware.mshr_probe_response_register_stages")!=std::optional<double>{1})
       throw std::invalid_argument("masked probe handoff requires selected SinkC Queue1/MSHR register1/eight shared SRAM ports");
     for(unsigned bank=0;bank<8;++bank)cache_banks_.push_back(s_.resource("memory.l2.data.bank."+std::to_string(bank)));
     s_.feature("target.posted.masked_sinkc_beats",0);
   }
   if(const auto selected=s_.number("target.scheduling.source_full_raw_packet_readout")){
     if(*selected!=1||!source_d_||cache_banks_.size()!=8||!readout_frontend_||!shared_a_path_||!shared_d_path_||
        s_.number("target.hardware.source_sink_a_put_lists")!=std::optional<double>{40}||
        s_.number("target.hardware.source_sink_a_put_beats")!=std::optional<double>{40}||
        s_.number("target.hardware.source_full_raw_scale_pipeline")!=std::optional<double>{8})
       throw std::invalid_argument("full raw packet route requires selected SinkA40/40 and full-data scale pipeline8");
     full_packet_writer_=std::make_unique<PostedFullPacketWriter>(q_,*shared_a_path_,*shared_d_path_,40);
     full_packet_source_d_=std::make_unique<PostedFullPacketSourceD>(q_,source_d_pipeline_);
     s_.feature("target.posted.full_raw_write_packets",0);s_.feature("target.posted.full_raw_write_beats",0);
   }
   if(const auto selected=s_.number("target.scheduling.source_masked_packet_readout")){
     if(*selected!=1||!h_.source_masked_packet_readout||!full_packet_writer_||!full_packet_source_d_||cache_banks_.size()!=8)
       throw std::invalid_argument("masked packets require original shared writer/SourceD/BankedStore owners");
     masked_packets_=true;
   }
   if(const auto resident=s_.number("target.scheduling.source_resident_dirty_put_request_retirement")){
     if(*resident!=1||!source_d_pipeline_||!masked_packets_||
        s_.number("target.scheduling.source_cold_write_misses")!=std::optional<double>{1}||
        s_.number("target.hardware.mshr_resident_dirty_put_no_wait_at_source_d_request")!=std::optional<double>{1})
       throw std::invalid_argument("resident dirty Put retirement requires shared SourceD and selected no_wait law");
     resident_dirty_put_retirement_=true;
   }
   if(const auto selected=s_.number("target.scheduling.source_ordered_resident_dirty_put")){
     if(*selected!=1||!resident_dirty_put_retirement_||!source_d_pipeline_||!full_packet_source_d_||
        s_.number("target.hardware.source_d_s2_entries")!=std::optional<double>{1}||
        s_.number("target.hardware.source_d_s3_entries")!=std::optional<double>{1}||
        s_.number("target.hardware.source_d_s4_entries")!=std::optional<double>{1})
       throw std::invalid_argument("ordered dirty Put needs selected FIFO SourceD S2/S3/S4 and actual request capture retirement");
     ordered_dirty_puts_=true;
   }
   if(const auto selected=s_.number("target.scheduling.source_store_request_release")){
     if(*selected!=1||!masked_packets_||!full_packet_writer_||!readout_frontend_||
        s_.number("target.hardware.store_controller_last_request_releases_command")!=std::optional<double>{1}||
        s_.number("target.hardware.store_dma_tracker_entries")!=std::optional<double>{double(config_.dma_commands[1])})
       throw std::invalid_argument("store FIFO release requires selected final DMA handshake and unchanged tracker capacity");
     store_request_release_=true;
   }
   if(const auto selected=s_.number("target.scheduling.source_store_local_request_completion")){
     if(*selected!=1||!store_request_release_||
        s_.number("target.hardware.source_completion_priority_execute_load_store")!=std::optional<double>{1}||
        s_.number("target.hardware.store_dma_response_at_local_read_acceptance")!=std::optional<double>{1}||
        s_.number("target.hardware.store_dma_completion_register_stages")!=std::optional<double>{1}||
        s_.number("target.hardware.store_dma_credit_reuse_register_stages")!=std::optional<double>{1})
       throw std::invalid_argument("store local completion requires original local responses and registered tracker reuse");
     store_local_completion_=true;
   }
   if(const auto selected=s_.number("target.scheduling.source_cold_write_misses")){
     const auto sets=s_.number("memory.caches.l2.sets");
     if(*selected!=1||!source_d_||cache_banks_.size()!=8||
        s_.number("memory.device_write_miss_pipeline.enabled")!=std::optional<double>{1}||
        s_.number("memory.device_write_miss_pipeline.line_bytes")!=std::optional<double>{64}||
        s_.number("memory.device_write_miss_pipeline.outer_beat_bytes")!=std::optional<double>{8}||
        s_.number("memory.device_write_miss_pipeline.demand_mshrs")!=std::optional<double>{10}||
        !sets||*sets<1||*sets>1048576||std::floor(*sets)!=*sets)
       throw std::invalid_argument("cold write actors require exact selected LLC and demand-MSHR source contract");
     cold_cache_sets_=std::uint64_t(*sets);
     cache_ports_=std::make_unique<PostedBankedStore>(q_,8);
     if(s_.number("memory.device_write_miss_pipeline.private_victim.clients")==std::optional<double>{1})
       victim_probe_=std::make_unique<PostedVictimProbe>(q_,[this](auto,auto address,auto mask,auto at,auto stored){
         if(mask!=0xffff){fail("victim SinkC requires actual16-byte data");return;}victim_bank_write(address,at,stored);
       });
     cold_write_=std::make_unique<PostedColdWrite>(q_,
       [this](auto address,auto port,auto at,auto accepted){cold_cache_port(address,port,at,accepted);},
       [this](auto latency,auto bus,auto at,auto returned){cold_lower(latency,bus,at,returned);},
       [this](auto at,auto accepted){cold_outer_bus(at,accepted);});
   }
   if(const auto selected=s_.number("target.scheduling.source_ordered_pool_readout")){
     if(*selected!=1||!h.source_ordered_pool_readout||!readout_frontend_||!one_beat_writer_||
        !source_d_||!config_.readout_stream||
        s_.number("target.hardware.pool_writer_single_reduction_register")!=std::optional<double>{1}||
        s_.number("target.hardware.pool_writer_store_only_last_request")!=std::optional<double>{1}||
        s_.number("target.hardware.pool_garbage_metadata_bypass")!=std::optional<double>{1})
       throw std::invalid_argument("ordered pool requires original request/reduction/garbage path facts");
     ordered_pool_readout_=true;
     for(const auto*name:{"target.posted.pool_writer_captures","target.posted.pool_garbage_requests","target.posted.pool_acc_reads"})s_.feature(name,0);
   }
   if(h.dim!=16||h.element_bytes!=1||h.accumulator_bytes!=4||!h.source_identity_ingress||!config_.source_identity_ingress||!config_.scratchpad_bank_rows||
       config_.scratchpad_bank_resources.empty()||!config_.late_accumulator_write_pipeline)
     throw std::invalid_argument("posted source requires selected source-service WS storage facts");
 }
 Result submit(const std::string&kind,const Event&e,std::optional<Cycle> occupancy,std::uint32_t funct,std::uint64_t rs1,std::uint64_t rs2,
               const std::optional<TransferPhase>&phase,const std::vector<Transfer>&transfers,std::optional<merlin_timing::StageOrigin> origin={}){
   if(kind=="fence"){drain(e.earliest);return {now(),now(),now()};}
   if(kind!="config"&&kind!="flush"&&kind!="load"&&kind!="preload"&&kind!="compute_ws"&&!store_kind(kind)){
     fail("unsupported committed primitive "+kind);return {};
   }
   if(kind=="config"&&(rs1&3)==0){
     if(!(rs1&128))ws_unit_=bool(rs1&4)&&!(rs1&(3ull<<8));
     ws_unit_=ws_unit_&&((rs1>>16)&65535)==1&&((rs2>>48)&65535)==1;
   }
   if((kind=="preload"||kind=="compute_ws")&&!ws_unit_){fail("posted compute needs non-transposed unit-stride WS");return {};}
   const auto group=kind=="load"?0:store_kind(kind)?2:kind=="config"&&((rs1&3)==1)?0:kind=="config"&&((rs1&3)==2||(rs1&3)==3)?2:1;
   const auto before_rs=now(e.earliest);
   prune(group);while(active_[group].size()>=config_.reservations[group]&&!q_.progress().failed){
     if(!q_.step(true)){fail("reservation backpressure has no source completion");break;}prune(group);
   }
   if(q_.progress().failed)return {};
   if(now(e.earliest)>before_rs)s_.feature("target.posted.modeled_cpu_rs_wait_cycles",now(e.earliest)-before_rs);
   auto c=std::make_shared<Command>();c->kind=kind;c->funct=funct;c->rs1=rs1;c->rs2=rs2;c->phase=phase;c->transfers=transfers;c->group=group;c->occupancy=occupancy;
   c->start=token();c->consume=token();c->done=token();q_.track_source_completion(c->done);c->original.origin=std::move(origin);c->original.earliest=now(e.earliest);c->original.latency=e.latency;
   if(actor_sink_){const auto role=group==0?ActorRole::load_command:group==2?ActorRole::store_command:ActorRole::execute_command;
     actor(role,c->done.id,q_.now(),true);actor_done_[c->done.id]=role;
     actor(static_cast<ActorRole>(std::size_t(ActorRole::load_rs_wait)+(group==0?0:group==2?1:2)),c->start.id,q_.now(),true);}
   c->original.reads.assign(e.reads.data,e.reads.data+e.reads.size);c->original.writes.assign(e.writes.data,e.writes.data+e.writes.size);
   // PRELOAD owns D's SP consumption; an ordinary following MUL does not read
   // those previous D rows a second time. Derive actual A/B row addresses.
   auto reads=c->original.reads;
   if(kind=="preload"){
     for(std::uint64_t row=0;row<std::min<std::uint64_t>(h_.dim,rs1>>48)&&std::uint32_t(rs1)!=0xffffffffu;++row)c->sp_reads.push_back(base_+std::uint32_t(rs1)+row);
     // The semantic PRELOAD event publishes a descriptor, not its delayed D
     // consumption. Bind the actual source rows here so a pending LOAD cannot
     // be mistaken for ready(0), and a later overwrite retains this consumer.
     reads.insert(reads.end(),c->sp_reads.begin(),c->sp_reads.end());
   }
   else if(kind=="compute_ws"){
     for(auto packet:{rs1,rs2})if(std::uint32_t(packet)!=0xffffffffu)
       for(std::uint64_t row=0;row<std::min<std::uint64_t>(h_.dim,packet>>48);++row)c->sp_reads.push_back(base_+std::uint32_t(packet)+row);
     reads.erase(std::remove_if(reads.begin(),reads.end(),[&](auto row){return sp(row)&&!contains(c->sp_reads,row);}),reads.end());
   }
   for(auto row:reads)if(acc(row))c->acc_reads.push_back(row);
   for(auto row:c->original.writes)if(physical(row))c->outputs.push_back(row);
   if(accumulator_ports_&&kind=="compute_ws")for(auto row:c->outputs)c->row_ready.emplace(row,token());
   // Explicit pending row generations bind commands not yet published in
   // Engine; default ready(row)==0 can NEVER satisfy an outstanding LOAD.
   for(auto row:reads){
     auto &state=rows_[row];
     state.readers.erase(std::remove_if(state.readers.begin(),state.readers.end(),[this](auto t){return q_.completed(t).has_value();}),state.readers.end());const bool late=kind=="compute_ws"&&acc(row);
     auto &dependencies=late?(accumulator_ports_?c->row_dependencies[row]:c->output_dependencies):c->dependencies;
     if(state.writer)dependencies.push_back(*state.writer);
     // ACC RMW consumes the old value in the RESULT path, not the SP feed.
     state.readers.push_back(late?(accumulator_ports_?c->row_ready.at(row):c->done):physical(row)?c->consume:c->start);
   }
   for(auto row:c->original.writes){auto &state=rows_[row];
     // ReservationStation same-EX deps clear on ISSUE (scala463-476).
     // COMPUTE's old ACC value / WAW belongs to its late output actor. Keep
     // exact generations and all old readers there; never erase the hazard.
     auto &dependencies=(kind=="compute_ws"&&acc(row))?(accumulator_ports_?c->row_dependencies[row]:c->output_dependencies):c->dependencies;
     if(state.writer)dependencies.push_back(*state.writer);
     for(auto reader:state.readers)if(reader.id!=c->consume.id&&reader.id!=c->start.id&&reader.id!=c->done.id&&
       (!c->row_ready.count(row)||reader.id!=c->row_ready.at(row).id))dependencies.push_back(reader);
     state.readers.clear();
     if(kind=="load"&&physical(row)){auto published=token();c->row_ready.emplace(row,published);state.writer=published;}
     else state.writer=accumulator_ports_&&kind=="compute_ws"&&acc(row)?c->row_ready.at(row):physical(row)?c->done:c->start;}
   if(last_issue_[group])c->dependencies.push_back(*last_issue_[group]);
   last_issue_[group]=c->start;
   // This is a bound on LIVE custody, not total workload command count.
   // Completed actors remain owned by their callbacks/queues as necessary;
   // removing their drain-history references never completes a token early.
   if(commands_.size()>=4096)commands_.erase(std::remove_if(commands_.begin(),commands_.end(),
     [this](const auto&old){return old->finished||q_.completed(old->done).has_value();}),commands_.end());
   active_[group].push_back(c);commands_.push_back(c);
   if(commands_.size()>65536){fail("bounded committed command budget");return {};}
   request_issue(c,c->original.earliest);s_.feature("target.posted.accepted",1);
   return {now(e.earliest),now(e.earliest),now(e.earliest)};
 }
 void drain(Cycle at){
   const auto before=now(at);
   for(const auto &c:commands_)if(!c->finished)await(c->done);
   // Local RS completion never discards independent writer ACK/publication
   // custody. Finished command history may be pruned while these remain live.
   while(!pending_store_obligations_.empty()&&!q_.progress().failed){
     const auto obligation=pending_store_obligations_.begin()->second;await(obligation);
   }
   while(!ws_pending_rows_.empty()&&!q_.progress().failed){const auto pending=ws_pending_rows_.begin()->second;await(pending);ws_pending_rows_.erase(pending.id);}
   if(q_.progress().failed)s_.unresolved("posted_source:"+q_.reason());
   if(now(at)>before)s_.feature("target.posted.modeled_target_fence_wait_cycles",now(at)-before);
   s_.engine.advance_issue(now(at));
 }
 bool can_allocate(std::size_t group,Cycle at)const{
   if(group>=active_.size())return false;
   std::size_t live=0;
   for(const auto&c:active_[group]){
     auto released=q_.completed(c->done);
     if(c->kind=="compute_ws")if(auto consumed=q_.completed(c->consume))released=consumed;
     // Registered entry.valid does not release a FULL RS combinationally
     // on the same edge as its completion notification.
     if(!released||*released>=at)++live;
   }
   return live<config_.reservations[group];
 }
 const auto& coverage()const{return coverage_;}
 bool complete()const{return !q_.progress().failed;}
};
}
#endif
