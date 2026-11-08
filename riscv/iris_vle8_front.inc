// Optional one-row load owner. This isolates CPU blocking; existing memory
// service, all vector drains, and whole-VRF/MRF assertions remain unchanged.
namespace {
thread_local iris_timing_adapter*vle8_front_owner=nullptr;
std::array<uint64_t,10> vle8_config(const vectorUnit_t&v){
 return {v.vtype->read(),v.mtype->read(),v.vl->read(),v.vstart->read(),v.tm,v.tk,v.vsew,v.widen,v.altfmt,uint64_t(v.vma)|(uint64_t(v.vta)<<1)|(uint64_t(v.vill)<<2)};
}
}
bool iris_timing_adapter::vle8_candidate(unsigned h,reg_t pc,const insn_fetch_t&fetch)const{
 if(!profile_.empirical_vle8_front||h>=2||vle8_pending_[h])return false;
 auto insn=fetch.insn;const uint32_t raw=insn.bits();
 if(insn.length()!=4||(raw&0xfff0707f)!=0x02000007)return false;
 auto&c=*cores_[h];const auto&s=*c.get_state();const auto&v=c.VU;
 if(!c.iris_pipeline_context_safe()||(s.mstatus->read()&MSTATUS_MPRV)||!(s.mstatus->read()&MSTATUS_VS)||!c.any_vector_extensions()||v.vill||v.vsew!=8||v.vflmul!=1||v.vstart->read_defined(pc)||!v.vl->read()||v.vl->read()>32)return false;
 const auto base=s.XPR.read_transport((raw>>15)&31);
 if(!std::all_of(base.known.begin(),base.known.end(),[](uint8_t b){return b==255;}))return false;
 return c.get_mmu()->iris_pipeline_vle8_permitted(base.value,v.vl->read());
}
void iris_timing_adapter::vle8_check_state(unsigned h,const Vle8Owner&a)const{
 auto&c=*cores_[h];const auto&v=c.VU;
 if(!c.iris_pipeline_context_safe()||v.vflmul!=1||vle8_config(v)!=a.config||std::memcmp(v.reg_file,a.vrf.data(),a.vrf.size())||v.iris_vrf_definedness.read(0,a.vrf.size())!=a.vrf_known.read(0,a.vrf.size())||v.mt!=a.mrf||v.iris_tile_definedness.read(0,a.mrf.size())!=a.mrf_known.read(0,a.mrf.size())||v.iris_initialized!=a.initialized)
  throw std::runtime_error("IRIS_VLE8_PENDING_NUMERIC_OR_CONTEXT_MUTATION hart="+std::to_string(h));
}
void iris_timing_adapter::vle8_begin(unsigned h,iris::NodeId response){
 if(vle8_pending_[h]||!pending_[h]||!pending_[h]->cache_owner||pure_[h].engaged||!pure_[h].packets.empty())throw std::logic_error("IRIS_VLE8_DRAINED_ADMISSION_OWNER");
 const auto&p=*pending_[h];auto insn=p.fetch.insn;const uint32_t raw=insn.bits();auto a=std::make_shared<Vle8Owner>();auto&v=cores_[h]->VU;
 a->pc=p.pc;a->raw=raw;a->destination=(raw>>7)&31;a->bytes=v.vl->read();a->address=cores_[h]->get_state()->XPR.read_transport((raw>>15)&31).value;a->response=response;a->cache_owner=p.cache_owner;
 a->vrf.resize(v.vlenb*32);std::memcpy(a->vrf.data(),v.reg_file,a->vrf.size());a->vrf_known=v.iris_vrf_definedness;a->mrf=v.mt;a->mrf_known=v.iris_tile_definedness;a->initialized=v.iris_initialized;a->config=vle8_config(v);vle8_pending_[h]=a;++vle8_metrics_[h].accepted;
 const auto d=profile_.harts[h].divider;
 // Existing CPU RRD→EX is one edge. Actual drained Compute128 PFC front
 // permission is EX+2 (withheld-response source proof), independent of D data.
 iris::Op front{h,"source.single-vle8.front-COM","source.vle8.front"+std::to_string(h),3*d,d};front.pc=a->pc;front.retires=false;front.issue_period=d;front.on_complete=[this,h,a]{vle8_front(h,a);};a->front=clock_.issue(std::move(front));
 if(async_trace_)*async_trace_<<"{\"event\":\"vle8_admit\",\"hart\":"<<h<<",\"pc\":"<<a->pc<<",\"raw\":"<<a->raw<<",\"cycle\":"<<clock_.now()<<",\"address\":"<<a->address<<",\"bytes\":"<<a->bytes<<",\"vd\":"<<a->destination<<",\"SEW\":8,\"LMUL\":1,\"vtype\":"<<v.vtype->read()<<",\"VL\":"<<a->bytes<<",\"front_node\":"<<a->front<<",\"response_node\":"<<response<<",\"memory_service_unchanged\":true}\n";
}
reg_t iris_timing_adapter::vle8_front_handler(processor_t*p,insn_t insn,reg_t pc){
 if(!vle8_front_owner)throw std::logic_error("IRIS_VLE8_FRONT_HANDLER_OWNER");auto&a=vle8_front_owner->vle8_pending_[p->get_id()];
 if(!a||a->pc!=pc||a->raw!=insn.bits())throw std::logic_error("IRIS_VLE8_FRONT_IDENTITY");
 p->get_state()->sstatus->dirty(SSTATUS_VS);p->VU.vstart->write(0);return pc+4;
}
void iris_timing_adapter::vle8_front(unsigned h,const std::shared_ptr<Vle8Owner>&a){
 if(vle8_pending_[h]!=a||!pending_[h]||a->front_retired||cores_[h]->get_state()->pc!=a->pc||vle8_front_owner)throw std::logic_error("IRIS_VLE8_FRONT_COM_OWNER");vle8_check_state(h,*a);
 completing_=h;completing_node_=a->front;completion_reads_.clear();pending_[h]->fetch.func=&iris_timing_adapter::vle8_front_handler;const auto before=retired_[h];vle8_front_owner=this;
 try{cores_[h]->step(1);if(cores_[h]->iris_step_timing_waited()||cores_[h]->iris_step_architectural_event()||retired_[h]!=before+1)throw std::runtime_error("IRIS_VLE8_FRONT_ARCHITECTURAL_OUTCOME_UNMODELED");}
 catch(...){vle8_front_owner=nullptr;completion_reads_.clear();completing_node_.reset();completing_.reset();throw;}
 vle8_front_owner=nullptr;finish_counter_reads(h,before);completing_node_.reset();completing_.reset();vle8_check_state(h,*a);pending_[h].reset();blocked_[h]=false;previous_[h]=a->front;++completions_;a->front_retired=true;++vle8_metrics_[h].front_retired;
 if(async_trace_)*async_trace_<<"{\"event\":\"vle8_front_COM\",\"hart\":"<<h<<",\"pc\":"<<a->pc<<",\"cycle\":"<<clock_.now()<<",\"numeric_state_unchanged\":true}\n";
 vle8_publish(h,a);
}
void iris_timing_adapter::vle8_response(unsigned h){
 auto a=vle8_pending_[h];if(!a||a->response_done||!a->cache_owner)throw std::logic_error("IRIS_VLE8_RESPONSE_OWNER");vle8_check_state(h,*a);
 try{for(unsigned i=0;i<a->bytes;++i)a->data.push_back(cores_[h]->get_mmu()->load_transport<uint8_t>(a->address+i));}
 catch(trap_t&t){throw std::runtime_error("IRIS_VLE8_POST_ADMISSION_MEMORY_FAULT_UNMODELED hart="+std::to_string(h)+" pc="+std::to_string(a->pc)+" cause="+std::to_string(t.cause()));}
 empirical_cache_->complete(*a->cache_owner,clock_.now(),true);cache_nodes_.erase(*a->cache_owner);a->cache_owner.reset();a->response_done=true;++vle8_metrics_[h].responses;
 if(async_trace_)*async_trace_<<"{\"event\":\"vle8_response\",\"hart\":"<<h<<",\"pc\":"<<a->pc<<",\"cycle\":"<<clock_.now()<<",\"bytes\":"<<a->bytes<<"}\n";
 vle8_publish(h,a);
}
void iris_timing_adapter::vle8_publish(unsigned h,const std::shared_ptr<Vle8Owner>&a){
 if(!a->front_retired||!a->response_done)return;if(vle8_pending_[h]!=a||a->data.size()!=a->bytes)throw std::logic_error("IRIS_VLE8_PUBLICATION_OWNER");vle8_check_state(h,*a);
 for(unsigned i=0;i<a->bytes;++i)cores_[h]->VU.write_transport(a->destination,i,a->data[i]);
 vle8_metrics_[h].published_bytes+=a->bytes;
 if(async_trace_)*async_trace_<<"{\"event\":\"vle8_publish\",\"hart\":"<<h<<",\"pc\":"<<a->pc<<",\"cycle\":"<<clock_.now()<<",\"bytes\":"<<a->bytes<<",\"scope\":\"batched-existing-response-not-physical-VRF-bank-timing\"}\n";
 vle8_pending_[h].reset();
}
void iris_timing_adapter::vle8_write_totals(std::ostream&out)const{
 if(!profile_.empirical_vle8_front)return;out<<",\"single_vle8_front\":{\"scope\":\"opt-in-h0h1-single-nf1-vm1-e8m1-VL1..32-one32B-block-Mmode-DRAM;scalarALU-CFI-only;wholeVRF-MRF-guards;all-other-boundaries-and-IRQ-drain;batched-response-memory-service-unchanged;not-full-LSU-VRF-bank-timing\",\"calibrated\":false,\"per_hart\":[";
 for(unsigned h=0;h<vle8_metrics_.size();++h){if(h)out<<',';const auto&m=vle8_metrics_[h];out<<"{\"accepted\":"<<m.accepted<<",\"front_retired\":"<<m.front_retired<<",\"responses\":"<<m.responses<<",\"published_bytes\":"<<m.published_bytes<<",\"scalar_retired_while_pending\":"<<m.scalar_retired_while_pending<<",\"IRQ_deferred_checks\":"<<m.IRQ_deferred<<",\"pending\":"<<bool(vle8_pending_[h])<<'}';}out<<"]}";
}
