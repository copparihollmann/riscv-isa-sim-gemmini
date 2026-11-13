// Actual saved TLSplitInterface -> TLWidthWidget16 -> Saturn TLBuffer.
// The external A-ready/D producer is an explicit directed TEST fixture only.
// This file supplies neither the VMU/SAS/SSS nor System/coherent arena history.
#include "saturn_storefront_v1.hpp"
struct iris_timing_adapter::VseSourceRuntime {
 struct Return {iris::saturn_storefront::Receipt A;Cycle due;};
 iris::saturn_storefront::Model model;
 std::vector<iris::saturn_storefront::Input>inputs;
 std::vector<Return>returns;std::optional<Return>held_D;
 Cycle next_edge=0;unsigned reset_remaining=2;bool scheduled=false;
 uint64_t actual_A=0,actual_D=0,VMU_requests=0,VMU_responses=0,idle_edges=0,busy_false_with_owned=0;
 VseSourceRuntime(unsigned h,unsigned seed,Cycle first):model(h,seed,{}, {2,0},{{0x80000000ULL,0x100000000ULL}}),next_edge(first){
  for(const auto&field:model.input_fields())inputs.push_back(iris::saturn_storefront::concrete(field.width));
 }
 void set(const char*name,uint64_t value){inputs.at(model.input_index(name)).value.limbs[0]=value;}
 uint64_t get(const iris::saturn_storefront::Outputs&o,const char*name)const{return o.words.at(model.output_index(name)).limbs[0];}
};
bool iris_timing_adapter::vse_source_transport_drained(unsigned h)const{
 const auto&r=vse_source_runtime_[h];return r&&r->model.drained()&&r->returns.empty()&&!r->held_D;
}
void iris_timing_adapter::vse_source_schedule(unsigned h){
 auto c=vse_boundary_commands_[h];if(!c)return;auto&r=vse_source_runtime_[h];
 if(!r)r=std::make_shared<VseSourceRuntime>(h,unsigned(seed_.value_or(0)),clock_.now()+profile_.harts[h].divider);
 if(r->scheduled)return;
 if(r->next_edge!=clock_.now()+profile_.harts[h].divider)throw std::logic_error("IRIS_VSE_SOURCE_NEXT_EDGE_NOT_CONTIGUOUS");
 r->scheduled=true;const auto d=profile_.harts[h].divider;
 iris::Op op{h,"source.Storefront.edge-with-synthetic-external-D","test.VSE.tick"+std::to_string(h),d,1};op.retires=false;op.issue_period=d;op.pc=c->owner.pc;
 op.on_complete=[this,h]{auto r=vse_source_runtime_[h];r->scheduled=false;if(r->next_edge!=clock_.now())throw std::logic_error("IRIS_VSE_SOURCE_CALLBACK_EDGE_CHANGED");vse_source_step(h,clock_.now(),false);if(vse_boundary_live(h))vse_source_schedule(h);};clock_.issue(std::move(op));
}
void iris_timing_adapter::vse_source_idle_advance(Cycle now){
 if(!profile_.vse_source_storefront)return;
 for(unsigned h=0;h<2;++h){auto r=vse_source_runtime_[h];if(!r||vse_boundary_live(h))continue;
  if(!vse_source_transport_drained(h)||r->scheduled)throw std::logic_error("IRIS_VSE_SOURCE_IDLE_WITH_ACCEPTED_OWNER");
  const auto d=profile_.harts[h].divider;
  if(r->next_edge<=now&&(now-r->next_edge)/d>2000000)throw std::runtime_error("IRIS_VSE_SOURCE_TEST_IDLE_EDGE_BUDGET_EXCEEDED");
  // Evaluate every actual idle source edge. No PRNG/control transition is
  // elided, no source time or CPU counter is fabricated, and no owner exists.
  while(r->next_edge<=now)vse_source_step(h,r->next_edge,true);
 }
}
void iris_timing_adapter::vse_source_step(unsigned h,Cycle edge,bool idle){
 namespace sf=iris::saturn_storefront;
 auto r=vse_source_runtime_[h];auto c=vse_boundary_commands_[h];auto&ledger=vse_boundary_ledgers_[h];
 if(!r||edge!=r->next_edge||edge%profile_.harts[h].divider)throw std::logic_error("IRIS_VSE_SOURCE_STALE_EDGE");
 if(idle&&(c||!r->model.drained()||!ledger.empty()))throw std::logic_error("IRIS_VSE_SOURCE_FALSE_IDLE");
 for(auto&in:r->inputs)in.value={};
 const bool reset=r->reset_remaining!=0;r->set("reset",reset);r->set("auto_atl_out_a_ready",1);
 std::optional<sf::Owner>store_owner;std::optional<iris::vse_boundary::Request>offer;
 if(!reset&&!idle){
  offer=ledger.request();
  if(offer){const auto&q=*offer;r->set("io_vec_store_req_valid",1);r->set("io_vec_store_req_bits_addr",q.address);r->set("io_vec_store_req_bits_tag",q.token.tag);r->set("io_vec_store_req_bits_mask",q.mask);
   auto&data=r->inputs.at(r->model.input_index("io_vec_store_req_bits_data"));
   for(unsigned i=0;i<16;++i){data.value.limbs[i/8]|=uint64_t(q.data[i])<<(8*(i%8));const auto mask=uint64_t(255)<<(8*(i%8));data.known.limbs[i/8]=(data.known.limbs[i/8]&~mask)|(uint64_t(q.known[i])<<(8*(i%8)));}
   store_owner=sf::Owner{h,q.token.tag,r->model.reset_epoch(),q.owner.command,q.token.generation,q.owner.pc,q.owner.raw};
  }
  if(!r->held_D){auto it=std::min_element(r->returns.begin(),r->returns.end(),[](const auto&a,const auto&b){return a.due<b.due;});if(it!=r->returns.end()&&it->due<=edge){r->held_D=*it;r->returns.erase(it);}}
  if(r->held_D){r->set("auto_atl_out_d_valid",1);r->set("auto_atl_out_d_bits_opcode",0);r->set("auto_atl_out_d_bits_size",4);r->set("auto_atl_out_d_bits_source",r->held_D->A.source);}
 }
 const auto preedge_owned=r->model.owned_requests();
 r->model.evaluate_control(r->inputs,{},store_owner);const auto output=r->model.sample();
 if(!reset&&!output.protocol_qualified)throw std::logic_error("IRIS_VSE_SOURCE_UNQUALIFIED_TRANSPORT_PHASE");
 if(!reset&&preedge_owned&&!r->get(output,"io_mem_busy"))++r->busy_false_with_owned;
 r->model.prepare(2*edge);r->model.commit();++r->next_edge;
 if(reset)--r->reset_remaining;
 if(idle)++r->idle_edges;
 const auto receipts=r->model.last_receipts();
 if(idle&&!receipts.empty())throw std::logic_error("IRIS_VSE_SOURCE_IDLE_EMITTED_OWNERSHIP_EVENT");
 for(const auto&e:receipts){
  if(!c||e.load||e.owner.hart!=h||e.owner.command!=c->owner.command||e.owner.pc!=c->owner.pc||e.owner.raw!=c->owner.raw||e.owner.epoch!=1)
   throw std::logic_error("IRIS_VSE_SOURCE_RECEIPT_ARCHITECTURAL_OWNER_MISMATCH");
  const char*name="unknown";
  switch(e.phase){
   case sf::Phase::VMURequest:
    if(!offer||offer->token.tag!=e.owner.tag||offer->token.generation!=e.owner.generation)throw std::logic_error("IRIS_VSE_SOURCE_REQUEST_OFFER_IDENTITY_LOST");
    ledger.accepted({e.owner.tag,e.owner.generation});++vse_boundary_requests_total_;++r->VMU_requests;name="VMU_request_fire";break;
   case sf::Phase::TileA:
    r->returns.push_back({e,edge+profile_.vse_boundary_ack+((e.owner.tag&1)?0:3)});++r->actual_A;name="ATL_A_fire";break;
   case sf::Phase::TileD:
    if(!r->held_D||r->held_D->A.owner!=e.owner||r->held_D->A.source!=e.source)throw std::logic_error("IRIS_VSE_SOURCE_D_TEST_SINK_OWNER_LOST");
    r->held_D.reset();++r->actual_D;name="ATL_D_fire";break;
   case sf::Phase::VMUResponse:
    ++r->VMU_responses;name="VMU_matching_response";break;
  }
  if(async_trace_)*async_trace_<<"{\"event\":\"VSE_source_storefront_"<<name<<"\",\"hart\":"<<h<<",\"command\":"<<e.owner.command<<",\"tag\":"<<e.owner.tag<<",\"generation\":"<<e.owner.generation<<",\"epoch\":"<<e.owner.epoch<<",\"pc\":"<<e.owner.pc<<",\"raw\":"<<e.owner.raw<<",\"cycle\":"<<edge<<",\"source_edge\":"<<e.source_edge<<",\"master_tick\":"<<e.master_tick<<",\"TL_source\":"<<e.source<<",\"address\":"<<e.address<<",\"mask16\":"<<e.mask<<",\"external_D_synthetic_test_only\":true,\"VMU_sequencer_or_CPU_phase_qualified\":false}\n";
  if(e.phase==sf::Phase::VMUResponse)vse_boundary_ack(h,c,e.owner.tag,e.owner.generation);
 }
 // Actual source ACK/ROB release belongs to its preedge at E.  This first
 // conservative CPU bridge stays blocked through E; it is released at E+1.
 if(!reset&&!idle&&c->source_CPU_release&&edge>=c->source_CPU_release){
  if(edge!=c->source_CPU_release||!vse_source_transport_drained(h)||!ledger.empty())throw std::logic_error("IRIS_VSE_SOURCE_CPU_RELEASE_PHASE_OR_OWNER");
  if(c->cache_owner){empirical_cache_->complete(*c->cache_owner,edge,true);cache_nodes_.erase(*c->cache_owner);c->cache_owner.reset();}
  if(async_trace_)*async_trace_<<"{\"event\":\"VSE_source_conservative_CPU_release\",\"hart\":"<<h<<",\"command\":"<<c->owner.command<<",\"cycle\":"<<edge<<",\"source_Core_join_qualified\":false}\n";
  vse_boundary_commands_[h].reset();++vse_boundary_completed_total_;
 }
 if(!reset&&!idle&&vse_boundary_live(h)&&c->next_word<c->words.size()&&ledger.reserve_ready()){
  auto&v=cores_[h]->VU;if(std::memcmp(v.reg_file,c->physical_vrf.data(),c->physical_vrf.size())||v.iris_vrf_definedness.read(0,c->physical_vrf.size())!=c->physical_known)throw std::logic_error("IRIS_VSE_SOURCE_VRF_VALUE_KNOWN_LEASE_CHANGED");
  iris::vse_boundary::Request q;q.owner=c->owner;q.first_word=c->next_word;q.words=std::min<unsigned>(4,c->words.size()-c->next_word);q.address=c->base+4*c->next_word;q.last=c->next_word+q.words==c->words.size();q.mask=uint16_t((uint32_t(1)<<(4*q.words))-1);
  for(unsigned i=0;i<q.words;++i)for(unsigned b=0;b<4;++b){q.data[4*i+b]=uint8_t(c->words[q.first_word+i].value>>(8*b));q.known[4*i+b]=c->words[q.first_word+i].known[b];}
  q=ledger.reserve(q);c->next_word+=q.words;
  if(async_trace_)*async_trace_<<"{\"event\":\"VSE_source_upstream_ROB_reserve\",\"hart\":"<<h<<",\"command\":"<<c->owner.command<<",\"tag\":"<<q.token.tag<<",\"generation\":"<<q.token.generation<<",\"cycle\":"<<edge<<",\"words\":"<<q.words<<",\"first_word\":"<<q.first_word<<",\"last\":"<<(q.last?"true":"false")<<",\"VMU_address_or_data_sequence_phase_qualified\":false}\n";
 }
}
void iris_timing_adapter::vse_source_totals(std::ostream&out)const{
 if(!profile_.vse_source_storefront)return;const auto h=profile_.vse_boundary_hart;auto r=vse_source_runtime_[h];
 out<<",\"VSE_source_storefront\":{\"enabled\":true,\"external_D_synthetic_test_only\":true,\"System_backend_available\":false,\"source_transport_identity\":\""<<iris::saturn_storefront::Model::raw_source_identity()<<"\",\"h\":"<<h<<",\"source_edges\":"<<(r?r->model.committed_source_edges():0)<<",\"idle_source_edges_evaluated\":"<<(r?r->idle_edges:0)<<",\"actual_VMU_requests\":"<<(r?r->VMU_requests:0)<<",\"actual_ATL_A\":"<<(r?r->actual_A:0)<<",\"actual_ATL_D\":"<<(r?r->actual_D:0)<<",\"actual_VMU_responses\":"<<(r?r->VMU_responses:0)<<",\"raw_busy_false_with_live_owners\":"<<(r?r->busy_false_with_owned:0)<<",\"owned_transport\":"<<(r?r->model.owned_requests():0)<<",\"drained\":"<<(r&&vse_source_transport_drained(h)?"true":"false")<<",\"CPU_VMU_timing_qualified\":false,\"physical_memory_latency_qualified\":false}";
}
