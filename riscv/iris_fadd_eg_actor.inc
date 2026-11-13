// Optional finite source-control integration. Successful COM makes a command
// available at COM+1; that CPU bridge is conservative and not RTL-qualified.
namespace {std::string fadd_eg_guest_context(unsigned h,processor_t*core,uint64_t pc,uint32_t raw){
 const auto*s=core->get_state();const auto&v=core->VU;std::ostringstream out;out<<" hart="<<h<<" pc="<<pc<<" raw="<<raw<<" VL="<<v.vl->read()<<" SEW="<<v.vsew<<" LMUL="<<v.vflmul<<" frm="<<s->frm->read()<<" flags="<<s->fflags->read()<<" mstatus="<<s->mstatus->read()<<" mie="<<s->mie->read()<<" mip="<<s->mip->read();return out.str();
}}
bool iris_timing_adapter::fadd_eg_is_vv(const insn_fetch_t*f)const{
 if(!f)return false;auto i=f->insn;return i.length()==4&&(uint32_t(i.bits())&0xfc00707f)==0x1057;
}
iris::rvv_fadd_source::Command iris_timing_adapter::fadd_eg_geometry(unsigned h,const insn_fetch_t&f,uint64_t id)const{
 auto&v=cores_[h]->VU;const auto*s=cores_[h]->get_state();auto i=f.insn;const auto raw=uint32_t(i.bits());
 if(h>=2||!fadd_eg_is_vv(&f)||!(raw&(1u<<25))||v.vill||v.vstart->read()||v.altfmt||v.vlenb!=32||
    (v.vsew!=16&&v.vsew!=32&&v.vsew!=64)||(v.vflmul!=1&&v.vflmul!=2&&v.vflmul!=4&&v.vflmul!=8)||v.vl->read()!=v.vlmax)
  throw std::runtime_error(std::string("IRIS_FADD_EG_FULLVL_HSD_UNMASKED_SCOPE")+fadd_eg_guest_context(h,cores_[h],s->pc,raw));
 if(s->prv!=PRV_M||s->v||s->debug_mode||!(s->mstatus->read()&MSTATUS_VS)||(s->mstatus->read()&MSTATUS_FS)!=MSTATUS_FS||
    s->frm->read()!=0||(s->frm->iris_known_bits()&7)!=7||(s->fflags->iris_known_bits()&31)!=31)
  throw std::runtime_error(std::string("IRIS_FADD_EG_MMODE_RNE_KNOWN_FLAGS_FS_ALREADY_DIRTY_SCOPE")+fadd_eg_guest_context(h,cores_[h],s->pc,raw));
 if((s->mstatus->read()&MSTATUS_MIE)||(s->mie->read()&s->mip->read()))throw std::runtime_error(std::string("IRIS_FADD_EG_IRQ_CONTEXT_UNMODELED")+fadd_eg_guest_context(h,cores_[h],s->pc,raw));
 iris::rvv_fadd_source::Command c{id,unsigned(id%32),unsigned(raw>>7&31),unsigned(raw>>15&31),unsigned(raw>>20&31),unsigned(v.vsew),unsigned(v.vflmul)};
 try{iris::rvv_fadd_source::Scheduler::validate(c);}catch(const std::invalid_argument&){throw std::runtime_error(std::string("IRIS_FADD_EG_REGISTER_GROUP_SCOPE")+fadd_eg_guest_context(h,cores_[h],s->pc,raw));}return c;
}
// Unretired CPU-front reservations have no VU/VRF side effects. An opaque
// token protects a speculative unqualified FADD until its older CFI resolves.
// Its placeholder only tests future FIFO input capacity; it must never be
// accepted into the source controller or used for functional arithmetic.
iris::rvv_fadd_source::Command iris_timing_adapter::fadd_eg_reservation_geometry(unsigned h,const insn_fetch_t&f,uint64_t id,bool&opaque)const{
 opaque=false;
 try{return fadd_eg_geometry(h,f,id);}
 catch(const std::runtime_error&e){const std::string message=e.what();if(!message.starts_with("IRIS_FADD_EG_FULLVL_HSD_UNMASKED_SCOPE ")&&!message.starts_with("IRIS_FADD_EG_MMODE_RNE_KNOWN_FLAGS_FS_ALREADY_DIRTY_SCOPE ")&&!message.starts_with("IRIS_FADD_EG_IRQ_CONTEXT_UNMODELED ")&&!message.starts_with("IRIS_FADD_EG_REGISTER_GROUP_SCOPE "))throw;}
 catch(const std::invalid_argument&e){if(std::string(e.what())!="FADD_SOURCE_FINITE_GEOMETRY")throw;}
 opaque=true;return iris::rvv_fadd_source::Command{id,unsigned(id%32),8,16,24,32,1};
}
std::shared_ptr<iris_timing_adapter::FaddEgOwner>iris_timing_adapter::fadd_eg_find(unsigned h,size_t id)const{
 if(h>=fadd_eg_pending_.size())return{};for(const auto&a:fadd_eg_pending_[h])if(a->actor->instruction==id)return a;return{};
}
bool iris_timing_adapter::fadd_eg_can_dispatch(unsigned h,const insn_fetch_t&fetch)const{
 const auto divider=profile_.harts[h].divider,now=clock_.now()/divider,available=now+4;
 if(clock_.now()%divider)throw std::logic_error("IRIS_FADD_EG_UNALIGNED_ADMISSION");
 bool opaque=false;auto candidate=fadd_eg_reservation_geometry(h,fetch,fadd_eg_generation_[h]+1,opaque);auto q=fadd_eg_queues_[h];const auto last=fadd_eg_last_edge_[h];
 auto begin=last?*last+1:now;
 if(q.empty()){begin=now;for(const auto&a:fadd_eg_pending_[h])if(!a->queued)begin=std::min(begin,a->available);if(last)begin=std::max(begin,*last+1);}
 for(auto edge=begin;edge<=available;++edge){
  std::optional<iris::rvv_fadd_source::Command>input;
  for(const auto&a:fadd_eg_pending_[h])if(!a->queued&&a->available==edge){if(input)throw std::logic_error("IRIS_FADD_EG_MULTIPLE_COM_SLOTS");input=a->command;}
  if(edge==available){if(input)return false;input=candidate;}
  auto result=q.step(edge,input);if(input&&!result.input_fire){if(edge==available)return false;throw std::logic_error("IRIS_FADD_EG_PRIOR_RESERVATION_OVERRUN");}
 }
 return true;
}
void iris_timing_adapter::fadd_eg_start_clock(unsigned h){
 if(fadd_eg_clock_active_[h])return;auto divider=profile_.harts[h].divider;
 iris::Op tick{h,"source.fadd.EG.queue.edge","source.fadd.EG.clock"+std::to_string(h),divider,divider};
 tick.retires=false;tick.cancellable=false;tick.issue_period=divider;tick.earliest=clock_.now();
 tick.on_complete=[this,h]{fadd_eg_clock_active_[h]=false;fadd_eg_tick(h);};fadd_eg_clock_active_[h]=true;clock_.issue(std::move(tick));
}
void iris_timing_adapter::fadd_eg_begin(unsigned h,size_t id){
 auto&r=pure_[h].instructions.at(id);if(!empirical_async_can_dispatch(h,&r.fetch))throw std::logic_error("IRIS_FADD_EG_UNRESERVED_FRONT");
 if(fadd_eg_pending_[h].empty()){
  if(!fadd_eg_queues_[h].empty())throw std::logic_error("IRIS_FADD_EG_ORPHAN_SOURCE_QUEUE");
  fadd_eg_physical_versions_[h].fill(0);fadd_eg_logical_versions_[h].fill(0);++fadd_eg_epoch_[h];
 }
 auto a=std::make_shared<FaddEgOwner>();a->actor=std::make_shared<EmpiricalAsync>();a->actor->instruction=id;a->actor->com_cycle=r.com_cycle;a->actor->stages_fp=true;
 a->command=fadd_eg_reservation_geometry(h,r.fetch,++fadd_eg_generation_[h],a->opaque_front);a->pc=r.pc;a->raw=uint32_t(r.fetch.insn.bits());a->epoch=fadd_eg_epoch_[h];a->available=r.com_cycle/profile_.harts[h].divider+1;a->remaining=a->command.beats();
 if(r.com_cycle!=clock_.now()+3*profile_.harts[h].divider)throw std::logic_error("IRIS_FADD_EG_FIXED_COM_PHASE_SCOPE");
 fadd_eg_pending_[h].push_back(a);empirical_async_[h]=fadd_eg_pending_[h].front()->actor;++fadd_eg_accepted_[h];fadd_eg_peak_[h]=std::max<uint64_t>(fadd_eg_peak_[h],fadd_eg_pending_[h].size());
 fadd_eg_start_clock(h);
 if(async_trace_)*async_trace_<<"{\"event\":\"fadd_EG_front_reservation\",\"hart\":"<<h<<",\"instruction\":"<<id<<",\"generation\":"<<a->command.id<<",\"pc\":"<<a->pc<<",\"RRD\":"<<clock_.now()<<",\"COM\":"<<r.com_cycle<<",\"available\":"<<a->available*profile_.harts[h].divider<<"}\n";
}
void iris_timing_adapter::fadd_eg_before(unsigned h,const std::shared_ptr<FaddEgOwner>&a){
 auto&v=cores_[h]->VU;auto*s=cores_[h]->get_state();auto&r=pure_[h].instructions.at(a->actor->instruction);
 auto c=fadd_eg_geometry(h,r.fetch,a->command.id);if(a->opaque_front)throw std::runtime_error(std::string("IRIS_FADD_EG_RRD_TO_COM_GEOMETRY_CHANGE_UNMODELED")+fadd_eg_guest_context(h,cores_[h],a->pc,a->raw));if(c.vd!=a->command.vd||c.vs1!=a->command.vs1||c.vs2!=a->command.vs2||c.sew!=a->command.sew||c.lmul!=a->command.lmul)throw std::runtime_error(std::string("IRIS_FADD_EG_CONFIGURATION_CHANGED_BEFORE_COM")+fadd_eg_guest_context(h,cores_[h],a->pc,a->raw));
 auto&actor=*a->actor;actor.before_vrf.resize(v.vlenb*32);std::memcpy(actor.before_vrf.data(),v.reg_file,actor.before_vrf.size());actor.before_vrf_known=v.iris_vrf_definedness;
 actor.before_fflags=s->fflags->read();actor.before_fflags_known=s->fflags->iris_known_bits();actor.before_fs=s->mstatus->read()&MSTATUS_FS;
 // Construct logical operand versions privately. Unknown operands refuse
 // before any projection into the functional core's synchronous COM oracle.
 a->input_vrf=actor.before_vrf;a->input_known=actor.before_vrf_known;
 auto required=[&](size_t off){for(unsigned base:{a->command.vd,a->command.vs1,a->command.vs2})if(off>=32*base&&off<32*(base+a->command.lmul))return true;return false;};
 for(const auto&older:fadd_eg_pending_[h]){
  if(older==a)break;if(!older->actor->retired)throw std::logic_error("IRIS_FADD_EG_COM_ORDER");
  for(unsigned eg=0;eg<older->command.beats();++eg){size_t off=32*older->command.vd+16*eg;if(required(off)){std::memcpy(a->input_vrf.data()+off,older->actor->after_vrf.data()+off,16);a->input_known.write(off,older->actor->after_vrf_known.read(off,16));}}
 }
 try{for(unsigned base:{a->command.vs1,a->command.vs2})a->input_known.require(32*base,32*a->command.lmul,{h,a->pc,"source-FADD-EG-operand"});}catch(const std::runtime_error&e){throw std::runtime_error(std::string(e.what())+fadd_eg_guest_context(h,cores_[h],a->pc,a->raw));}
 a->read_versions=fadd_eg_logical_versions_[h];a->before_versions=fadd_eg_logical_versions_[h];a->after_versions=a->before_versions;
 for(unsigned i=0;i<a->command.beats();++i){unsigned eg=2*a->command.vd+i;a->after_versions[eg]=++fadd_eg_logical_versions_[h][eg];}
 // Isolate newly raised IEEE exception bits even if architectural flags were
 // already set. A zero aggregate proves every per-EG local flag delta is zero.
 std::memcpy(v.reg_file,a->input_vrf.data(),a->input_vrf.size());v.iris_vrf_definedness=a->input_known;
 s->fflags->iris_restore_snapshot(0,actor.before_fflags_known);
}
void iris_timing_adapter::fadd_eg_after(unsigned h,const std::shared_ptr<FaddEgOwner>&a,bool retired){
 auto&v=cores_[h]->VU;auto*s=cores_[h]->get_state();auto&actor=*a->actor;
 actor.after_vrf.resize(v.vlenb*32);std::memcpy(actor.after_vrf.data(),v.reg_file,actor.after_vrf.size());actor.after_vrf_known=v.iris_vrf_definedness;
 const auto local_flags=s->fflags->read(),local_known=s->fflags->iris_known_bits(),after_fs=s->mstatus->read()&MSTATUS_FS;
 std::memcpy(v.reg_file,actor.before_vrf.data(),actor.before_vrf.size());v.iris_vrf_definedness=actor.before_vrf_known;
 s->fflags->iris_restore_snapshot(actor.before_fflags,actor.before_fflags_known);s->mstatus->iris_restore_fs_snapshot(actor.before_fs);
 if(!retired){fadd_eg_cancel(h,a);return;}
 if(local_flags||(local_known&31)!=31)throw std::runtime_error(std::string("IRIS_FADD_EG_NEW_EXCEPTION_FLAGS_UNSUPPORTED")+fadd_eg_guest_context(h,cores_[h],a->pc,a->raw)+" new_flags="+std::to_string(local_flags));
 if(after_fs!=actor.before_fs)throw std::runtime_error(std::string("IRIS_FADD_EG_FS_TRANSITION_UNSUPPORTED")+fadd_eg_guest_context(h,cores_[h],a->pc,a->raw));
 const size_t begin=32*a->command.vd,end=begin+32*a->command.lmul;
 for(size_t i=0;i<a->input_vrf.size();++i)if(i<begin||i>=end)if(actor.after_vrf[i]!=a->input_vrf[i]||actor.after_vrf_known.byte(i)!=a->input_known.byte(i))throw std::logic_error("IRIS_FADD_EG_UNEXPECTED_VRF_WRITE");
 if(clock_.now()!=actor.com_cycle)throw std::logic_error("IRIS_FADD_EG_COM_PHASE_CHANGED");actor.retired=true;fadd_eg_start_clock(h);
 if(async_trace_)*async_trace_<<"{\"event\":\"fadd_EG_functional_COM\",\"hart\":"<<h<<",\"generation\":"<<a->command.id<<",\"pc\":"<<a->pc<<",\"cycle\":"<<clock_.now()<<",\"new_flags\":0,\"physical_VRF_restored\":true}\n";
}
void iris_timing_adapter::fadd_eg_tick(unsigned h){
 const auto divider=profile_.harts[h].divider,edge=clock_.now()/divider;
 if(clock_.now()%divider)throw std::logic_error("IRIS_FADD_EG_UNALIGNED_EDGE");
 std::shared_ptr<FaddEgOwner>input;for(const auto&a:fadd_eg_pending_[h])if(!a->queued&&a->available<=edge){if(input||a->available!=edge||!a->actor->retired||a->opaque_front)throw std::logic_error("IRIS_FADD_EG_COM_INPUT_PHASE");input=a;}
 auto result=fadd_eg_queues_[h].step(edge,input?std::optional<iris::rvv_fadd_source::Command>(input->command):std::nullopt);fadd_eg_last_edge_[h]=edge;
 if(input){if(!result.input_fire)throw std::logic_error("IRIS_FADD_EG_RESERVED_INPUT_NOT_READY");input->queued=true;}
 auto owner=[&](uint64_t generation){for(const auto&a:fadd_eg_pending_[h])if(a->command.id==generation)return a;throw std::logic_error("IRIS_FADD_EG_UNOWNED_SOURCE_EVENT");};
 auto&v=cores_[h]->VU;
 if(result.issue){const auto&m=*result.issue;auto a=owner(m.command.id);if(!a->actor->retired||!a->queued||a->epoch!=fadd_eg_epoch_[h])throw std::logic_error("IRIS_FADD_EG_ISSUE_OWNER");
  for(unsigned eg:{m.source1,m.source2}){size_t off=16*eg;if(fadd_eg_physical_versions_[h][eg]!=a->read_versions[eg]||std::memcmp(v.reg_file+off,a->input_vrf.data()+off,16)||v.iris_vrf_definedness.read(off,16)!=a->input_known.read(off,16))throw std::logic_error("IRIS_FADD_EG_SOURCE_VERSION_AT_READ");}
  ++fadd_eg_issued_[h];if(async_trace_)*async_trace_<<"{\"event\":\"fadd_EG_microissue\",\"hart\":"<<h<<",\"generation\":"<<a->command.id<<",\"pc\":"<<a->pc<<",\"cycle\":"<<clock_.now()<<",\"index\":"<<m.index<<",\"destination_EG\":"<<m.destination<<"}\n";
 }
 if(result.write){const auto&m=*result.write;auto a=owner(m.command.id);const size_t off=16*m.destination;
  if(!a->actor->retired||!a->remaining||a->epoch!=fadd_eg_epoch_[h]||fadd_eg_physical_versions_[h][m.destination]!=a->before_versions[m.destination]||std::memcmp(v.reg_file+off,a->input_vrf.data()+off,16)||v.iris_vrf_definedness.read(off,16)!=a->input_known.read(off,16))throw std::logic_error("IRIS_FADD_EG_DESTINATION_VERSION_AT_WRITE");
  std::memcpy(v.reg_file+off,a->actor->after_vrf.data()+off,16);v.iris_vrf_definedness.write(off,a->actor->after_vrf_known.read(off,16));fadd_eg_physical_versions_[h][m.destination]=a->after_versions[m.destination];
  ++fadd_eg_writes_[h];--a->remaining;
  iris::PhysicalOp point{h,"source.fadd.EG.write","source.fadd.EG.write"+std::to_string(h),a->pc,16,0,{},"saved Compute128 FADD EG controller; CPU COMplus1 bridge unqualified; flags0",true};clock_.record_physical_edge(std::move(point));
  if(async_trace_)*async_trace_<<"{\"event\":\"fadd_EG_physical_write\",\"hart\":"<<h<<",\"generation\":"<<a->command.id<<",\"pc\":"<<a->pc<<",\"cycle\":"<<clock_.now()<<",\"index\":"<<m.index<<",\"bytes\":16,\"version\":"<<a->after_versions[m.destination]<<"}\n";
  if(!a->remaining){a->actor->done=true;auto&pending=fadd_eg_pending_[h];pending.erase(std::find(pending.begin(),pending.end(),a));empirical_async_[h]=pending.empty()?nullptr:pending.front()->actor;}
 }
 bool waiting=false;for(const auto&a:fadd_eg_pending_[h])waiting|=!a->queued;
 if(waiting||!fadd_eg_queues_[h].empty())fadd_eg_start_clock(h);
}
void iris_timing_adapter::fadd_eg_cancel(unsigned h,const std::shared_ptr<FaddEgOwner>&a){
 if(a->actor->retired||a->queued)throw std::logic_error("IRIS_FADD_EG_ACCEPTED_SOURCE_WORK_NOT_CANCELLABLE");
 if(!a->input_vrf.empty())for(unsigned i=0;i<a->command.beats();++i){unsigned eg=2*a->command.vd+i;if(fadd_eg_logical_versions_[h][eg]!=a->after_versions[eg])throw std::logic_error("IRIS_FADD_EG_FAILED_COM_LOGICAL_VERSION");fadd_eg_logical_versions_[h][eg]=a->before_versions[eg];}
 auto&pending=fadd_eg_pending_[h];auto it=std::find(pending.begin(),pending.end(),a);if(it==pending.end())throw std::logic_error("IRIS_FADD_EG_CANCEL_OWNER");pending.erase(it);++fadd_eg_killed_[h];empirical_async_[h]=pending.empty()?nullptr:pending.front()->actor;
 if(async_trace_)*async_trace_<<"{\"event\":\"fadd_EG_wrongpath_cancel\",\"hart\":"<<h<<",\"generation\":"<<a->command.id<<",\"pc\":"<<a->pc<<",\"cycle\":"<<clock_.now()<<"}\n";
}
void iris_timing_adapter::fadd_eg_check_irq()const{
 for(unsigned h=0;h<2;++h)if(std::any_of(fadd_eg_pending_[h].begin(),fadd_eg_pending_[h].end(),[](const auto&a){return a->actor->retired;})){const auto*s=cores_[h]->get_state();if((s->mstatus->read()&MSTATUS_MIE)||(s->mie->read()&s->mip->read()))throw std::runtime_error(std::string("IRIS_FADD_EG_ACTIVE_IRQ_CONTEXT_UNMODELED")+fadd_eg_guest_context(h,cores_[h],fadd_eg_pending_[h].front()->pc,fadd_eg_pending_[h].front()->raw));}
}
void iris_timing_adapter::fadd_eg_write_totals(std::ostream&out)const{
 out<<",\"fadd_EG_scope\":\"optional savedCompute128 VFADD.VV IEEEHSD fullVLmax unmasked RNE defined operands; FS already dirty; isolated newflags0 oracle; VDQ4-IQ3-perEG-sourcewrites; COMplus1 bridge unqualified; scalarALU/CFI overlap; otherCSR-memory-vector boundaries drain; opaque wrongpath front tokens never enqueue; no exact wrongpath CPU-VU timing or physical-traffic claim\",\"fadd_EG_metrics\":[";
 for(unsigned h=0;h<fadd_eg_pending_.size();++h){if(h)out<<',';out<<"{\"accepted\":"<<fadd_eg_accepted_[h]<<",\"microissues\":"<<fadd_eg_issued_[h]<<",\"physical_16B_writes\":"<<fadd_eg_writes_[h]<<",\"preCOM_killed\":"<<fadd_eg_killed_[h]<<",\"peak\":"<<fadd_eg_peak_[h]<<",\"pending\":"<<fadd_eg_pending_[h].size()<<'}';}out<<']';
}
