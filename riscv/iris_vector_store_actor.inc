// Finite source-sequencer store actor. Source queue/CPU joining and effective
// ACK service remain explicit experimental boundaries, not whole-RTL timing.
struct iris_timing_adapter::VectorStoreCommand {
 unsigned hart;uint32_t raw;uint64_t serial,pc,base;Cycle COM;
 std::vector<iris_definedness::Value<uint32_t>> words;std::vector<iris_definedness::Value<uint64_t>> before;
 unsigned requests=0,total_requests=0,ACKs=0;bool reads_done=false,done=false;
 std::optional<uint64_t>cache_owner;
};
struct iris_timing_adapter::VectorStoreRuntime {
 struct Request{std::shared_ptr<VectorStoreCommand>command;unsigned tag,word_begin,words,beat=0;Cycle ready;};
 iris::rvv_store::Sequencer sequencer;iris::rvv_store::CompactorControl compactor;unsigned width,outer,capacity;
 bool scheduled=false;Cycle next_A=0,dispatch_at=0;
 std::shared_ptr<VectorStoreCommand>dispatch,current;
 std::deque<Request>requests,data_requests;std::set<unsigned>tags;
 explicit VectorStoreRuntime(unsigned h):sequencer(h<2?iris::rvv_store::Profile::Compute128:iris::rvv_store::Profile::Rocket256),compactor(h<2?16:32),width(h<2?16:32),outer(h<2?32:8),capacity(h<2?16:32){iris::rvv_store::Inputs i{true,false,{},true,true,0,0,true};sequencer.evaluate(i);sequencer.commit();compactor.evaluate({true,false,width,false,width,true});compactor.commit();}
};
bool iris_timing_adapter::vector_store_pending(unsigned hart)const{for(const auto&c:vector_store_commands_)if(c->hart==hart&&!c->done)return true;return false;}
void iris_timing_adapter::vector_store_check_environment()const{
 bool any=false;for(const auto&c:vector_store_commands_)any|=!c->done;if(!any)return;
 const auto h=profile_.vector_store_hart;
 if(cores_[h]->get_state()->mstatus->read()&MSTATUS_MIE)throw std::runtime_error("IRIS_VSE_ACTOR_GLOBAL_IRQ_ENABLE_UNSUPPORTED");
 for(unsigned p=0;p<cores_.size();++p){const auto*s=cores_[p]->get_state();if(s->mip->read()&s->mie->read())throw std::runtime_error("IRIS_VSE_ACTOR_PENDING_INTERRUPT_UNSUPPORTED");if(p!=h&&!cores_[p]->is_waiting_for_interrupt())throw std::runtime_error("IRIS_VSE_ACTOR_PEER_NOT_QUIET");}
}
bool iris_timing_adapter::vector_store_cpu_allowed(unsigned hart,const insn_fetch_t&fetch)const{
 if(!vector_store_pending(hart))return true;
 auto insn=fetch.insn;const uint32_t raw=insn.length()==2?iris::frontend::expand_source_rvc(uint16_t(insn.bits())):uint32_t(insn.bits());const auto op=raw&127;
 const bool vector=(op==0x57)||(op==0x27&&(((raw>>12)&7)==0||((raw>>12)&7)>=5));
 bool lease=false;for(const auto&c:vector_store_commands_)if(c->hart==hart&&!c->reads_done)lease=true;
 if(vector){
  if(lease)return false;
  if(op==0x27){const auto v=cores_[hart]->get_state()->XPR.read_transport((raw>>15)&31);if(!std::all_of(v.known.begin(),v.known.end(),[](uint8_t b){return b==255;}))return false;
   const uint64_t base=v.value,bytes=cores_[hart]->VU.vl->read()*4;
   for(const auto&c:vector_store_commands_)if(c->hart==hart&&!c->done&&((base>>6)<=((c->base+c->words.size()*4-1)>>6))&&((c->base>>6)<=((base+bytes-1)>>6)))return false;
  }
  return true;
 }
 if(op==0x03||op==0x23||op==0x2f||op==0x07||op==0x27||op==0x0f||op==0x53||op==0x43||op==0x47||op==0x4b||op==0x4f)return false;
 if(op==0x73){const auto csr=raw>>20,f=(raw>>12)&7;return((raw>>15)&31)==0&&(f==2||f==3||f==6||f==7)&&(csr==0xb00||csr==0xb02||csr==0xc00||csr==0xc02||csr==0xf14);}
 return true; // Scalar ALU/branches may retire; all memory and state CSR paths drain.
}
void iris_timing_adapter::vector_store_start(unsigned hart,uint32_t raw,reg_t base,const std::vector<iris_definedness::Value<uint32_t>>&words){
 if(hart!=profile_.vector_store_hart)throw std::runtime_error("IRIS_VSE_ACTOR_ACTIVE_HART_REFUSED");
 auto&runtime=vector_store_runtime_[hart];if(!runtime)runtime=std::make_shared<VectorStoreRuntime>(hart);
 if(base%runtime->width)throw std::runtime_error("IRIS_VSE_ACTOR_SOURCE_REQUEST_ALIGNMENT_REFUSED");
 if(runtime->dispatch||runtime->current)throw std::runtime_error("IRIS_VSE_ACTOR_VRF_LEASE_OVERLAP");
 auto c=std::make_shared<VectorStoreCommand>();c->hart=hart;c->raw=raw;c->serial=++vector_store_serial_;c->pc=pending_[hart]->pc;c->base=base;c->COM=clock_.now();c->words=words;c->total_requests=(words.size()*4+runtime->width-1)/runtime->width;for(unsigned i=0;i<words.size();++i)c->before.push_back(cores_[hart]->iris_frontend_read_beat((base+4*i)&~7ULL));c->cache_owner=pending_[hart]->cache_owner;pending_[hart]->cache_owner.reset();
 vector_store_commands_.erase(std::remove_if(vector_store_commands_.begin(),vector_store_commands_.end(),[](const auto&x){return x->done;}),vector_store_commands_.end());vector_store_commands_.push_back(c);
 vector_store_check_environment();runtime->dispatch=c;runtime->dispatch_at=clock_.now()+(profile_.vector_store_read-1)*profile_.harts[hart].divider;
 if(async_trace_)*async_trace_<<"{\"event\":\"VSE_actor_front_COM\",\"hart\":"<<hart<<",\"command\":"<<c->serial<<",\"pc\":"<<c->pc<<",\"cycle\":"<<clock_.now()<<",\"bytes\":"<<words.size()*4<<",\"RAM_published\":false}\n";
 vector_store_schedule(hart);
}
void iris_timing_adapter::vector_store_schedule(unsigned hart){
 auto r=vector_store_runtime_[hart];if(!r||r->scheduled)return;
 if(!r->dispatch&&!r->current&&r->requests.empty()&&r->data_requests.empty()&&(!profile_.vector_store_compactor||r->compactor.idle()))return;
 r->scheduled=true;const auto d=profile_.harts[hart].divider;
 iris::Op tick{hart,"experimental.VSE.source-controller-edge","experimental.VSE.controller"+std::to_string(hart),d,1};tick.retires=false;tick.issue_period=d;tick.on_complete=[this,hart]{auto r=vector_store_runtime_[hart];r->scheduled=false;vector_store_tick(hart);vector_store_schedule(hart);};clock_.issue(std::move(tick));
}
void iris_timing_adapter::vector_store_tick(unsigned hart){
 if(profile_.vector_store_compactor){vector_store_tick_compactor(hart);return;}
 auto r=vector_store_runtime_[hart];const auto now=clock_.now(),divider=profile_.harts[hart].divider;
 vector_store_check_environment();
 if(!r->requests.empty()&&r->requests.front().ready<=now&&r->next_A<=now){
  auto req=r->requests.front();++vector_store_A_beats_;r->next_A=now+profile_.vector_store_A_period*divider;
  const auto total=(r->width+r->outer-1)/r->outer;
  if(async_trace_)*async_trace_<<"{\"event\":\"VSE_actor_A_beat\",\"hart\":"<<hart<<",\"command\":"<<req.command->serial<<",\"tag\":"<<req.tag<<",\"beat\":"<<req.beat<<",\"cycle\":"<<now<<",\"message_payload_bytes\":"<<req.words*4<<",\"beat_payload_bytes\":"<<std::min(r->outer,req.words*4>req.beat*r->outer?req.words*4-req.beat*r->outer:0u)<<",\"physical_slot_bytes\":"<<r->outer<<"}\n";
  if(++r->requests.front().beat==total){
   r->requests.pop_front();auto c=req.command;
   iris::Op ack{hart,"experimental.VSE.matching-ACK","experimental.VSE.ACK"+std::to_string(hart),profile_.vector_store_ack*divider,1};ack.retires=false;ack.issue_period=divider;ack.pc=c->pc;ack.bytes=req.words*4;
   ack.on_complete=[this,hart,req,c]{auto r=vector_store_runtime_[hart];if(c->done||!r->tags.erase(req.tag))throw std::runtime_error("IRIS_VSE_ACTOR_ACK_OWNER_LOST");vector_store_check_environment();
    for(unsigned i=0;i<req.words;++i){const unsigned wi=req.word_begin+i;const auto before=cores_[hart]->iris_frontend_read_beat((c->base+4*wi)&~7ULL);const unsigned shift=((c->base+4*wi)&7)*8;
     // Neighbor words in this same beat may have received an EARLIER ACK;
     // qualify only this request-owned word and its known-mask bytes.
     const auto&saved=c->before[wi];if(uint32_t(before.value>>shift)!=uint32_t(saved.value>>shift)||!std::equal(before.known.begin()+shift/8,before.known.begin()+shift/8+4,saved.known.begin()+shift/8))throw std::runtime_error("IRIS_VSE_ACTOR_RAM_CHANGED_BEFORE_MATCHING_ACK");
     cores_[hart]->get_mmu()->store_transport<uint32_t>(c->base+4*wi,c->words[wi]);
    }
    ++vector_store_ACKs_;++c->ACKs;
    if(async_trace_)*async_trace_<<"{\"event\":\"VSE_actor_ACK_publish\",\"hart\":"<<hart<<",\"command\":"<<c->serial<<",\"tag\":"<<req.tag<<",\"cycle\":"<<clock_.now()<<",\"bytes\":"<<req.words*4<<",\"RAM_unchanged_before_ACK\":true}\n";
    if(c->reads_done&&c->ACKs==c->requests&&c->requests==c->total_requests){c->done=true;if(c->cache_owner){empirical_cache_->complete(*c->cache_owner,clock_.now(),true);cache_nodes_.erase(*c->cache_owner);c->cache_owner.reset();}}
    vector_store_schedule(hart);
   };clock_.issue(std::move(ack));
  }
 }
 iris::rvv_store::Inputs in{false,bool(r->dispatch&&now>=r->dispatch_at),{},r->tags.size()<r->capacity,true,0,0,true};
 if(in.dispatch_valid){auto c=r->dispatch;const auto lmul=unsigned(cores_[hart]->VU.vflmul);unsigned emul=0;while((1u<<emul)<lmul)++emul;in.dispatch=iris::rvv_store::Command{c->raw,unsigned(c->words.size()),0,emul,0,unsigned(c->serial&65535),2,0,c->serial};}
 r->sequencer.evaluate(in);const auto out=r->sequencer.sample();
 if(out.data_fire){if(!r->current||!out.payload)throw std::runtime_error("IRIS_VSE_ACTOR_MICROISSUE_OWNER_LOST");auto c=r->current;const auto&p=*out.payload;unsigned tag=0;while(r->tags.count(tag))++tag;if(tag>=r->capacity)throw std::runtime_error("IRIS_VSE_ACTOR_SOURCE_TAG_CAPACITY");r->tags.insert(tag);
  const unsigned begin=p.eidx,count=std::min<unsigned>(r->width/4,c->words.size()-begin);r->requests.push_back({c,tag,begin,count,0,now+2*divider});++c->requests;++vector_store_requests_;
  if(async_trace_)*async_trace_<<"{\"event\":\"VSE_actor_VRF_read\",\"hart\":"<<hart<<",\"command\":"<<c->serial<<",\"cycle\":"<<now<<",\"eg\":"<<p.eg<<",\"read_intent\":"<<p.read_intent<<",\"bytes\":"<<count*4<<"}\n";
  if(p.tail){c->reads_done=true;r->current.reset();if(c->ACKs==c->requests&&c->requests==c->total_requests){c->done=true;if(c->cache_owner){empirical_cache_->complete(*c->cache_owner,clock_.now(),true);cache_nodes_.erase(*c->cache_owner);c->cache_owner.reset();}}}
 }
 if(out.dispatch_fire){r->current=r->dispatch;r->dispatch.reset();}
 r->sequencer.commit();
}
void iris_timing_adapter::vector_store_write_totals(std::ostream&out)const{
 if(!profile_.empirical_vector_store_actor)return;unsigned pending=0,leases=0;for(const auto&c:vector_store_commands_){pending+=!c->done;leases+=!c->reads_done;}
 out<<",\"finite_vector_store_actor\":{\"enabled\":true,\"active_hart\":"<<profile_.vector_store_hart<<",\"pending_commands\":"<<pending<<",\"VRF_leases\":"<<leases<<",\"TL_requests\":"<<vector_store_requests_<<",\"physical_A_beats\":"<<vector_store_A_beats_<<",\"matching_ACKs\":"<<vector_store_ACKs_<<",\"front_core_edges\":"<<profile_.vector_store_front<<",\"first_read_after_COM_core_edges\":"<<profile_.vector_store_read<<",\"external_ACK_core_edges\":"<<profile_.vector_store_ack<<",\"external_A_period_core_edges\":"<<profile_.vector_store_A_period<<",\"source_compactor_control\":"<<(profile_.vector_store_compactor?"true":"false")<<",\"CPU_VU_join_qualified\":false,\"physical_memory_latency_calibrated\":false,\"scope\":\"Mbare unmasked nf1 alignedVSE32<=256B; oneactivehart/quietpeers/noIRQ; sourceStoreSequencer, conservativewholeVRFlease; originalhandlerCOMquarantine; noncancellabletypedpublicationatmatchingexplicitserviceACK; ordinarymemory/CSR/FENCEdrain\"}";
}

