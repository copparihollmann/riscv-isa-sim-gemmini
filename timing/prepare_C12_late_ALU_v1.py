#!/usr/bin/env python3
"""Narrow default-OFF source COM-retirement/WB-result split on frozen retry2c40."""
from pathlib import Path
import subprocess,shutil,json,hashlib
R=Path(__file__).resolve().parents[1];P=R/'pipeline/riscv-isa-sim-C12-pending-base-v1';C=R/'build/C12-pending-base-frozen-2c40dca7-v1';S=R/'pipeline/riscv-isa-sim-C12-late-ALU-v1';O=R/'build/C12-late-ALU-preparation-v1';O.mkdir();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();inv=json.loads((C/'native-inventory.json').read_text())
subprocess.run(['git','clone','--local','--no-hardlinks','--no-checkout',str(P),str(S)],check=True,stdout=subprocess.DEVNULL);subprocess.run(['git','-C',str(S),'checkout','--detach','72958551566a30f19444bd7e354552824e4d0a98'],check=True,stdout=subprocess.DEVNULL)
for n,h in inv.items():
 assert sha(P/n)==h,n;d=S/n;d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(P/n,d)
def edit(n,a,b):
 p=S/'riscv'/n;s=p.read_text();assert s.count(a)==1,(n,a[:70],s.count(a));p.write_text(s.replace(a,b))
