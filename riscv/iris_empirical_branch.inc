// Explicit lightweight prediction approximation over source legal issue/RAW rules.
uint64_t iris_timing_adapter::empirical_predict(unsigned hart,uint64_t pc,const iris::shuttle::Uop&u,unsigned length)const{
 if(hart==2&&rocket_packets_)if(auto next=rocket_packets_->prediction(pc,u.raw,length))return *next;
 return empirical_predict_legacy(hart,pc,u,length);
}
uint64_t iris_timing_adapter::empirical_predict_legacy(unsigned hart,uint64_t pc,const iris::shuttle::Uop&u,unsigned length)const{
 const auto&b=empirical_branches_.at(hart);insn_t instruction(u.expanded);
 if(u.has(iris::shuttle::JAL))return pc+instruction.uj_imm();
 if(u.has(iris::shuttle::BRANCH))return b.counters[(pc>>1)&1023]>=2?pc+instruction.sb_imm():pc+length;
 if(u.has(iris::shuttle::JALR)){const auto index=(pc>>1)&255;if(b.valid[index]&&b.tags[index]==pc)return b.targets[index];}
 return pc+length;
}
void iris_timing_adapter::empirical_branch_resolve(unsigned hart,size_t id){
 auto&p=pure_[hart];auto&r=p.instructions.at(id);if(r.squashed)return;
 auto&b=empirical_branches_[hart];insn_t instruction(r.uop.expanded);auto next=r.pc+r.fetch.insn.length();
 if(r.branch_operands){const auto operands=p.values->read(*r.branch_operands);if(!operands[0]||!operands[1])throw std::runtime_error("IRIS_EMPIRICAL_UNDEFINED_BRANCH_OPERANDS");if(r.uop.has(iris::shuttle::BRANCH))r.branch_taken=iris::frontend::ShuttleBranch::compare(r.uop.expanded,*operands[0],*operands[1]);if(r.uop.has(iris::shuttle::JALR))r.branch_wdata=*operands[0]+instruction.i_imm();r.branch_operands.reset();}
 if(r.uop.has(iris::shuttle::BRANCH)){if(r.branch_taken)next=r.pc+instruction.sb_imm();auto&counter=b.counters[(r.pc>>1)&1023];counter=r.branch_taken?std::min(3u,unsigned(counter)+1):counter?counter-1:0;}
 else if(r.uop.has(iris::shuttle::JAL))next=r.pc+instruction.uj_imm();
 else if(r.uop.has(iris::shuttle::JALR)){next=r.branch_wdata&~uint64_t(1);const auto index=(r.pc>>1)&255;b.valid[index]=true;b.tags[index]=r.pc;b.targets[index]=next;if(!r.private_value_ready){r.private_value=r.pc+r.fetch.insn.length();p.values->complete_external(id,r.private_value);r.private_value_ready=true;}}
 r.branch_resolved=true;r.branch_mispredict=next!=r.empirical_prediction;r.branch_redirect=r.branch_mispredict;++b.branches;if(r.branch_mispredict){++b.mispredicts;frontend_squash(hart,id,false);p.frontier=next;if(hart==2&&rocket_packets_)rocket_packet_redirect(next,"source-MEM-mispredict",1);
  for(const auto&rule:profile_.empirical_branch_rules)if(rule.hart==hart){if(rule.penalty>profile_.max_cycles)throw std::runtime_error("IRIS_EMPIRICAL_BRANCH_PENALTY_HORIZON");if(rule.penalty>0){iris::Op recovery{hart,"empirical.branch-recovery","empirical.frontend"+std::to_string(hart),uint64_t(std::ceil(rule.penalty)),1};recovery.retires=false;recovery.pc=r.pc;recovery.on_complete=[this,hart]{empirical_branch_recovery_[hart].reset();};empirical_branch_recovery_[hart]=clock_.issue(std::move(recovery));}break;}
 }
}