void iris_timing_adapter::vector_store_tick_compactor(unsigned hart){
 auto r=vector_store_runtime_[hart];const auto now=clock_.now(),divider=profile_.harts[hart].divider;vector_store_check_environment();
 if(!r->requests.empty()&&r->requests.front().ready<=now&&r->next_A<=now){
  auto req=r->requests.front();++vector_store_A_beats_;r->next_A=now+profile_.vector_store_A_period*divider;
  const auto total=(r->width+r->outer-1)/r->outer;
  if(async_trace_)*async_trace_<<"{\"event\":\"VSE_actor_A_beat\",\"hart\":"<<hart<<",\"command\":"<<req.command->serial<<",\"tag\":"<<req.tag<<",\"beat\":"<<req.beat<<",\"cycle\":"<<now<<",\"message_payload_bytes\":"<<req.words*4<<",\"beat_payload_bytes\":"<<std::min(r->outer,req.words*4>req.beat*r->outer?req.words*4-req.beat*r->outer:0u)<<",\"physical_slot_bytes\":"<<r->outer<<"}\n";
  if(++r->requests.front().beat==total){
   r->requests.pop_front();auto c=req.command;
   iris::Op ack{hart,"experimental.VSE.matching-ACK","experimental.VSE.ACK"+std::to_string(hart),profile_.vector_store_ack*divider,1};ack.retires=false;ack.issue_period=divider;ack.pc=c->pc;ack.bytes=req.words*4;
   ack.on_complete=[this,hart,req,c]{auto r=vector_store_runtime_[hart];if(c->done||!r->tags.erase(req.tag))throw std::runtime_error("IRIS_VSE_ACTOR_ACK_OWNER_LOST");vector_store_check_environment();
    for(unsigned i=0;i<req.words;++i){const unsigned wi=req.word_begin+i;const auto before=cores_[hart]->iris_frontend_read_beat((c->base+4*wi)&~7ULL);const unsigned shift=((c->base+4*wi)&7)*8;
     // Neighbor words in this same beat may have received an EARLIER ACK;
     // qualify only this request-owned word and its known-mask bytes.
     const auto&saved=c->before[wi];if(uint32_t(before.value>>shift)!=uint32_t(saved.value>>shift)||!std::equal(before.known.begin()+shift/8,before.known.begin()+shift/8+4,saved.known.begin()+shift/8))throw std::runtime_error("IRIS_VSE_ACTOR_RAM_CHANGED_BEFORE_MATCHING_ACK");
     cores_[hart]->get_mmu()->store_transport<uint32_t>(c->base+4*wi,c->words[wi]);
    }
    ++vector_store_ACKs_;++c->ACKs;
    if(async_trace_)*async_trace_<<"{\"event\":\"VSE_actor_ACK_publish\",\"hart\":"<<hart<<",\"command\":"<<c->serial<<",\"tag\":"<<req.tag<<",\"cycle\":"<<clock_.now()<<",\"bytes\":"<<req.words*4<<",\"RAM_unchanged_before_ACK\":true}\n";
    if(c->reads_done&&c->ACKs==c->requests&&c->requests==c->total_requests){c->done=true;if(c->cache_owner){empirical_cache_->complete(*c->cache_owner,clock_.now(),true);cache_nodes_.erase(*c->cache_owner);c->cache_owner.reset();}}
    vector_store_schedule(hart);
   };clock_.issue(std::move(ack));
  }
 }

 const bool can_pop=!r->data_requests.empty()&&r->requests.empty()&&r->tags.size()<r->capacity;
 const unsigned pop_bytes=r->data_requests.empty()?r->width:r->data_requests.front().words*4;
 iris::rvv_store::CompactorControl::Inputs ci{false,false,r->width,can_pop,pop_bytes,true};r->compactor.evaluate(ci);const auto ready=r->compactor.sample().push_ready;
 iris::rvv_store::Inputs in{false,bool(r->dispatch&&now>=r->dispatch_at),{},ready,true,0,0,true};
 if(in.dispatch_valid){auto c=r->dispatch;const auto lmul=unsigned(cores_[hart]->VU.vflmul);unsigned emul=0;while((1u<<emul)<lmul)++emul;in.dispatch=iris::rvv_store::Command{c->raw,unsigned(c->words.size()),0,emul,0,unsigned(c->serial&65535),2,0,c->serial};}
 r->sequencer.evaluate(in);const auto out=r->sequencer.sample();ci.push_valid=out.data_valid;
 if(out.payload){const auto begin=out.payload->eidx;ci.push_bytes=std::min<unsigned>(r->width/4,r->current->words.size()-begin)*4;}
 r->compactor.evaluate(ci);const auto co=r->compactor.sample();if(co.push_fire!=out.data_fire)throw std::logic_error("IRIS_VSE_COMPACTOR_PUSH_SOURCE_HANDSHAKE_MISMATCH");
 if(co.pop_fire){auto req=r->data_requests.front();r->data_requests.pop_front();unsigned tag=0;while(r->tags.count(tag))++tag;if(tag>=r->capacity)throw std::logic_error("IRIS_VSE_COMPACTOR_TAG_CAPACITY");r->tags.insert(tag);req.tag=tag;req.ready=now+divider;r->requests.push_back(req);++req.command->requests;++vector_store_requests_;
  if(async_trace_)*async_trace_<<"{\"event\":\"VSE_actor_inner_A_accept\",\"hart\":"<<hart<<",\"command\":"<<req.command->serial<<",\"tag\":"<<tag<<",\"cycle\":"<<now<<",\"bytes\":"<<req.words*4<<"}\n";
 }
 if(out.data_fire){if(!r->current||!out.payload)throw std::logic_error("IRIS_VSE_COMPACTOR_READ_OWNER");auto c=r->current;const auto&p=*out.payload;const unsigned begin=p.eidx,count=std::min<unsigned>(r->width/4,c->words.size()-begin);r->data_requests.push_back({c,0,begin,count,0,0});
  if(async_trace_)*async_trace_<<"{\"event\":\"VSE_actor_VRF_read\",\"hart\":"<<hart<<",\"command\":"<<c->serial<<",\"cycle\":"<<now<<",\"eg\":"<<p.eg<<",\"read_intent\":"<<p.read_intent<<",\"bytes\":"<<count*4<<"}\n";
  if(p.tail){c->reads_done=true;r->current.reset();}
 }
 if(out.dispatch_fire){r->current=r->dispatch;r->dispatch.reset();}
 r->sequencer.commit();r->compactor.commit();unsigned logical=0;for(const auto&req:r->data_requests)logical+=req.words*4;if(logical!=r->compactor.buffered_bytes())throw std::logic_error("IRIS_VSE_COMPACTOR_TYPED_BYTE_LEDGER_MISMATCH");
}
