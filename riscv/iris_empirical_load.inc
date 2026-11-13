namespace {thread_local iris_timing_adapter*empirical_load_owner=nullptr;
template<typename T>iris_definedness::Value<reg_t>empirical_read(processor_t*p,uint64_t address){return iris_definedness::extend_integer<reg_t>(p->get_mmu()->load_transport<T>(address));}}
bool iris_timing_adapter::empirical_load_candidate(unsigned hart,const iris::shuttle::Uop&u)const{
 if(!profile_.empirical_load_front||(u.expanded&127)!=3||((u.expanded>>12)&7)>6||!u.has(iris::shuttle::MEM))return false;
 const auto*s=cores_[hart]->get_state();if(s->prv!=PRV_M||s->v||(s->mstatus->read()&MSTATUS_MPRV))return false;
 const auto&p=pure_[hart];auto base=p.engaged&&p.values?p.values->peek(u.rs1):std::optional<uint64_t>{};
 if(!p.engaged){const auto v=s->XPR.read_transport(u.rs1);if(std::all_of(v.known.begin(),v.known.end(),[](uint8_t x){return x==255;}))base=v.value;}
 if(!base)return false;insn_t instruction(u.expanded);const auto address=*base+instruction.i_imm();const unsigned bytes=1u<<((u.expanded>>12)&3);
 return address%bytes==0&&empirical_cache_->data_hit(hart,address,bytes);
}
void iris_timing_adapter::empirical_load_capture(unsigned hart,size_t id){
 auto&p=pure_[hart];auto&r=p.instructions.at(id);if(r.squashed)return;
 try{
  switch((r.uop.expanded>>12)&7){case 0:r.empirical_load_value=empirical_read<int8_t>(cores_[hart],r.memory_address);break;case 1:r.empirical_load_value=empirical_read<int16_t>(cores_[hart],r.memory_address);break;case 2:r.empirical_load_value=empirical_read<int32_t>(cores_[hart],r.memory_address);break;case 3:r.empirical_load_value=empirical_read<int64_t>(cores_[hart],r.memory_address);break;case 4:r.empirical_load_value=empirical_read<uint8_t>(cores_[hart],r.memory_address);break;case 5:r.empirical_load_value=empirical_read<uint16_t>(cores_[hart],r.memory_address);break;case 6:r.empirical_load_value=empirical_read<uint32_t>(cores_[hart],r.memory_address);break;default:throw std::logic_error("empirical load width");}
  const auto&v=*r.empirical_load_value;const bool known=std::all_of(v.known.begin(),v.known.end(),[](uint8_t x){return x==255;});if(!known)++empirical_load_metrics_[hart].partial_transports;r.private_value=known?std::optional<uint64_t>(v.value):std::nullopt;r.private_value_ready=true;p.values->complete_external(id,r.private_value);
 }catch(trap_t&){
  ++empirical_load_metrics_[hart].faults;r.exception=std::current_exception();frontend_squash(hart,id,false);if(r.wb){const auto&n=clock_.nodes().at(*r.wb);if(!n.cancelled&&!n.completed)clock_.cancel(*r.wb,"empirical-load-precise-fault");r.wb.reset();}p.values->annul_one(id);p.boundary=true;
 }
 if(r.empirical_load_owner){empirical_cache_->complete(*r.empirical_load_owner,clock_.now());cache_nodes_.erase(*r.empirical_load_owner);r.empirical_load_owner.reset();}
}
void iris_timing_adapter::empirical_load_response(unsigned hart,size_t id){
 auto&p=pure_[hart];auto&r=p.instructions.at(id);if(r.squashed)return;
 const auto owner=next_cache_owner_++;const auto d=empirical_cache_->begin({owner,hart,r.memory_address,1u<<r.memory_size,false,clock_.now()});r.empirical_load_owner=owner;empirical_memory_feature(hart,d,false);
 if(d.l1_misses==0&&d.wait_for.empty()){++empirical_load_metrics_[hart].hit_responses;empirical_load_capture(hart,id);return;}
 // A prediction invalidated by real intervening coherence is a conservative
 // miss response, never an invented hit or a repeated architectural load.
 ++empirical_load_metrics_[hart].coherence_fallbacks;frontend_squash(hart,id,false);p.boundary=true;p.frontier=r.pc+r.fetch.insn.length();
 if(async_trace_)*async_trace_<<"{\"event\":\"load-coherence-fallback-debug\",\"hart\":"<<hart<<",\"cycle\":"<<clock_.now()<<",\"load_pc\":"<<r.pc<<",\"restart_pc\":"<<p.frontier<<",\"CPU_instruction\":"<<id<<"}\n";
 // Both parcels may already have left the real frontend FIFO. The accepted
 // load survives, but its annulled younger instructions must be fetched again.
 // This is the empirical cache fallback's explicit CPU redirect, not an
 // architectural PC assignment or a repeated accepted memory transaction.
 if(frontend_enabled(hart)){
  if(!r.frontend||r.frontend->pc!=r.pc)throw std::logic_error("IRIS_FRONTEND_LOAD_FALLBACK_OWNER_MISSING");
  frontend_redirect(hart,p.frontier,r.frontend->ras_head);
  ++frontend_[hart].memory_replay_redirects;
  if(async_trace_)*async_trace_<<"{\"event\":\"frontend-coherence-fallback-redirect\",\"hart\":"<<hart<<",\"cycle\":"<<clock_.now()<<",\"load_pc\":"<<r.pc<<",\"restart_pc\":"<<p.frontier<<",\"RAS_head\":"<<r.frontend->ras_head<<",\"CPU_instruction\":"<<id<<"}\n";
 }

 // The source IBuf has already consumed younger parcels too. Redirect only
 // its speculative fetch state when this accepted load requests CPU replay.
 // Its cache transaction/result actor remains owned and is never canceled.
 if(hart==2&&rocket_packets_)rocket_packet_redirect(p.frontier,"load-coherence-replay",2);

 double cost=3,interval=1;std::string resource="empirical.memory"+std::to_string(hart);
 for(const auto&rule:profile_.empirical_cache_rules)if(rule.hart==hart){cost=3+rule.read+rule.l1*d.l1_misses+rule.outer*d.l2_misses;interval=d.l2_misses?rule.outer_interval*d.l2_misses:1;if(d.l2_misses)resource="empirical.outer";break;}
 if(!std::isfinite(cost)||cost>profile_.max_cycles)throw std::runtime_error("IRIS_EMPIRICAL_LOAD_SERVICE_HORIZON");
 iris::Op response{hart,"empirical.load-coherence-response",resource,uint64_t(std::max(1.0,std::ceil(cost))),uint64_t(std::max(1.0,std::ceil(interval)))};response.pc=r.pc;response.retires=false;response.bytes=1u<<r.memory_size;
 for(const auto dependency:d.wait_for){auto found=cache_nodes_.find(dependency);if(found==cache_nodes_.end())throw std::logic_error("empirical load pending owner");response.deps.push_back(found->second);}
 // The accepted cache transaction outlives its speculative CPU row. Its
 // physical response is never canceled by a branch/IRQ, and a discarded
 // load has no register or device side effect (this path is DRAM-only).
 auto actor=std::make_shared<EmpiricalLoadActor>();actor->hart=hart;actor->cache_owner=owner;r.empirical_load_actor=actor;
 response.on_complete=[this,hart,id,actor]{
  if(actor->done)throw std::logic_error("IRIS_EMPIRICAL_LOAD_DUPLICATE_RESPONSE");
  if(actor->discarded){empirical_cache_->complete(actor->cache_owner,clock_.now());cache_nodes_.erase(actor->cache_owner);++empirical_load_metrics_[hart].discarded_responses;if(async_trace_)*async_trace_<<"{\"event\":\"discarded_load_response\",\"hart\":"<<hart<<",\"node\":"<<*actor->response<<",\"cycle\":"<<clock_.now()<<"}\n";}
  else{auto&r=pure_[hart].instructions.at(id);if(r.empirical_load_actor!=actor||r.squashed)throw std::logic_error("IRIS_EMPIRICAL_LOAD_LIVE_RESPONSE_OWNER");empirical_load_capture(hart,id);r.com_cycle=clock_.now()+profile_.harts[hart].divider;}
  actor->done=true;empirical_load_responses_.erase(*actor->response);
 };
 const auto node=clock_.issue(std::move(response));actor->response=node;empirical_load_responses_[node]=actor;cache_nodes_[owner]=node;r.result=node;clock_.add_dependency(*r.com,node);
}
reg_t iris_timing_adapter::empirical_load_handler(processor_t*p,insn_t insn,reg_t pc){
 if(!empirical_load_owner||!empirical_load_owner->completing_pure_)throw std::logic_error("empirical load handler missing owner");auto&owner=*empirical_load_owner;auto&r=owner.pure_[p->get_id()].instructions.at(*owner.completing_pure_);auto raw=r.fetch.insn;
 if(r.pc!=pc||raw.bits()!=insn.bits()||!r.empirical_load_value)throw std::logic_error("empirical latched load identity");p->iris_write_xpr_transport(r.uop.rd,*r.empirical_load_value);return pc+insn.length();
}
void iris_timing_adapter::empirical_load_before_commit(unsigned hart,size_t id){
 auto&r=pure_[hart].instructions.at(id);if(r.exception)return;if(!r.empirical_load_value)throw std::logic_error("empirical load COM without response");if(empirical_load_owner)throw std::logic_error("nested empirical load COM");empirical_load_owner=this;r.fetch.func=&iris_timing_adapter::empirical_load_handler;
}
void iris_timing_adapter::empirical_load_after_commit(){empirical_load_owner=nullptr;}
