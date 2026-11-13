// Optional finite source-control integration. Successful COM makes a command
// available at COM+1; that CPU bridge is conservative and not RTL-qualified.
namespace {std::string vadd_eg_guest_context(unsigned h,processor_t*core,uint64_t pc,uint32_t raw){
 const auto*s=core->get_state();const auto&v=core->VU;std::ostringstream out;out<<" hart="<<h<<" pc="<<pc<<" raw="<<raw<<" VL="<<v.vl->read()<<" SEW="<<v.vsew<<" LMUL="<<v.vflmul<<" frm="<<s->frm->read()<<" flags="<<s->fflags->read()<<" mstatus="<<s->mstatus->read()<<" mie="<<s->mie->read()<<" mip="<<s->mip->read();return out.str();
}}
bool iris_timing_adapter::vadd_eg_is_vv(const insn_fetch_t*f)const{
 if(!f)return false;auto i=f->insn;return i.length()==4&&(uint32_t(i.bits())&0xfc00707f)==0x0057;
}
iris::rvv_integer_source::Command iris_timing_adapter::vadd_eg_geometry(unsigned h,const insn_fetch_t&f,uint64_t id)const{
 auto&v=cores_[h]->VU;const auto*s=cores_[h]->get_state();auto i=f.insn;const auto raw=uint32_t(i.bits());
 if(h>=2||!vadd_eg_is_vv(&f)||!(raw&(1u<<25))||v.vill||v.vstart->read()||v.altfmt||v.vlenb!=32||
    (v.vsew!=8&&v.vsew!=16&&v.vsew!=32&&v.vsew!=64)||(v.vflmul!=1&&v.vflmul!=2&&v.vflmul!=4&&v.vflmul!=8)||v.vl->read()!=v.vlmax)
  throw std::runtime_error(std::string("IRIS_VADD_EG_FULLVL_UNMASKED_SCOPE")+vadd_eg_guest_context(h,cores_[h],s->pc,raw));
 if(s->prv!=PRV_M||s->v||s->debug_mode||(s->mstatus->read()&MSTATUS_VS)!=MSTATUS_VS||(s->mstatus->iris_known_bits()&MSTATUS_VS)!=MSTATUS_VS)
  throw std::runtime_error(std::string("IRIS_VADD_EG_MMODE_KNOWN_CONFIG_VS_ALREADY_DIRTY_SCOPE")+vadd_eg_guest_context(h,cores_[h],s->pc,raw));
 if((s->mstatus->read()&MSTATUS_MIE)||(s->mie->read()&s->mip->read()))throw std::runtime_error(std::string("IRIS_VADD_EG_IRQ_CONTEXT_UNMODELED")+vadd_eg_guest_context(h,cores_[h],s->pc,raw));
 iris::rvv_integer_source::Command c{id,unsigned(id%32),unsigned(raw>>7&31),unsigned(raw>>15&31),unsigned(raw>>20&31),unsigned(v.vsew),unsigned(v.vflmul)};
 try{iris::rvv_integer_source::Scheduler::validate(c);}catch(const std::invalid_argument&){throw std::runtime_error(std::string("IRIS_VADD_EG_REGISTER_GROUP_SCOPE")+vadd_eg_guest_context(h,cores_[h],s->pc,raw));}return c;
}
// Unretired CPU-front reservations have no VU/VRF side effects. An opaque
// token protects a speculative unqualified VADD until its older CFI resolves.
// Its placeholder only tests future FIFO input capacity; it must never be
// accepted into the source controller or used for functional arithmetic.
iris::rvv_integer_source::Command iris_timing_adapter::vadd_eg_reservation_geometry(unsigned h,const insn_fetch_t&f,uint64_t id,bool&opaque)const{
 opaque=false;
 try{return vadd_eg_geometry(h,f,id);}
 catch(const std::runtime_error&e){const std::string message=e.what();if(!message.starts_with("IRIS_VADD_EG_FULLVL_UNMASKED_SCOPE ")&&!message.starts_with("IRIS_VADD_EG_MMODE_KNOWN_CONFIG_VS_ALREADY_DIRTY_SCOPE ")&&!message.starts_with("IRIS_VADD_EG_IRQ_CONTEXT_UNMODELED ")&&!message.starts_with("IRIS_VADD_EG_REGISTER_GROUP_SCOPE "))throw;}
 catch(const std::invalid_argument&e){if(std::string(e.what())!="VADD_SOURCE_FINITE_GEOMETRY")throw;}
 opaque=true;return iris::rvv_integer_source::Command{id,unsigned(id%32),8,16,24,32,1};
}
std::shared_ptr<iris_timing_adapter::VaddEgOwner>iris_timing_adapter::vadd_eg_find(unsigned h,size_t id)const{
 if(h>=vadd_eg_pending_.size())return{};for(const auto&a:vadd_eg_pending_[h])if(a->actor->instruction==id)return a;return{};
}
bool iris_timing_adapter::vadd_eg_can_dispatch(unsigned h,const insn_fetch_t&fetch)const{
 const auto divider=profile_.harts[h].divider,now=clock_.now()/divider,available=now+4;
 if(clock_.now()%divider)throw std::logic_error("IRIS_VADD_EG_UNALIGNED_ADMISSION");
 bool opaque=false;auto candidate=vadd_eg_reservation_geometry(h,fetch,vadd_eg_generation_[h]+1,opaque);auto q=vadd_eg_queues_[h];const auto last=vadd_eg_last_edge_[h];
 auto begin=last?*last+1:now;
 if(q.empty()){begin=now;for(const auto&a:vadd_eg_pending_[h])if(!a->queued)begin=std::min(begin,a->available);if(last)begin=std::max(begin,*last+1);}
 for(auto edge=begin;edge<=available;++edge){
  std::optional<iris::rvv_integer_source::Command>input;
  for(const auto&a:vadd_eg_pending_[h])if(!a->queued&&a->available==edge){if(input)throw std::logic_error("IRIS_VADD_EG_MULTIPLE_COM_SLOTS");input=a->command;}
  if(edge==available){if(input)return false;input=candidate;}
  auto result=q.step(edge,input);if(input&&!result.input_fire){if(edge==available)return false;throw std::logic_error("IRIS_VADD_EG_PRIOR_RESERVATION_OVERRUN");}
 }
 return true;
}
void iris_timing_adapter::vadd_eg_start_clock(unsigned h){
 if(vadd_eg_clock_active_[h])return;auto divider=profile_.harts[h].divider;
 iris::Op tick{h,"source.vadd.EG.queue.edge","source.vadd.EG.clock"+std::to_string(h),divider,divider};
 tick.retires=false;tick.cancellable=false;tick.issue_period=divider;tick.earliest=clock_.now();
 tick.on_complete=[this,h]{vadd_eg_clock_active_[h]=false;vadd_eg_tick(h);};vadd_eg_clock_active_[h]=true;clock_.issue(std::move(tick));
}
void iris_timing_adapter::vadd_eg_begin(unsigned h,size_t id){
 auto&r=pure_[h].instructions.at(id);if(!empirical_async_can_dispatch(h,&r.fetch))throw std::logic_error("IRIS_VADD_EG_UNRESERVED_FRONT");
 if(vadd_eg_pending_[h].empty()){
  if(!vadd_eg_queues_[h].empty())throw std::logic_error("IRIS_VADD_EG_ORPHAN_SOURCE_QUEUE");
  vadd_eg_physical_versions_[h].fill(0);vadd_eg_logical_versions_[h].fill(0);++vadd_eg_epoch_[h];
 }
 auto a=std::make_shared<VaddEgOwner>();a->actor=std::make_shared<EmpiricalAsync>();a->actor->instruction=id;a->actor->com_cycle=r.com_cycle;a->actor->stages_fp=false;
 a->command=vadd_eg_reservation_geometry(h,r.fetch,++vadd_eg_generation_[h],a->opaque_front);a->pc=r.pc;a->raw=uint32_t(r.fetch.insn.bits());a->epoch=vadd_eg_epoch_[h];a->available=r.com_cycle/profile_.harts[h].divider+1;a->remaining=a->command.beats();
 if(r.com_cycle!=clock_.now()+3*profile_.harts[h].divider)throw std::logic_error("IRIS_VADD_EG_FIXED_COM_PHASE_SCOPE");
 vadd_eg_pending_[h].push_back(a);empirical_async_[h]=vadd_eg_pending_[h].front()->actor;++vadd_eg_accepted_[h];vadd_eg_peak_[h]=std::max<uint64_t>(vadd_eg_peak_[h],vadd_eg_pending_[h].size());
 vadd_eg_start_clock(h);
 if(async_trace_)*async_trace_<<"{\"event\":\"vadd_EG_front_reservation\",\"hart\":"<<h<<",\"instruction\":"<<id<<",\"generation\":"<<a->command.id<<",\"pc\":"<<a->pc<<",\"RRD\":"<<clock_.now()<<",\"COM\":"<<r.com_cycle<<",\"available\":"<<a->available*profile_.harts[h].divider<<"}\n";
}
void iris_timing_adapter::vadd_eg_before(unsigned h,const std::shared_ptr<VaddEgOwner>&a){
 auto&v=cores_[h]->VU;auto*s=cores_[h]->get_state();auto&r=pure_[h].instructions.at(a->actor->instruction);
 auto c=vadd_eg_geometry(h,r.fetch,a->command.id);if(a->opaque_front)throw std::runtime_error(std::string("IRIS_VADD_EG_RRD_TO_COM_GEOMETRY_CHANGE_UNMODELED")+vadd_eg_guest_context(h,cores_[h],a->pc,a->raw));if(c.vd!=a->command.vd||c.vs1!=a->command.vs1||c.vs2!=a->command.vs2||c.sew!=a->command.sew||c.lmul!=a->command.lmul)throw std::runtime_error(std::string("IRIS_VADD_EG_CONFIGURATION_CHANGED_BEFORE_COM")+vadd_eg_guest_context(h,cores_[h],a->pc,a->raw));
 auto&actor=*a->actor;actor.before_vrf.resize(v.vlenb*32);std::memcpy(actor.before_vrf.data(),v.reg_file,actor.before_vrf.size());actor.before_vrf_known=v.iris_vrf_definedness;
 // Construct logical operand versions privately. Unknown operands refuse
 // before any projection into the functional core's synchronous COM oracle.
 a->input_vrf=actor.before_vrf;a->input_known=actor.before_vrf_known;
 auto required=[&](size_t off){for(unsigned base:{a->command.vd,a->command.vs1,a->command.vs2})if(off>=32*base&&off<32*(base+a->command.lmul))return true;return false;};
 for(const auto&older:vadd_eg_pending_[h]){
  if(older==a)break;if(!older->actor->retired)throw std::logic_error("IRIS_VADD_EG_COM_ORDER");
  for(unsigned eg=0;eg<older->command.beats();++eg){size_t off=32*older->command.vd+16*eg;if(required(off)){std::memcpy(a->input_vrf.data()+off,older->actor->after_vrf.data()+off,16);a->input_known.write(off,older->actor->after_vrf_known.read(off,16));}}
 }
 try{for(unsigned base:{a->command.vs1,a->command.vs2})a->input_known.require(32*base,32*a->command.lmul,{h,a->pc,"source-VADD-EG-operand"});}catch(const std::runtime_error&e){throw std::runtime_error(std::string(e.what())+vadd_eg_guest_context(h,cores_[h],a->pc,a->raw));}
 a->read_versions=vadd_eg_logical_versions_[h];a->before_versions=vadd_eg_logical_versions_[h];a->after_versions=a->before_versions;
 for(unsigned i=0;i<a->command.beats();++i){unsigned eg=2*a->command.vd+i;a->after_versions[eg]=++vadd_eg_logical_versions_[h][eg];}a->logical_reserved=true;
 // VADD has no floating flag or FS effects. Only private logical VRF
 // operands enter the synchronous functional oracle; no source RAM is touched.
 std::memcpy(v.reg_file,a->input_vrf.data(),a->input_vrf.size());v.iris_vrf_definedness=a->input_known;
}
void iris_timing_adapter::vadd_eg_after(unsigned h,const std::shared_ptr<VaddEgOwner>&a,bool retired){
 auto&v=cores_[h]->VU;auto*s=cores_[h]->get_state();auto&actor=*a->actor;
 actor.after_vrf.resize(v.vlenb*32);std::memcpy(actor.after_vrf.data(),v.reg_file,actor.after_vrf.size());actor.after_vrf_known=v.iris_vrf_definedness;
 std::memcpy(v.reg_file,actor.before_vrf.data(),actor.before_vrf.size());v.iris_vrf_definedness=actor.before_vrf_known;
 if(!retired){vadd_eg_cancel(h,a);return;}
 const size_t begin=32*a->command.vd,end=begin+32*a->command.lmul;
 for(size_t i=0;i<a->input_vrf.size();++i)if(i<begin||i>=end)if(actor.after_vrf[i]!=a->input_vrf[i]||actor.after_vrf_known.byte(i)!=a->input_known.byte(i))throw std::logic_error("IRIS_VADD_EG_UNEXPECTED_VRF_WRITE");
 if(clock_.now()!=actor.com_cycle)throw std::logic_error("IRIS_VADD_EG_COM_PHASE_CHANGED");actor.retired=true;vadd_eg_start_clock(h);
 if(async_trace_)*async_trace_<<"{\"event\":\"vadd_EG_functional_COM\",\"hart\":"<<h<<",\"generation\":"<<a->command.id<<",\"pc\":"<<a->pc<<",\"cycle\":"<<clock_.now()<<",\"raw\":"<<a->raw<<",\"SEW\":"<<a->command.sew<<",\"VL\":"<<v.vl->read()<<",\"LMUL_numerator\":"<<a->command.lmul<<",\"LMUL_denominator\":1,\"vs1\":"<<a->command.vs1<<",\"vs2\":"<<a->command.vs2<<",\"vd\":"<<a->command.vd<<",\"geometry_authority\":\"checked_architectural_COM\",\"physical_VRF_restored\":true}\n";
}
void iris_timing_adapter::vadd_eg_tick(unsigned h){
 const auto divider=profile_.harts[h].divider,edge=clock_.now()/divider;
 if(clock_.now()%divider)throw std::logic_error("IRIS_VADD_EG_UNALIGNED_EDGE");
 std::shared_ptr<VaddEgOwner>input;for(const auto&a:vadd_eg_pending_[h])if(!a->queued&&a->available<=edge){if(input||a->available!=edge||!a->actor->retired||a->opaque_front)throw std::logic_error("IRIS_VADD_EG_COM_INPUT_PHASE");input=a;}
 auto result=vadd_eg_queues_[h].step(edge,input?std::optional<iris::rvv_integer_source::Command>(input->command):std::nullopt);vadd_eg_last_edge_[h]=edge;
 // Scheduler state after step may already be empty while this source edge
 // still consumes the final writepipe slot. Preserve the actual preedge busy.
 vadd_eg_prebusy_[h]=result.vdq_before||result.iq_before||result.seq_before||std::any_of(result.pipe.begin(),result.pipe.end(),[](const auto&p){return bool(p);});
 if(input){if(!result.input_fire)throw std::logic_error("IRIS_VADD_EG_RESERVED_INPUT_NOT_READY");input->queued=true;}
 auto owner=[&](uint64_t generation){for(const auto&a:vadd_eg_pending_[h])if(a->command.id==generation)return a;throw std::logic_error("IRIS_VADD_EG_UNOWNED_SOURCE_EVENT");};
 auto&v=cores_[h]->VU;
 if(result.issue){const auto&m=*result.issue;auto a=owner(m.command.id);if(!a->actor->retired||!a->queued||a->epoch!=vadd_eg_epoch_[h])throw std::logic_error("IRIS_VADD_EG_ISSUE_OWNER");
  for(unsigned eg:{m.source1,m.source2}){size_t off=16*eg;if(vadd_eg_physical_versions_[h][eg]!=a->read_versions[eg]||std::memcmp(v.reg_file+off,a->input_vrf.data()+off,16)||v.iris_vrf_definedness.read(off,16)!=a->input_known.read(off,16))throw std::logic_error("IRIS_VADD_EG_SOURCE_VERSION_AT_READ");}
  ++vadd_eg_issued_[h];if(async_trace_)*async_trace_<<"{\"event\":\"vadd_EG_microissue\",\"hart\":"<<h<<",\"generation\":"<<a->command.id<<",\"pc\":"<<a->pc<<",\"cycle\":"<<clock_.now()<<",\"index\":"<<m.index<<",\"destination_EG\":"<<m.destination<<"}\n";
 }
 if(result.write){const auto&m=*result.write;auto a=owner(m.command.id);const size_t off=16*m.destination;
  if(!a->actor->retired||!a->remaining||a->epoch!=vadd_eg_epoch_[h]||vadd_eg_physical_versions_[h][m.destination]!=a->before_versions[m.destination]||std::memcmp(v.reg_file+off,a->input_vrf.data()+off,16)||v.iris_vrf_definedness.read(off,16)!=a->input_known.read(off,16))throw std::logic_error("IRIS_VADD_EG_DESTINATION_VERSION_AT_WRITE");
  std::memcpy(v.reg_file+off,a->actor->after_vrf.data()+off,16);v.iris_vrf_definedness.write(off,a->actor->after_vrf_known.read(off,16));vadd_eg_physical_versions_[h][m.destination]=a->after_versions[m.destination];
  ++vadd_eg_writes_[h];--a->remaining;
  iris::PhysicalOp point{h,"source.vadd.EG.write","source.vadd.EG.write"+std::to_string(h),a->pc,16,0,{},"saved Compute128 integer VADD EG controller; source oneedge write; CPU COMplus1 bridge unqualified",true};clock_.record_physical_edge(std::move(point));
  if(async_trace_)*async_trace_<<"{\"event\":\"vadd_EG_physical_write\",\"hart\":"<<h<<",\"generation\":"<<a->command.id<<",\"pc\":"<<a->pc<<",\"cycle\":"<<clock_.now()<<",\"index\":"<<m.index<<",\"bytes\":16,\"version\":"<<a->after_versions[m.destination]<<"}\n";
  if(!a->remaining){a->actor->done=true;auto&pending=vadd_eg_pending_[h];pending.erase(std::find(pending.begin(),pending.end(),a));empirical_async_[h]=pending.empty()?nullptr:pending.front()->actor;}
 }
 bool waiting=false;for(const auto&a:vadd_eg_pending_[h])waiting|=!a->queued;
 if(waiting||!vadd_eg_queues_[h].empty())vadd_eg_start_clock(h);
}
void iris_timing_adapter::vadd_eg_cancel(unsigned h,const std::shared_ptr<VaddEgOwner>&a){
 if(a->actor->retired||a->queued)throw std::logic_error("IRIS_VADD_EG_ACCEPTED_SOURCE_WORK_NOT_CANCELLABLE");
 if(a->logical_reserved)for(unsigned i=0;i<a->command.beats();++i){unsigned eg=2*a->command.vd+i;if(vadd_eg_logical_versions_[h][eg]!=a->after_versions[eg])throw std::logic_error("IRIS_VADD_EG_FAILED_COM_LOGICAL_VERSION");vadd_eg_logical_versions_[h][eg]=a->before_versions[eg];}
 auto&pending=vadd_eg_pending_[h];auto it=std::find(pending.begin(),pending.end(),a);if(it==pending.end())throw std::logic_error("IRIS_VADD_EG_CANCEL_OWNER");pending.erase(it);++vadd_eg_killed_[h];empirical_async_[h]=pending.empty()?nullptr:pending.front()->actor;
 if(async_trace_)*async_trace_<<"{\"event\":\"vadd_EG_wrongpath_cancel\",\"hart\":"<<h<<",\"generation\":"<<a->command.id<<",\"pc\":"<<a->pc<<",\"cycle\":"<<clock_.now()<<"}\n";
}
void iris_timing_adapter::vadd_eg_check_irq()const{
 for(unsigned h=0;h<2;++h)if(std::any_of(vadd_eg_pending_[h].begin(),vadd_eg_pending_[h].end(),[](const auto&a){return a->actor->retired;})){const auto*s=cores_[h]->get_state();if((s->mstatus->read()&MSTATUS_MIE)||(s->mie->read()&s->mip->read()))throw std::runtime_error(std::string("IRIS_VADD_EG_ACTIVE_IRQ_CONTEXT_UNMODELED")+vadd_eg_guest_context(h,cores_[h],vadd_eg_pending_[h].front()->pc,vadd_eg_pending_[h].front()->raw));}
}
void iris_timing_adapter::vadd_eg_write_totals(std::ostream&out)const{
 if(profile_.empirical_vadd_eg)out<<",\"vadd_EG_counter_CSR_scope\":\"readonly machine/user cycle-instret CSRRS-CSRRC and immediate zero source; existing CPU counter EX-COM predicates; no VADD numeric-tail drain; other CSR/FENCE dependencies unchanged\"";
 out<<",\"vadd_EG_scope\":\"optional savedCompute128 integerVADD.VV SEW8/16/32/64 fullVLmax unmasked defined operands; VS alreadydirty; perEG modular result; no FCSR effects; VDQ4-IQ3-perEG-sourcewrites; COMplus1 bridge unqualified; scalarALU/CFI overlap; independent cycle-instret CSR/ALU/CFI overlap; all other consumers drain; opaque wrongpath front tokens never enqueue; no exact wrongpath CPU-VU timing or physical-traffic claim\",\"vadd_EG_metrics\":[";
 for(unsigned h=0;h<vadd_eg_pending_.size();++h){if(h)out<<',';out<<"{\"accepted\":"<<vadd_eg_accepted_[h]<<",\"microissues\":"<<vadd_eg_issued_[h]<<",\"physical_16B_writes\":"<<vadd_eg_writes_[h]<<",\"preCOM_killed\":"<<vadd_eg_killed_[h]<<",\"peak\":"<<vadd_eg_peak_[h]<<",\"pending\":"<<vadd_eg_pending_[h].size()<<'}';}out<<']';
}

// Independent readonly counters deliberately do not use this FENCE predicate.
bool iris_timing_adapter::vadd_eg_boundary_wait(unsigned h,const insn_fetch_t&fetch){
 if(h>=2)return false;auto i=fetch.insn;const auto raw=uint32_t(i.bits());
 if(vadd_eg_is_vv(&fetch)||vadd_eg_scalar_allowed(fetch))return false;
 if(!vadd_eg_pending_[h].empty()||!vadd_eg_queues_[h].empty()||vadd_eg_clock_active_[h])return true;
 const auto d=profile_.harts[h].divider;const auto last=vadd_eg_last_edge_[h];
 if(last&&clock_.now()%d==0&&*last==clock_.now()/d&&vadd_eg_prebusy_[h]){
  if(clock_.now()>UINT64_MAX-d)throw std::overflow_error("IRIS_VADD_EG_FENCE_EDGE_HORIZON");
  opu_fence_retry_[h]=clock_.now()+d;return true;
 }
 return false;
}
