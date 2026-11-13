// Experimental non-memory compute timing: front retirement is distinct from
// numeric publication. A bounded second owner requires prior publication by EX.
bool iris_timing_adapter::empirical_async_can_dispatch(unsigned hart,const insn_fetch_t*candidate)const{
 if(profile_.empirical_fadd_eg&&hart<2){
   if(!fadd_eg_pending_[hart].empty())return candidate&&fadd_eg_is_vv(candidate)&&fadd_eg_can_dispatch(hart,*candidate);
   if(fadd_eg_is_vv(candidate))return !empirical_async_[hart]&&fadd_eg_can_dispatch(hart,*candidate);
 }
 if(profile_.empirical_opu_entry){
  const bool mm=hart<2&&opu_is_mm(candidate);const auto&active=opu_pending_[hart];
  if(!active.empty())return mm&&opu_can_dispatch(hart);
  if(mm&&empirical_async_[hart])return false;
  if(mm)return opu_can_dispatch(hart);
 }
 const auto&head=empirical_async_[hart];if(!head)return true;
 if(!profile_.empirical_async_two_owner||empirical_async_next_[hart]||!head->backend)return false;
 // A newly accepted command reaches source EX one edge after RRD. Admit a
 // bounded successor only if the older functional result is guaranteed to be
 // published by that edge, including its separate architectural COM.
 const auto edge=clock_.now()+profile_.harts[hart].divider;const auto&node=clock_.nodes().at(*head->backend);
 return head->com_cycle<=edge&&(head->done||(node.issued&&!node.cancelled&&node.end<=edge));
}
void iris_timing_adapter::empirical_async_begin(unsigned hart,size_t instruction){
 if(profile_.empirical_fadd_eg&&hart<2&&fadd_eg_is_vv(&pure_[hart].instructions.at(instruction).fetch)){fadd_eg_begin(hart,instruction);return;}
 if(profile_.empirical_opu_entry&&hart<2&&opu_is_mm(&pure_[hart].instructions.at(instruction).fetch)){opu_begin(hart,instruction);return;}
 auto&p=pure_[hart];auto&r=p.instructions.at(instruction);
 if(!empirical_async_can_dispatch(hart))throw std::logic_error("IRIS_EMPIRICAL_BACKEND_OWNER_BUSY");
 auto work=empirical_feature(hart,r.fetch);auto actor=std::make_shared<EmpiricalAsync>();actor->instruction=instruction;actor->com_cycle=r.com_cycle;actor->feature=work;actor->stages_fp=work.family.starts_with("rvv.fadd.");
 double duration=std::max<uint64_t>(1,work.work);Cycle interval=1;std::string resource=(actor->stages_fp?(hart==2?"empirical.sharedFPU":"empirical.vectorFP"):work.family.starts_with("vme.")?"empirical.vme":"empirical.vector")+std::to_string(hart);
 for(const auto&rule:profile_.empirical_rules)if(rule.hart==hart&&rule.family==work.family){duration+=rule.setup+rule.work*work.work;interval=rule.interval;resource=rule.resource;break;}
 if(!std::isfinite(duration)||duration>profile_.max_cycles)throw std::runtime_error("IRIS_EMPIRICAL_COST_OUTSIDE_HORIZON");
 iris::Op op{hart,"empirical.async."+work.family,resource,uint64_t(std::ceil(duration))*profile_.harts[hart].divider,interval*profile_.harts[hart].divider};op.retires=false;op.pc=r.pc;op.bytes=work.bytes;op.macs=work.macs;op.issue_period=profile_.harts[hart].divider;op.earliest=clock_.now()+profile_.harts[hart].divider;op.cancellable=true;
 op.on_complete=[this,hart,actor]{actor->done=true;empirical_async_publish(hart,actor);};r.empirical_backend=clock_.issue(std::move(op));actor->backend=r.empirical_backend;
 if(async_trace_){auto&out=*async_trace_;out<<"{\"event\":\"begin\",\"hart\":"<<hart<<",\"instruction\":"<<instruction<<",\"pc\":"<<r.pc<<",\"rrd\":"<<clock_.now()<<",\"ex\":"<<clock_.now()+profile_.harts[hart].divider<<",\"com\":"<<actor->com_cycle<<",\"backend_node\":"<<*actor->backend;if(empirical_async_[hart]){const auto&head=empirical_async_[hart];const auto&node=clock_.nodes().at(*head->backend);out<<",\"prior_instruction\":"<<head->instruction<<",\"prior_backend_node\":"<<*head->backend<<",\"prior_com\":"<<head->com_cycle<<",\"prior_backend_end\":"<<(head->done?clock_.now():node.end);}out<<"}\n";}
 if(empirical_async_[hart]){empirical_async_next_[hart]=std::move(actor);++empirical_async_handoffs_[hart];}else empirical_async_[hart]=std::move(actor);
}
void iris_timing_adapter::empirical_async_before(unsigned hart,size_t instruction){
 if(profile_.empirical_fadd_eg)if(auto a=fadd_eg_find(hart,instruction)){fadd_eg_before(hart,a);return;}
 if(profile_.empirical_opu_entry)if(auto actor=opu_find(hart,instruction)){opu_before(hart,actor);return;}
 auto actor=empirical_async_[hart];if(!actor||actor->instruction!=instruction)throw std::logic_error("IRIS_EMPIRICAL_BACKEND_COM_OWNER");auto&v=cores_[hart]->VU;
 actor->before_vrf.resize(v.vlenb*32);std::memcpy(actor->before_vrf.data(),v.reg_file,actor->before_vrf.size());actor->before_vrf_known=v.iris_vrf_definedness;
 if(actor->stages_fp){const auto*state=cores_[hart]->get_state();if(state->v||state->prv!=PRV_M)throw std::runtime_error("IRIS_EMPIRICAL_FADD_PRIVILEGE_SCOPE");actor->before_fflags=state->fflags->read();actor->before_fflags_known=state->fflags->iris_known_bits();actor->before_fs=state->mstatus->read()&MSTATUS_FS;}
 if(actor->feature.family.starts_with("vme.")){actor->before_mrf=v.mt;actor->before_mrf_known=v.iris_tile_definedness;actor->before_initialized=v.iris_initialized;}
}
void iris_timing_adapter::empirical_async_after(unsigned hart,size_t instruction,bool retired){
 if(profile_.empirical_fadd_eg)if(auto a=fadd_eg_find(hart,instruction)){fadd_eg_after(hart,a,retired);return;}
 if(profile_.empirical_opu_entry)if(auto actor=opu_find(hart,instruction)){opu_after(hart,actor,retired);return;}
 auto actor=empirical_async_[hart];if(!actor||actor->instruction!=instruction)throw std::logic_error("IRIS_EMPIRICAL_BACKEND_AFTER_OWNER");auto&v=cores_[hart]->VU;
 actor->after_vrf.resize(v.vlenb*32);std::memcpy(actor->after_vrf.data(),v.reg_file,actor->after_vrf.size());actor->after_vrf_known=v.iris_vrf_definedness;
 std::memcpy(v.reg_file,actor->before_vrf.data(),actor->before_vrf.size());v.iris_vrf_definedness=actor->before_vrf_known;
 if(actor->stages_fp){auto*state=cores_[hart]->get_state();actor->after_fflags=state->fflags->read();actor->after_fflags_known=state->fflags->iris_known_bits();actor->after_fs=state->mstatus->read()&MSTATUS_FS;state->fflags->iris_restore_snapshot(actor->before_fflags,actor->before_fflags_known);state->mstatus->iris_restore_fs_snapshot(actor->before_fs);}
 if(!actor->before_mrf.empty()){actor->after_mrf=v.mt;actor->after_mrf_known=v.iris_tile_definedness;actor->after_initialized=v.iris_initialized;v.mt=actor->before_mrf;v.iris_tile_definedness=actor->before_mrf_known;v.iris_initialized=actor->before_initialized;}
 if(actor->stages_fp&&async_trace_)*async_trace_<<"{\"event\":\"fp_staged\",\"hart\":"<<hart<<",\"backend_node\":"<<*actor->backend<<",\"cycle\":"<<clock_.now()<<",\"flags_before\":"<<actor->before_fflags<<",\"flags_after\":"<<actor->after_fflags<<",\"known_before\":"<<actor->before_fflags_known<<",\"known_after\":"<<actor->after_fflags_known<<",\"fs_before\":"<<actor->before_fs<<",\"fs_after\":"<<actor->after_fs<<",\"visible_flags\":"<<cores_[hart]->get_state()->fflags->read()<<",\"visible_fs\":"<<(cores_[hart]->get_state()->mstatus->read()&MSTATUS_FS)<<"}\n";
 if(!retired){empirical_async_cancel(hart,instruction);return;}
 actor->retired=true;empirical_async_publish(hart,actor);
}
void iris_timing_adapter::empirical_async_publish(unsigned hart,const std::shared_ptr<EmpiricalAsync>&actor){
 if(!actor->done||!actor->retired)return;
 if(empirical_async_[hart]!=actor)throw std::logic_error("IRIS_EMPIRICAL_BACKEND_PUBLISH_OWNER");
 auto&v=cores_[hart]->VU;if(actor->stages_fp){const auto*state=cores_[hart]->get_state();if(state->fflags->read()!=actor->before_fflags||state->fflags->iris_known_bits()!=actor->before_fflags_known||(state->mstatus->read()&MSTATUS_FS)!=actor->before_fs)throw std::logic_error("IRIS_EMPIRICAL_ASYNC_EARLY_FCSR_MUTATION");}
 if(std::memcmp(v.reg_file,actor->before_vrf.data(),actor->before_vrf.size())||v.iris_vrf_definedness.read(0,actor->before_vrf.size())!=actor->before_vrf_known.read(0,actor->before_vrf.size())||(!actor->before_mrf.empty()&&(v.mt!=actor->before_mrf||v.iris_tile_definedness.read(0,actor->before_mrf.size())!=actor->before_mrf_known.read(0,actor->before_mrf.size()))))throw std::logic_error("IRIS_EMPIRICAL_ASYNC_EARLY_NUMERIC_MUTATION");std::memcpy(v.reg_file,actor->after_vrf.data(),actor->after_vrf.size());v.iris_vrf_definedness=actor->after_vrf_known;
 if(actor->stages_fp){auto*state=cores_[hart]->get_state();state->fflags->iris_restore_snapshot(actor->after_fflags,actor->after_fflags_known);state->mstatus->iris_restore_fs_snapshot(actor->after_fs);}
 if(!actor->after_mrf.empty()){v.mt=actor->after_mrf;v.iris_tile_definedness=actor->after_mrf_known;v.iris_initialized=actor->after_initialized;}
 if(async_trace_)*async_trace_<<"{\"event\":\"publish\",\"hart\":"<<hart<<",\"instruction\":"<<actor->instruction<<",\"backend_node\":"<<*actor->backend<<",\"cycle\":"<<clock_.now()<<"}\n";
 empirical_async_[hart]=std::move(empirical_async_next_[hart]);empirical_async_next_[hart].reset();
}
void iris_timing_adapter::empirical_async_cancel(unsigned hart,size_t instruction){
 if(profile_.empirical_fadd_eg)if(auto a=fadd_eg_find(hart,instruction)){fadd_eg_cancel(hart,a);return;}
 if(profile_.empirical_opu_entry)if(auto actor=opu_find(hart,instruction)){opu_cancel(hart,actor);return;}
 auto actor=empirical_async_[hart];const bool tail=empirical_async_next_[hart]&&empirical_async_next_[hart]->instruction==instruction;if(tail)actor=empirical_async_next_[hart];if(!actor||actor->instruction!=instruction)return;
 if(!tail&&empirical_async_next_[hart])empirical_async_cancel(hart,empirical_async_next_[hart]->instruction);
 if(actor->retired)throw std::logic_error("IRIS_EMPIRICAL_RETIRED_BACKEND_CANNOT_SQUASH");
 const auto node=actor->backend;
 if(node){const auto&n=clock_.nodes().at(*node);if(n.completed)clock_.mark_squashed(*node,"empirical-vector-front-squash");else if(!n.cancelled)clock_.cancel(*node,"empirical-vector-front-squash");}
 if(async_trace_)*async_trace_<<"{\"event\":\"cancel\",\"hart\":"<<hart<<",\"backend_node\":"<<*actor->backend<<",\"cycle\":"<<clock_.now()<<"}\n";
 if(tail)empirical_async_next_[hart].reset();else empirical_async_[hart].reset();
}