edit('iris_timing_adapter.h','empirical_pending_base_retry=false,','empirical_pending_base_retry=false,empirical_late_alu=false,')
edit('iris_timing_adapter.h','  bool empirical_load_wait_base(unsigned,const iris::shuttle::Uop&,uint64_t)const;','  bool empirical_load_wait_base(unsigned,const iris::shuttle::Uop&,uint64_t)const;\n  void empirical_late_alu_before(unsigned,size_t);\n  void empirical_late_alu_after(unsigned,size_t,bool);\n  void empirical_late_alu_write(unsigned,size_t);')
edit('iris_timing_adapter.h','    bool counter = false;','    bool late_alu=false;std::optional<iris_definedness::Value<reg_t>>late_before,late_after;std::optional<iris::frontend::ForwardedValues::Operands>late_operands;\n    bool counter = false;')
edit('iris_timing_adapter.cc','      } else if(key=="empirical_pending_base_retry"&&f.size()==2){','      } else if(key=="empirical_late_alu"&&f.size()==2){\n        if(!singleton.insert(key).second||f[1]!="h0h1-hit-load-pair-COM-WB-v1")throw std::runtime_error("unsupported empirical late ALU");p.empirical_late_alu=true;\n      } else if(key=="empirical_pending_base_retry"&&f.size()==2){')
edit('iris_timing_adapter.cc','  if(p.empirical_pending_base_retry&&','  if(p.empirical_late_alu&&(!p.empirical||!p.empirical_load_front||!p.empirical_shuttle_load_com_forward||!p.private_forwarded_values||!p.shuttle_pure_pipeline))throw std::runtime_error("late ALU requires empirical Shuttle COM-forward load front and private values");\n  if(p.empirical_pending_base_retry&&')
edit('iris_timing_adapter.cc','#include "iris_empirical_load.inc"','#include "iris_empirical_load.inc"\n#include "iris_empirical_late_alu.inc"')
# Source MEM late-ALU uses shared memALU two edges later in WB.
edit('iris_shuttle_issue.cc','  signals.integer_hazard=hazards.values();','  signals.integer_hazard=hazards.values();\n  if(profile_.empirical_late_alu)for(size_t i=p.first_live;i<p.instructions.size();++i){const auto&r=p.instructions[i];if(!r.released&&!r.squashed&&r.late_alu&&now==r.com_cycle-divider)signals.mem_lane1_will_be_latealu=Signal::yes;}')
a='if(profile_.empirical_load_front&&plan.ready_prefix>1&&plan.lanes[1].integer_result_stage==ResultStage::wb){';b='const bool late_pair=profile_.empirical_late_alu&&plan.ready_prefix==2&&plan.lanes[1].integer_result_stage==ResultStage::wb&&uops[0].has(iris::shuttle::MEM)&&(uops[0].expanded&127)==3&&empirical_load_candidate(hart,uops[0])&&base_integer(uops[1])&&uops[1].rd&&!plan.lanes[1].sfb_shadow;\n    if(profile_.empirical_load_front&&plan.ready_prefix>1&&plan.lanes[1].integer_result_stage==ResultStage::wb&&!late_pair){';edit('iris_shuttle_issue.cc',a,b)
edit('iris_shuttle_issue.cc','&& plan.lanes[i].integer_result_stage!=ResultStage::mem)','&& plan.lanes[i].integer_result_stage!=ResultStage::mem && !(late_pair&&i==1&&plan.lanes[i].integer_result_stage==ResultStage::wb))')
edit('iris_shuttle_issue.cc','    const auto id=p.instructions.size();p.instructions.push_back(std::move(instruction));','    instruction.late_alu=profile_.empirical_late_alu&&lane==1&&instruction.result_stage==ResultStage::wb;\n    if(instruction.late_alu&&(!base_integer(instruction.uop)||!instruction.uop.rd||p.instructions.empty()||!p.instructions.back().empirical_load||p.instructions.back().packet!=packet))throw std::logic_error("IRIS_LATE_ALU_PAIR_SCOPE");\n    const auto id=p.instructions.size();p.instructions.push_back(std::move(instruction));')
edit('iris_shuttle_issue.cc','      } else if(stored.empirical_load)p.values->issue_external(id,stored.uop.rd);','      } else if(stored.late_alu){stored.late_operands=p.values->latch(stored.uop.has(iris::shuttle::RXS1)?stored.uop.rs1:0,stored.uop.has(iris::shuttle::RXS2)?stored.uop.rs2:0);p.values->issue_external(id,stored.uop.rd);}\n      else if(stored.empirical_load)p.values->issue_external(id,stored.uop.rd);')
edit('iris_shuttle_issue.cc','prefix+(stored.empirical_load?"LOAD_RESPONSE":mem?"MEM_ALU":"EX"),stored.ex_release-now,divider','prefix+(stored.empirical_load?"LOAD_RESPONSE":mem||stored.late_alu?"MEM_ALU":"EX"),stored.late_alu?divider:stored.ex_release-now,divider')
edit('iris_shuttle_issue.cc','      if (mem) result.earliest=future_cycle(now,divider,1);','      if (mem) result.earliest=future_cycle(now,divider,1);\n      if(stored.late_alu){result.name=stored.uop.instruction_name+".late-WB-result";result.earliest=stored.com_cycle;}')
edit('iris_shuttle_issue.cc','        if(row.empirical_load){empirical_load_response(hart,id);return;}','        if(row.late_alu){empirical_late_alu_write(hart,id);return;}\n        if(row.empirical_load){empirical_load_response(hart,id);return;}')
edit('iris_shuttle_issue.cc','commit.deps={stored.counter?*stored.csr_ex:*stored.result};','commit.deps={stored.counter?*stored.csr_ex:*stored.result};\n    if(stored.late_alu){commit.deps.clear();for(auto producer:stored.raw_producers)commit.deps.push_back(*p.instructions.at(producer).result);}')
edit('iris_shuttle_issue.cc','    stored.com=clock_.issue(std::move(commit));','    stored.com=clock_.issue(std::move(commit));\n    if(stored.late_alu)clock_.add_dependency(*stored.result,*stored.com);')
edit('iris_shuttle_issue.cc','      row.released=true;\n      if (!--p.packets.front().remaining)','      if(row.late_alu&&!row.private_value_ready)throw std::logic_error("IRIS_LATE_ALU_WB_RELEASE_BEFORE_RESULT");\n      row.released=true;\n      if (!--p.packets.front().remaining)')
edit('iris_shuttle_issue.cc','  if(row.scalar_fadd)scalar_fadd_before(hart,id);','  if(row.late_alu)empirical_late_alu_before(hart,id);\n  if(row.scalar_fadd)scalar_fadd_before(hart,id);')
edit('iris_shuttle_issue.cc','if(row.empirical_load)empirical_load_after_commit();completion_reads_.clear();','if(row.empirical_load)empirical_load_after_commit();if(row.late_alu&&row.late_before)cores_[hart]->get_state()->XPR.write_transport(row.uop.rd,*row.late_before);completion_reads_.clear();')
edit('iris_shuttle_issue.cc','  if(row.empirical_load)empirical_load_after_commit();\n  if(row.scalar_fadd)','  if(row.empirical_load)empirical_load_after_commit();\n  if(row.late_alu)empirical_late_alu_after(hart,id,retired_[hart]==before+1);\n  if(row.scalar_fadd)')
edit('iris_shuttle_issue.cc','if(row.source_memory&&row.memory_pending)p.values->retire_pending_external(id);','if(row.late_alu||row.source_memory&&row.memory_pending)p.values->retire_pending_external(id);')
# Header code observes existing buffers only; numeric effects are on exact COM/WB.
(S/'riscv/iris_empirical_late_alu.inc').write_text('''// Source finite lateALU: COM retires, WB computes/writes/bypasses one edge later.
void iris_timing_adapter::empirical_late_alu_before(unsigned h,size_t id){
 auto&r=pure_[h].instructions.at(id);if(!r.late_alu||r.retired||r.squashed||r.late_before||clock_.now()!=r.com_cycle||!r.late_operands||!pure_[h].values->operands_ready(*r.late_operands))throw std::logic_error("IRIS_LATE_ALU_COM_OWNER_OR_OPERANDS");
 r.late_before=cores_[h]->get_state()->XPR.read_transport(r.uop.rd);
}
void iris_timing_adapter::empirical_late_alu_after(unsigned h,size_t id,bool retired){
 auto&r=pure_[h].instructions.at(id);if(!r.late_before)throw std::logic_error("IRIS_LATE_ALU_COM_SNAPSHOT");
 r.late_after=cores_[h]->get_state()->XPR.read_transport(r.uop.rd);cores_[h]->get_state()->XPR.write_transport(r.uop.rd,*r.late_before);
 if(!retired)throw std::runtime_error("IRIS_LATE_ALU_UNEXPECTED_PURE_TRAP");
 const auto operands=pure_[h].values->read(*r.late_operands);if(operands[0]&&operands[1]){auto op=iris::frontend::PureAluValue::decode(r.uop.expanded);if(!op||op->evaluate(r.pc,*operands[0],*operands[1])!=r.late_after->value)throw std::logic_error("IRIS_LATE_ALU_RRD_COM_VALUE_MISMATCH");}
 cpu_event(h,"late_ALU_semantic_COM",r.pc,r.uop.raw,id,"\\"physical_WB\\":"+std::to_string(r.com_cycle+profile_.harts[h].divider));
}
void iris_timing_adapter::empirical_late_alu_write(unsigned h,size_t id){
 auto&p=pure_[h];auto&r=p.instructions.at(id);if(!r.late_alu||!r.retired||r.squashed||!r.late_after||r.private_value_ready||clock_.now()!=r.com_cycle+profile_.harts[h].divider)throw std::logic_error("IRIS_LATE_ALU_WB_OWNER");
 const auto&v=*r.late_after;const bool known=std::all_of(v.known.begin(),v.known.end(),[](uint8_t x){return x==255;});r.private_value=known?std::optional<uint64_t>(v.value):std::nullopt;
 p.values->complete_retired_external(r.uop.rd,id,r.private_value);cores_[h]->get_state()->XPR.write_transport(r.uop.rd,v);r.private_value_ready=true;r.late_operands.reset();
 cpu_event(h,"late_ALU_physical_WB",r.pc,r.uop.raw,id,"\\"value\\":"+std::to_string(v.value)+",\\"fully_known\\":"+(known?"true":"false"));
}
''')
new=dict(inv);new['riscv/iris_empirical_late_alu.inc']=sha(S/'riscv/iris_empirical_late_alu.inc');changed={n:sha(S/n)for n in new if n not in inv or sha(S/n)!=inv[n]};subprocess.run(['git','-C',str(S),'add','-N','--',*new],check=True)
(O/'preparation.json').write_text(json.dumps({'schema':'iris.C12_late_ALU_preparation.v1','parent_manifest_sha256':sha(C/'manifest.json'),'source':str(S),'default_OFF':True,'changed_source_sha256':changed,'source_probe':str(R/'build/Shuttle-late-ALU-source-probe-v1/stdout'),'source_probe_sha256':sha(R/'build/Shuttle-late-ALU-source-probe-v1/stdout'),'hardware_contacted':False},indent=2)+'\n');print(json.dumps({'changed':list(changed)}))
