namespace {std::optional<uint64_t> store_xpr_value(processor_t*p,unsigned reg){const auto v=p->get_state()->XPR.read_transport(reg);if(std::all_of(v.known.begin(),v.known.end(),[](uint8_t b){return b==255;}))return v.value;return {};}}
// Optional finite scalar store front over approximate V6 intent-time tags.
// Functional bytes/known masks are written only by the original handler at COM.
bool iris_timing_adapter::empirical_store_candidate(unsigned hart,const iris::shuttle::Uop&u)const{
 if(!profile_.empirical_store_front||!u.control_verified||u.exception||!u.has(iris::shuttle::MEM)||(u.expanded&127)!=0x23||((u.expanded>>12)&7)>3)return false;
 bool fallback_rule=false;for(const auto&rule:profile_.rules)if(rule.hart==hart&&(u.raw&rule.mask)==rule.match){fallback_rule=true;break;}if(!fallback_rule)return false;
 const auto&s=*cores_[hart]->get_state();if(s.prv!=PRV_M||s.v||s.debug_mode||(s.mstatus->read()&MSTATUS_MPRV))return false;
 const auto&p=pure_[hart];auto base=p.engaged&&p.values?p.values->peek(u.rs1):store_xpr_value(cores_[hart],u.rs1);if(!base)return false;
 const auto x=u.expanded;const auto address=*base+iris::frontend::PureAluValue::sext(((x>>25)<<5)|((x>>7)&31),12);const unsigned bytes=1u<<((x>>12)&3);
 return cores_[hart]->get_mmu()->iris_pipeline_store_permitted(address,bytes)&&empirical_cache_->owned_store_hit(hart,address,bytes);
}
bool iris_timing_adapter::empirical_store_wait_base(unsigned hart,const iris::shuttle::Uop&u)const{
 if(!profile_.empirical_store_front||(u.expanded&127)!=0x23||((u.expanded>>12)&7)>3)return false;
 const auto&p=pure_[hart];if(!p.engaged||!p.values||!u.rs1||!p.last_writer[u.rs1])return false;
 const auto&producer=p.instructions.at(*p.last_writer[u.rs1]);return !producer.released&&!producer.private_value_ready;
}
bool iris_timing_adapter::empirical_store_before_commit(unsigned hart,size_t id){
 auto&p=pure_[hart];auto&r=p.instructions.at(id);const unsigned bytes=1u<<r.memory_size;
 if(r.store_serviced){if(!r.store_owner||store_deferred_[hart]!=std::optional<size_t>(id))throw std::logic_error("IRIS_STORE_SERVICE_OWNER_MISSING");return true;}
 if(r.store_owner||store_deferred_[hart])throw std::logic_error("IRIS_STORE_COM_DUPLICATE_OWNER");
 const auto base=store_xpr_value(cores_[hart],r.uop.rs1);const auto x=r.uop.expanded;
 if(!base||*base+iris::frontend::PureAluValue::sext(((x>>25)<<5)|((x>>7)&31),12)!=r.memory_address)throw std::logic_error("IRIS_STORE_ADDRESS_PHASE_MISMATCH");
 const bool owned=empirical_cache_->owned_store_hit(hart,r.memory_address,bytes);
 auto instruction=r.fetch.insn;const auto divider=profile_.harts[hart].divider;const Rule*selected=nullptr;for(const auto&rule:profile_.rules)if(rule.hart==hart&&(uint32_t(instruction.bits())&rule.mask)==rule.match){selected=&rule;break;}if(!selected)throw std::logic_error("IRIS_STORE_CONFIGURED_FALLBACK_RULE_MISSING");
 const auto owner=next_cache_owner_++;
 auto d=owned?empirical_cache_->begin_owned_store({owner,hart,r.memory_address,bytes,true,clock_.now()}):empirical_cache_->begin({owner,hart,r.memory_address,bytes,true,clock_.now()});
 empirical_memory_feature(hart,d,true);r.store_owner=owner;
 // Preserve the existing scalar DRAM rule priority and fractional state.
 // Ordinary DRAM families are superseded when cache-service rules exist;
 // cache miss/dirty terms and the shared outer interval remain explicit.
 double extra=0,interval=1;std::string resource="empirical.memory"+std::to_string(hart);
 auto charge=[&](const std::string&key,double residual){auto&fraction=empirical_fraction_[key];fraction+=residual;if(!std::isfinite(fraction)||fraction<0||fraction>profile_.max_cycles)throw std::runtime_error("IRIS_STORE_SERVICE_COST_HORIZON");const auto whole=std::floor(fraction);fraction-=whole;extra+=whole;};
 if(profile_.empirical_cache_rules.empty())for(const auto&rule:profile_.empirical_rules)if(rule.hart==hart&&rule.family=="memory.DRAM.store"){charge(std::to_string(hart)+":memory.DRAM.store",rule.setup);interval=rule.interval;resource=rule.resource;break;}
 for(const auto&rule:profile_.empirical_cache_rules)if(rule.hart==hart){charge("cache:"+std::to_string(hart),rule.write+rule.l1*d.l1_misses+rule.outer*d.l2_misses+rule.dirty*d.l2_dirty_victims);if(d.l2_misses){resource="empirical.outer";interval=rule.outer_interval*d.l2_misses;}break;}
 if(!std::isfinite(extra)||extra<0||extra>profile_.max_cycles||!std::isfinite(interval)||interval<1||interval>double(UINT64_MAX/divider))throw std::runtime_error("IRIS_STORE_SERVICE_COST_HORIZON");
 if(owned&&extra==0&&interval==1){++store_metrics_[hart].fast_COM;empirical_store_observe(hart,id,"accepted-fast-COM");return true;}
 // Ownership changed AFTER admission, or configured extra service is positive.
 // This instruction is already oldest at COM. Retain it, annul younger CPU
 // work and perform one conservative owned response before architectural write.
 if(!owned)++store_metrics_[hart].ownership_losses;else ++store_metrics_[hart].cost_deferrals;
 frontend_squash(hart,id,false,"empirical-store-COM-conservative-service");p.boundary=true;p.frontier=r.pc+r.fetch.insn.length();
 if(frontend_enabled(hart)){
  if(!r.frontend||r.frontend->pc!=r.pc)throw std::logic_error("IRIS_STORE_REPLAY_FRONTEND_OWNER_MISSING");frontend_redirect(hart,p.frontier,r.frontend->ras_head);
 }else if(hart==2&&rocket_packets_)rocket_packet_redirect(p.frontier,"store-COM-conservative-service",2);
 double cost=owned?extra:double(selected->latency)/divider+extra;
 if(!std::isfinite(cost)||cost<0||cost>profile_.max_cycles)throw std::runtime_error("IRIS_STORE_SERVICE_COST_HORIZON");
 const auto duration=uint64_t(std::max(1.0,std::ceil(cost)));if(duration>(UINT64_MAX-1)/divider)throw std::overflow_error("IRIS_STORE_SERVICE_CLOCK_HORIZON");
 iris::Op response{hart,"empirical.owned-store-response",resource,duration*divider,uint64_t(std::max(1.0,std::ceil(interval)))*divider};response.pc=r.pc;response.retires=false;response.issue_period=divider;response.bytes=bytes;
 for(const auto dependency:d.wait_for){const auto found=cache_nodes_.find(dependency);if(found==cache_nodes_.end())throw std::logic_error("IRIS_STORE_CACHE_DEPENDENCY_MISSING");response.deps.push_back(found->second);}
 response.on_complete=[this,hart,id]{auto&r=pure_[hart].instructions.at(id);if(r.squashed||r.retired||!r.store_owner||store_deferred_[hart]!=std::optional<size_t>(id))throw std::logic_error("IRIS_STORE_ACCEPTED_RESPONSE_LOST");r.store_serviced=true;r.com_cycle=clock_.now();empirical_store_observe(hart,id,"before-deferred-publication");if(cores_[hart]->iris_pipeline_interrupt_exception())++store_metrics_[hart].IRQ_pending_before_publish;pure_commit(hart,id);};
 const auto old_com=*r.com;const auto node=clock_.issue(std::move(response));cache_nodes_[owner]=node;store_deferred_[hart]=id;
 if(hart==2){r.com=node;r.wb=node;}else{r.com=node;if(!r.wb)throw std::logic_error("IRIS_STORE_WB_OWNER_MISSING");clock_.add_dependency(*r.wb,node);}
 previous_[hart]=r.wb?r.wb:r.com;
 empirical_store_observe(hart,id,"accepted-deferred-COM");
 if(async_trace_)*async_trace_<<"{\"event\":\"store_defer\",\"hart\":"<<hart<<",\"instruction\":"<<id<<",\"pc\":"<<r.pc<<",\"cycle\":"<<clock_.now()<<",\"address\":"<<r.memory_address<<",\"bytes\":"<<bytes<<",\"owned_at_COM\":"<<(owned?"true":"false")<<",\"old_COM\":"<<old_com<<",\"response\":"<<node<<",\"cache_owner\":"<<owner<<",\"waiting_for_owners\":"<<d.wait_for.size()<<"}\n";
 return false;
}
void iris_timing_adapter::empirical_store_after_commit(unsigned hart,size_t id,bool retired){
 auto&r=pure_[hart].instructions.at(id);if(!r.store_owner)throw std::logic_error("IRIS_STORE_PUBLISH_WITHOUT_OWNER");if(retired)empirical_store_observe(hart,id,"after-publication");const auto owner=*r.store_owner;empirical_cache_->complete(owner,clock_.now());cache_nodes_.erase(owner);r.store_owner.reset();if(retired){++store_metrics_[hart].published;clock_.set_completing_payload(*r.com,1u<<r.memory_size);}
 if(store_deferred_[hart]){if(*store_deferred_[hart]!=id)throw std::logic_error("IRIS_STORE_PUBLISH_OWNER_MISMATCH");store_deferred_[hart].reset();}
 if(retired&&async_trace_)*async_trace_<<"{\"event\":\"store_publish\",\"hart\":"<<hart<<",\"instruction\":"<<id<<",\"pc\":"<<r.pc<<",\"cycle\":"<<clock_.now()<<",\"address\":"<<r.memory_address<<",\"bytes\":"<<(1u<<r.memory_size)<<",\"serviced\":"<<(r.store_serviced?"true":"false")<<"}\n";
}
void iris_timing_adapter::empirical_store_write_totals(std::ostream&out)const{
 if(!profile_.empirical_store_front)return;
 out<<",\"owned_store_front\":{\"enabled\":true,\"scope\":\"M-mode aligned DRAM integer SB/SH/SW/SD inclRVC; original typed effect at COM; V6 approximate intent-time ownership, not RTL coherence proof\",\"ownership_loss_policy\":\"retain oldest unretired instruction, annul younger CPU, noncancellable ordinary cache service, interrupt delivery after owned instruction\",\"calibrated\":false,\"per_hart\":[";
 for(unsigned h=0;h<store_metrics_.size();++h){if(h)out<<',';const auto&m=store_metrics_[h];out<<"{\"RRD_accepted\":"<<m.accepted<<",\"fast_COM\":"<<m.fast_COM<<",\"ownership_losses\":"<<m.ownership_losses<<",\"positive_cost_deferrals\":"<<m.cost_deferrals<<",\"published\":"<<m.published<<",\"IRQ_pending_before_publication\":"<<m.IRQ_pending_before_publish<<",\"pending_accepted_response\":"<<(store_deferred_[h]?"true":"false")<<'}';}out<<"]}";
}

