#!/usr/bin/env python3
"""Observability-only edits in the verified private C12 diagnostic checkout."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];CAP=R/'build/warm-OPU-TK124-frozen-c12a08f7-v1'
import argparse
ap=argparse.ArgumentParser(__doc__);ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();S=args.source.resolve();OUT=args.output.resolve();OUT.mkdir(parents=True,exist_ok=False)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
inv=json.loads((CAP/'native-inventory.json').read_text())
for n,h in inv.items():assert sha(S/n)==h,n
def edit(name,changes):
 p=S/'riscv'/name;s=p.read_text()
 for old,new,count in changes:
  assert s.count(old)==count,(name,old[:80],s.count(old),count);s=s.replace(old,new)
 p.write_text(s)
edit('iris_timing_adapter.h',[(
 'std::unique_ptr<std::ofstream> feature_stream_,async_trace_;',
 'std::unique_ptr<std::ofstream> feature_stream_,async_trace_,cpu_trace_;\n  Cycle cpu_trace_first_=0,cpu_trace_last_=UINT64_MAX;unsigned cpu_trace_hart_=0;\n  void cpu_event(unsigned,const char*,uint64_t,uint32_t,size_t,const std::string& = {})const;',1)])
constructor='''
  if(const char*path=std::getenv("IRIS_CPU_DIAGNOSTIC_TRACE")){
   cpu_trace_=std::make_unique<std::ofstream>(path);if(!*cpu_trace_)throw std::runtime_error("cannot open CPU diagnostic trace");
   auto number=[](const char*name,uint64_t fallback){const char*s=std::getenv(name);if(!s)return fallback;size_t end=0;auto v=std::stoull(s,&end,0);if(s[end])throw std::runtime_error("invalid CPU trace filter");return uint64_t(v);};
   cpu_trace_first_=number("IRIS_CPU_DIAGNOSTIC_FIRST",0);cpu_trace_last_=number("IRIS_CPU_DIAGNOSTIC_LAST",UINT64_MAX);cpu_trace_hart_=number("IRIS_CPU_DIAGNOSTIC_HART",0);if(cpu_trace_first_>cpu_trace_last_||cpu_trace_hart_>1)throw std::runtime_error("invalid CPU trace range/hart");
  }
'''
edit('iris_timing_adapter.cc',[(
 '  opu_pending_.resize(cores_.size());',constructor+'  opu_pending_.resize(cores_.size());',1)])
definition='''
void iris_timing_adapter::cpu_event(unsigned h,const char*event,uint64_t pc,uint32_t raw,size_t id,const std::string&fields)const{
 if(!cpu_trace_||h!=cpu_trace_hart_||clock_.now()<cpu_trace_first_||clock_.now()>cpu_trace_last_)return;
 auto&out=*cpu_trace_;out<<"{\\"schema\\":\\"iris.CPU_diagnostic.v1\\",\\"event\\":"<<std::quoted(event)<<",\\"cycle\\":"<<clock_.now()<<",\\"hart\\":"<<h<<",\\"pc\\":"<<pc<<",\\"raw\\":"<<raw<<",\\"instruction\\":";if(id==SIZE_MAX)out<<"null";else out<<id;if(!fields.empty())out<<','<<fields;out<<"}\\n";out.flush();
}
'''
edit('iris_shuttle_issue.cc',[
 ('#include <set>','#include <set>\n#include <sstream>\n#include <fstream>',1),
 ('std::optional<iris::shuttle::Uop> iris_timing_adapter::pure_decode_for_frontend',definition+'\nstd::optional<iris::shuttle::Uop> iris_timing_adapter::pure_decode_for_frontend',1),
 ('      if (current!=stage) continue;','      if (current!=stage) continue;\n      cpu_event(hart,"model_stage",instruction.pc,instruction.uop.raw,index,"\\"stage\\":"+std::to_string(stage)+",\\"result_completed\\":"+((instruction.result&&clock_.nodes().at(*instruction.result).completed)?"true":"false"));',1),
 ('  p.last_attempt=now;\n  if (pure_signals(hart).ex_stall==Signal::yes) return;','  p.last_attempt=now;\n  cpu_event(hart,"rrd_attempt",p.frontier,0,SIZE_MAX,"\\"packets\\":"+std::to_string(p.packets.size()));\n  if (pure_signals(hart).ex_stall==Signal::yes) return;',1),
 ('  if (pure_signals(hart).ex_stall==Signal::yes) return;','  if (pure_signals(hart).ex_stall==Signal::yes){cpu_event(hart,"rrd_reject",p.frontier,0,SIZE_MAX,"\\"reason\\":\\"ex_stall\\"");return;}',1),
 ('  if (p.boundary) {','  if (p.boundary) {\n    cpu_event(hart,"boundary_wait",p.frontier,0,SIZE_MAX,"\\"packets\\":"+std::to_string(p.packets.size())+",\\"async_owner\\":"+(empirical_async_[hart]?"true":"false"));',2),
 ('    const auto pc=next_pc;','    const auto pc=next_pc;\n    cpu_event(hart,"fetch_attempt",pc,0,SIZE_MAX,"\\"lane\\":"+std::to_string(lane));',1),
 ('      p.boundary=true; break;','      cpu_event(hart,"candidate_boundary",pc,0,SIZE_MAX,"\\"reason\\":\\"prefetch_scope\\"");p.boundary=true; break;',1),
 ('if(profile_.empirical&&!empirical_fetch_ready(hart,pc,fetch.insn.length(),&fetch)){if(fetched.empty())return;break;}',
  'if(profile_.empirical&&!empirical_fetch_ready(hart,pc,fetch.insn.length(),&fetch)){cpu_event(hart,"rrd_reject",pc,uint32_t(fetch.insn.bits()),SIZE_MAX,"\\"reason\\":\\"icache_fetch_wait\\"");if(fetched.empty())return;break;}',1),
 ('    if (!pure_candidate(hart,fetch)) { p.boundary=true; break; }','    if (!pure_candidate(hart,fetch)) {cpu_event(hart,"candidate_boundary",pc,uint32_t(fetch.insn.bits()),SIZE_MAX,"\\"reason\\":\\"pure_candidate_false\\"");p.boundary=true; break; }',1),
 ('if(profile_.empirical_async&&!empirical_async_can_dispatch(hart,&fetch)&&empirical_unit_decode(uint32_t(fetch.insn.bits()),profile_.empirical_async_fadd)){if(fetched.empty())return;break;}',
  'if(profile_.empirical_async&&!empirical_async_can_dispatch(hart,&fetch)&&empirical_unit_decode(uint32_t(fetch.insn.bits()),profile_.empirical_async_fadd)){cpu_event(hart,"rrd_reject",pc,uint32_t(fetch.insn.bits()),SIZE_MAX,"\\"reason\\":\\"whole_async_owner\\"");if(fetched.empty())return;break;}',1),
 ('    if(profile_.empirical_load_front&&plan.ready_prefix>1&&plan.lanes[1].integer_result_stage==ResultStage::wb)plan.ready_prefix=1;',
  '    if(profile_.empirical_load_front&&plan.ready_prefix>1&&plan.lanes[1].integer_result_stage==ResultStage::wb){cpu_event(hart,"lane1_WB_split",fetched[1].first,uint32_t(fetched[1].second.insn.bits()),SIZE_MAX,"\\"planned_ready_prefix\\":2");plan.ready_prefix=1;}\n    if(cpu_trace_)for(unsigned i=0;i<plan.lanes.size();++i){std::ostringstream fields;fields<<"\\"lane\\":"<<i<<",\\"accepted_prefix\\":"<<plan.ready_prefix<<",\\"reasons\\":[";bool first=true;for(const auto&reason:plan.lanes[i].reasons){if(!first)fields<<",";first=false;fields<<std::quoted(reason);}fields<<"]";cpu_event(hart,"rrd_plan",fetched[i].first,uint32_t(fetched[i].second.insn.bits()),SIZE_MAX,fields.str());}',1),
 ('    auto& stored=p.instructions.at(id);if(stored.empirical_load)',
  '    auto& stored=p.instructions.at(id);cpu_event(hart,"rrd_accept",stored.pc,uint32_t(stored.fetch.insn.bits()),id,"\\"lane\\":"+std::to_string(lane)+",\\"EX_planned\\":"+std::to_string(stored.ex_release)+",\\"MEM_planned\\":"+std::to_string(stored.com_cycle-divider)+",\\"COM_planned\\":"+std::to_string(stored.com_cycle));if(stored.empirical_load)',1),
 ('        if(row.squashed)return;','        if(row.squashed)return;\n        cpu_event(hart,"result_callback",row.pc,uint32_t(row.fetch.insn.bits()),id,"\\"load\\":"+std::string(row.empirical_load?"true":"false"));',1),
 ('  completing_=hart;completing_pure_=id;',
  '  cpu_event(hart,"COM_enter",row.pc,uint32_t(row.fetch.insn.bits()),id);\n  completing_=hart;completing_pure_=id;',1),
 ('  completing_pure_.reset();completing_.reset();++p.next_commit;',
  '  cpu_event(hart,"COM_exit",row.pc,uint32_t(row.fetch.insn.bits()),id,"\\"retired_delta\\":"+std::to_string(retired_[hart]-before));\n  completing_pure_.reset();completing_.reset();++p.next_commit;',1),
])
edit('iris_empirical_load.inc',[
 (' if(!base)return false;insn_t instruction(u.expanded);',
  ' if(!base){cpu_event(hart,"load_candidate_reject",0,u.raw,SIZE_MAX,"\\"reason\\":\\"unknown_base\\",\\"candidate_pc_unavailable\\":true");return false;}insn_t instruction(u.expanded);',1),
 (' return address%bytes==0&&empirical_cache_->data_hit(hart,address,bytes);',
  ' if(address%bytes){cpu_event(hart,"load_candidate_reject",0,u.raw,SIZE_MAX,"\\"reason\\":\\"alignment\\",\\"candidate_pc_unavailable\\":true");return false;}const bool hit=empirical_cache_->data_hit(hart,address,bytes);cpu_event(hart,hit?"load_candidate_hit":"load_candidate_reject",0,u.raw,SIZE_MAX,"\\"reason\\":\\"own_cache_tag\\",\\"address\\":"+std::to_string(address)+",\\"candidate_pc_unavailable\\":true");return hit;',1),
 ('void iris_timing_adapter::empirical_load_capture(unsigned hart,size_t id){\n auto&p=pure_[hart];auto&r=p.instructions.at(id);if(r.squashed)return;',
  'void iris_timing_adapter::empirical_load_capture(unsigned hart,size_t id){\n auto&p=pure_[hart];auto&r=p.instructions.at(id);if(r.squashed)return;cpu_event(hart,"load_capture",r.pc,uint32_t(r.fetch.insn.bits()),id,"\\"address\\":"+std::to_string(r.memory_address));',1),
 ('r.empirical_load_owner=owner;empirical_memory_feature(hart,d,false);',
  'r.empirical_load_owner=owner;empirical_memory_feature(hart,d,false);cpu_event(hart,"load_response_class",r.pc,uint32_t(r.fetch.insn.bits()),id,"\\"address\\":"+std::to_string(r.memory_address)+",\\"L1_misses\\":"+std::to_string(d.l1_misses)+",\\"L2_misses\\":"+std::to_string(d.l2_misses)+",\\"wait_owners\\":"+std::to_string(d.wait_for.size()));',1),
])
changed={n:sha(S/n)for n in inv if sha(S/n)!=inv[n]}
(OUT/'instrumentation.json').write_text(json.dumps({'schema':'iris.C12_CPU_instrumentation_preparation.v1','pass':True,'source':str(S),'changed_source_sha256':changed,'new_timing_operations_added':False,'modeled_state_or_rule_changes':False,'stream_scope':'defaultOFF;hart0bydefault;environmentabsoluteglobalcyclefilter;read-onlystage/decisionobservations','parent_manifest_sha256':sha(CAP/'manifest.json'),'hardware_contacted':False},indent=2)+'\n');print(json.dumps({'pass':True,'changed_files':list(changed)}))
