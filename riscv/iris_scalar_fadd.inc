// Finite scalar FADD control. Source: ShuttleFPPipe l4 and configured Rocket
// FPU l3; memory/shared-CP/non-FADD domains retain an explicit generic drain.
bool iris_timing_adapter::scalar_fadd_candidate(unsigned h,const iris::shuttle::Uop&u)const {
 if(!profile_.empirical_scalar_fadd)return false;
 const auto raw=u.expanded,op=raw&0xfe00007f;
 if(op!=0x53&&op!=0x02000053&&op!=0x04000053)return false;
 const auto*s=cores_[h]->get_state();const auto rm=(raw>>12)&7;
 if(s->prv!=PRV_M||s->v||s->debug_mode||!(s->mstatus->read()&MSTATUS_FS)||rm==5||rm==6)return false;
 if(rm==7&&(s->frm->iris_known_bits()&7)==7&&s->frm->read()>4)return false;
 if(profile_.empirical_async&&empirical_async_[h])return false;
 return u.control_verified&&!u.exception;
}
bool iris_timing_adapter::scalar_fadd_pending(unsigned h)const {
 if(!profile_.empirical_scalar_fadd)return false;
 for(const auto&a:scalar_fadd_[h])if(!a->done&&(!a->killed||a->accepted))return true;
 return false;
}
bool iris_timing_adapter::scalar_fadd_defer_irq(unsigned h){
 if(!scalar_fadd_pending(h)||!cores_[h]->iris_pipeline_interrupt_exception())return false;
 if(scalar_fadd_last_irq_[h]!=std::optional<Cycle>(clock_.now())){scalar_fadd_last_irq_[h]=clock_.now();++scalar_fadd_irq_deferrals_[h];if(async_trace_)*async_trace_<<"{\"event\":\"scalar_fadd_irq_drain\",\"hart\":"<<h<<",\"cycle\":"<<clock_.now()<<"}\n";}
 return true;
}
iris_timing_adapter::Cycle iris_timing_adapter::scalar_fadd_release(unsigned h,const iris::shuttle::Uop&u,Cycle base)const {
 if(!profile_.empirical_scalar_fadd)return base;
 const bool fadd=scalar_fadd_candidate(h,u),csr=h<2&&source_counter_read(u);
 if(!fadd&&!csr)return base;
 const auto d=profile_.harts[h].divider;
 for(const auto&a:scalar_fadd_[h])if(!a->done&&!a->killed){
  const bool dependency=csr||u.rs1==a->rd||u.rs2==a->rd||u.rd==a->rd;
  if(dependency)base=std::max(base,h<2?future_cycle(a->write,d,1):a->write);
 }
 return base;
}
void iris_timing_adapter::scalar_fadd_reserve(unsigned h,size_t id){
 auto&r=pure_[h].instructions.at(id);auto a=std::make_shared<ScalarFaddActor>();
 a->hart=h;a->instruction=id;a->pc=r.pc;a->rd=r.uop.rd;a->rs1=r.uop.rs1;a->rs2=r.uop.rs2;
 a->width=((r.uop.expanded>>25)&3)==0?32:((r.uop.expanded>>25)&3)==1?64:16;a->rm=(r.uop.expanded>>12)&7;
 a->ex=r.ex_release;a->write=future_cycle(a->ex,profile_.harts[h].divider,h<2?4:3);
 auto&v=scalar_fadd_[h];v.erase(std::remove_if(v.begin(),v.end(),[](const auto&x){return x->done||x->killed&&!x->accepted;}),v.end());
 if(v.size()>=8)throw std::logic_error("IRIS_SCALAR_FADD_LOGICAL_CAPACITY");v.push_back(a);r.scalar_fadd=a;
}
void iris_timing_adapter::scalar_fadd_ex(unsigned h,size_t id){
 auto&r=pure_[h].instructions.at(id);auto a=r.scalar_fadd;
 if(!a||a->killed||r.squashed||clock_.now()!=a->ex)throw std::logic_error("IRIS_SCALAR_FADD_EX_OWNER");
 auto*core=cores_[h];
 a->source1=core->get_state()->FPR.read_transport(a->rs1);a->source2=core->get_state()->FPR.read_transport(a->rs2);
 if(a->rm==7)a->frm=core->get_state()->frm->read_defined(a->pc);
 a->accepted=true;++scalar_fadd_accepted_[h];unsigned active=0;for(const auto&x:scalar_fadd_[h])active+=x->accepted&&!x->done;
 scalar_fadd_peak_[h]=std::max<uint64_t>(scalar_fadd_peak_[h],active);if(active>(h<2?4:3))throw std::logic_error("IRIS_SCALAR_FADD_PHYSICAL_PIPE_CAPACITY");
 const auto d=profile_.harts[h].divider;iris::Op op{h,"source.scalar-FADD.fp"+std::to_string(a->width),"source.scalarFPU"+std::to_string(h),a->write-a->ex,d};
 op.pc=a->pc;op.retires=false;op.issue_period=d;op.cancellable=false;op.on_complete=[this,a]{scalar_fadd_write(a);};a->node=clock_.issue(std::move(op));
 if(async_trace_)*async_trace_<<"{\"event\":\"scalar_fadd_EX\",\"hart\":"<<h<<",\"instruction\":"<<id<<",\"pc\":"<<a->pc<<",\"cycle\":"<<a->ex<<",\"write\":"<<a->write<<",\"node\":"<<*a->node<<"}\n";
}
void iris_timing_adapter::scalar_fadd_before(unsigned h,size_t id){
 auto a=pure_[h].instructions.at(id).scalar_fadd;auto*c=cores_[h];auto*s=c->get_state();
 if(!a||!a->accepted||a->killed||a->retired||c->iris_scalar_fp_exception_capture)throw std::logic_error("IRIS_SCALAR_FADD_COM_OWNER");
 c->iris_read_fpr(a->rs1,a->pc);c->iris_read_fpr(a->rs2,a->pc);
 const auto equal=[](const auto&x,const auto&y){return !std::memcmp(&x.value,&y.value,8)&&std::equal(x.known.begin(),x.known.begin()+8,y.known.begin());};
 if(!equal(a->source1,s->FPR.read_transport(a->rs1))||!equal(a->source2,s->FPR.read_transport(a->rs2)))throw std::logic_error("IRIS_SCALAR_FADD_EX_COM_OPERAND_CHANGED");
 if(a->rm==7&&s->frm->read_defined(a->pc)!=a->frm)throw std::logic_error("IRIS_SCALAR_FADD_EX_COM_FRM_CHANGED");
 a->before=s->FPR.read_transport(a->rd);a->flags_before=s->fflags->read();a->flags_known_before=s->fflags->iris_known_bits();a->fs_before=s->mstatus->read()&MSTATUS_FS;c->iris_scalar_fp_exception_capture=0;
}
void iris_timing_adapter::scalar_fadd_after(unsigned h,size_t id,bool retired){
 auto a=pure_[h].instructions.at(id).scalar_fadd;auto*c=cores_[h];auto*s=c->get_state();
 if(!c->iris_scalar_fp_exception_capture)throw std::logic_error("IRIS_SCALAR_FADD_FLAGS_CAPTURE_MISSING");
 a->delta_flags=*c->iris_scalar_fp_exception_capture;c->iris_scalar_fp_exception_capture.reset();a->after=s->FPR.read_transport(a->rd);
 s->FPR.write_transport(a->rd,a->before);s->fflags->iris_restore_snapshot(a->flags_before,a->flags_known_before);s->mstatus->iris_restore_fs_snapshot(a->fs_before);
 if(!retired){scalar_fadd_cancel(h,id);return;}a->retired=true;
 if(async_trace_)*async_trace_<<"{\"event\":\"scalar_fadd_COM\",\"hart\":"<<h<<",\"instruction\":"<<id<<",\"cycle\":"<<clock_.now()<<",\"flags\":"<<a->delta_flags<<"}\n";
}
void iris_timing_adapter::scalar_fadd_cancel(unsigned h,size_t id){
 auto a=pure_[h].instructions.at(id).scalar_fadd;if(!a||a->killed)return;
 if(a->retired)throw std::logic_error("IRIS_RETIRED_SCALAR_FADD_CANNOT_KILL");a->killed=true;++scalar_fadd_killed_[h];if(!a->accepted)a->done=true;
}
void iris_timing_adapter::scalar_fadd_write(const std::shared_ptr<ScalarFaddActor>&a){
 if(!a->accepted||a->done||clock_.now()!=a->write)throw std::logic_error("IRIS_SCALAR_FADD_WRITE_PHASE");
 a->done=true;if(a->killed)return;if(!a->retired)throw std::logic_error("IRIS_SCALAR_FADD_WRITE_BEFORE_COM");
 auto*s=cores_[a->hart]->get_state();if(!(s->mstatus->read()&MSTATUS_FS))throw std::runtime_error("IRIS_SCALAR_FADD_PENDING_FS_CHANGE_UNMODELED");
 s->FPR.write_transport(a->rd,a->after);if(a->delta_flags)s->fflags->accumulate(a->delta_flags);s->sstatus->dirty(SSTATUS_FS);++scalar_fadd_published_[a->hart];
 if(async_trace_)*async_trace_<<"{\"event\":\"scalar_fadd_FPR_WRITE\",\"hart\":"<<a->hart<<",\"instruction\":"<<a->instruction<<",\"pc\":"<<a->pc<<",\"cycle\":"<<clock_.now()<<",\"flags\":"<<a->delta_flags<<"}\n";
}