void iris_timing_adapter::empirical_store_observe(unsigned hart,size_t id,const char*phase)const{
 if(!async_trace_)return;const auto&r=pure_[hart].instructions.at(id);auto instruction=r.fetch.insn;const auto value=cores_[hart]->iris_frontend_read_beat(r.memory_address&~7ull);const unsigned shift=(r.memory_address&7)*8;uint64_t known=0;for(unsigned i=0;i<8;++i)known|=uint64_t(value.known[i])<<(i*8);const auto source=cores_[hart]->get_state()->XPR.read_transport(r.uop.rs2);uint64_t source_known=0;for(unsigned i=0;i<8;++i)source_known|=uint64_t(source.known[i])<<(i*8);
 *async_trace_<<"{\"event\":\"store_memory_observation\",\"scope\":\"side-effect-free simulation RAM+typedXPR, not RTL physical ports\",\"phase\":"<<std::quoted(phase)<<",\"hart\":"<<hart<<",\"instruction\":"<<id<<",\"pc\":"<<r.pc<<",\"raw\":"<<(instruction.length()==2?uint16_t(instruction.bits()):uint32_t(instruction.bits()))<<",\"cycle\":"<<clock_.now()<<",\"address\":"<<r.memory_address<<",\"bytes\":"<<(1u<<r.memory_size)<<",\"cache_owner\":"<<r.store_owner.value_or(0)<<",\"COM_node\":"<<r.com.value_or(0)<<",\"memory_value\":"<<(value.value>>shift)<<",\"memory_known\":"<<(known>>shift)<<",\"source_value\":"<<source.value<<",\"source_known\":"<<source_known<<"}\n";
}

void iris_timing_adapter::empirical_store_boundary_observe(unsigned hart){
 if(!profile_.empirical_store_front||!async_trace_||!pending_[hart])return;const auto&p=*pending_[hart];const auto&f=p.feature.memory;if(f.decode!=iris::MemoryDecode::scalar||(f.kind!=iris::AccessKind::load&&f.kind!=iris::AccessKind::store)||!f.bytes||f.bytes>8||f.address<0x80000000ull||f.address+f.bytes>0x180000000ull||(f.address&7)+f.bytes>8)return;
 auto insn=p.fetch.insn;const uint32_t raw=insn.bits();uint64_t value=0,known=0;
 if(f.kind==iris::AccessKind::load){const bool c=insn.length()==2;const unsigned q=raw&3,cf=raw>>13;if(c?!((q==0||q==2)&&(cf==2||cf==3)):(raw&127)!=3)return;const unsigned rd=c?(q==0?8+((raw>>2)&7):(raw>>7)&31):(raw>>7)&31;if(!rd)return;const auto v=cores_[hart]->get_state()->XPR.read_transport(rd);value=v.value;for(unsigned i=0;i<8;++i)known|=uint64_t(v.known[i])<<(i*8);}
 else{const auto v=cores_[hart]->iris_frontend_read_beat(f.address&~7ull);const unsigned shift=(f.address&7)*8;value=v.value>>shift;for(unsigned i=0;i<8;++i)known|=uint64_t(v.known[i])<<(i*8);known>>=shift;}
 *async_trace_<<"{\"event\":"<<std::quoted(f.kind==iris::AccessKind::load?"scalar_cache_load_value":"scalar_cache_store_value")<<",\"scope\":\"simulated architectural response, not physicalRTLport\",\"hart\":"<<hart<<",\"pc\":"<<p.pc<<",\"cycle\":"<<clock_.now()<<",\"address\":"<<f.address<<",\"bytes\":"<<f.bytes<<",\"value\":"<<value<<",\"known\":"<<known<<",\"cache_owner\":"<<p.cache_owner.value_or(0)<<",\"node\":"<<p.completion_node.value_or(0)<<"}\n";
}
