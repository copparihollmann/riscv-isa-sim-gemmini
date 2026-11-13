#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,subprocess,shutil
R=Path(__file__).resolve().parents[1];P=R/'pipeline/riscv-isa-sim-C12-scheduler-diagnostic-v1';S=R/'pipeline/riscv-isa-sim-C12-async-RRD-wake-v1';C=R/'build/C12-scheduler-diagnostic-frozen-fca1eed2-v1';O=R/'build/C12-async-RRD-wake-preparation-v1';O.mkdir();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();inv=json.loads((C/'native-inventory.json').read_text());subprocess.run(['git','clone','--local','--no-hardlinks','--no-checkout',str(P),str(S)],check=True,stdout=subprocess.DEVNULL);subprocess.run(['git','-C',str(S),'checkout','--detach','72958551566a30f19444bd7e354552824e4d0a98'],check=True,stdout=subprocess.DEVNULL)
for n,h in inv.items():
 assert sha(P/n)==h,n;d=S/n;d.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(P/n,d)
def edit(n,a,b):
 p=S/'riscv'/n;s=p.read_text();assert s.count(a)==1,(n,a[:70],s.count(a));p.write_text(s.replace(a,b))
edit('iris_timing_adapter.h','empirical_async_two_owner=false,','empirical_async_two_owner=false,empirical_async_rrd_wake=false,')
edit('iris_timing_adapter.h','  bool empirical_async_can_dispatch(unsigned,const insn_fetch_t* = nullptr)const;','  bool empirical_async_can_dispatch(unsigned,const insn_fetch_t* = nullptr)const;\n  void empirical_async_RRD_deadline(std::optional<Cycle>&);')
edit('iris_timing_adapter.h','  Cycle cpu_trace_first_=0,cpu_trace_last_=UINT64_MAX;unsigned cpu_trace_hart_=0;','  Cycle cpu_trace_first_=0,cpu_trace_last_=UINT64_MAX;unsigned cpu_trace_hart_=0;\n  unsigned cpu_trace_roi_stride_=0;std::vector<uint64_t>cpu_trace_mcycle_counts_;std::string cpu_trace_event_filter_;')
edit('iris_timing_adapter.cc','      } else if(key=="empirical_async"&&f.size()==2){','      } else if(key=="empirical_async_rrd_wake"&&f.size()==2){\n        if(!singleton.insert(key).second||f[1]!="h0h1-existing-live-head-eligibility-v1")throw std::runtime_error("unsupported async RRD wake");p.empirical_async_rrd_wake=true;\n      } else if(key=="empirical_async"&&f.size()==2){')
edit('iris_timing_adapter.cc','  if(!p.empirical&&(p.empirical_async||','  if(p.empirical_async_rrd_wake&&(!p.empirical||!p.empirical_async_two_owner||!p.shuttle_pure_pipeline))throw std::runtime_error("async RRD wake requires explicit empirical two-owner Shuttle pipeline");\n  if(!p.empirical&&(p.empirical_async||')
edit('iris_timing_adapter.cc','  if(const char*path=std::getenv("IRIS_CPU_DIAGNOSTIC_TRACE")){','  cpu_trace_mcycle_counts_.resize(cores_.size());\n  if(const char*s=std::getenv("IRIS_CPU_DIAGNOSTIC_MCYCLEROI")){if(std::string(s)!="3")throw std::runtime_error("CPU trace MCYCLE ROI requires explicit3-phase grouping");cpu_trace_roi_stride_=3;}\n  if(const char*s=std::getenv("IRIS_CPU_DIAGNOSTIC_EVENTS"))cpu_trace_event_filter_=","+std::string(s)+",";\n  if(const char*path=std::getenv("IRIS_CPU_DIAGNOSTIC_TRACE")){')
edit('iris_timing_adapter.cc','    if (!event) {','    if(profile_.empirical_async_rrd_wake)empirical_async_RRD_deadline(event);\n    if (!event) {')
edit('iris_timing_adapter.cc','#include "iris_empirical_async.inc"','#include "iris_empirical_async.inc"\n#include "iris_async_RRD_wake.inc"')
edit('iris_shuttle_issue.cc',' if(!cpu_trace_||h!=cpu_trace_hart_||clock_.now()<cpu_trace_first_||clock_.now()>cpu_trace_last_)return;',' if(!cpu_trace_||h!=cpu_trace_hart_||clock_.now()<cpu_trace_first_||clock_.now()>cpu_trace_last_)return;\n if(cpu_trace_roi_stride_&&(!cpu_trace_mcycle_counts_.at(h)||cpu_trace_mcycle_counts_.at(h)%cpu_trace_roi_stride_==0))return;\n if(!cpu_trace_event_filter_.empty()&&cpu_trace_event_filter_.find(","+std::string(event)+",")==std::string::npos)return;')
edit('iris_counter_observations.cc','      row.sequence=counter_sequences_.at(hart)++;','      if(row.csr==0xb00||row.csr==0xc00)++cpu_trace_mcycle_counts_.at(hart);\n      row.sequence=counter_sequences_.at(hart)++;')
(S/'riscv/iris_async_RRD_wake.inc').write_text('''// Visit an already-permitted future RRD edge. No actor/cost/queue is changed.
void iris_timing_adapter::empirical_async_RRD_deadline(std::optional<Cycle>&event){
 if(!event)return;
 for(unsigned h=0;h<std::min(size_t(2),pure_.size());++h){
  const auto&p=pure_[h];const auto&head=empirical_async_[h];
  if(!p.engaged||p.boundary||!p.packets.empty()||blocked_[h]||empirical_branch_recovery_[h]||!head||head->done||!head->backend||empirical_async_next_[h]||cores_[h]->is_waiting_for_interrupt())continue;
  if(profile_.source_counter_clock&&source_counter_clocks_[h].blocks_rrd(clock_.now()))continue;
  if(cores_[h]->iris_pipeline_interrupt_exception())continue;
  const auto&node=clock_.nodes().at(*head->backend);if(node.id!=*head->backend||node.op.hart!=h||!node.issued||node.completed||node.cancelled||node.physical)continue;
  const auto d=profile_.harts[h].divider;const auto first=std::max(head->com_cycle,node.end);if(first<d)continue;
  auto retry=first-d;if(const auto rem=retry%d){if(retry>UINT64_MAX-(d-rem))throw std::overflow_error("IRIS_ASYNC_RRD_WAKE_HORIZON");retry+=d-rem;}
  if(retry<=clock_.now()||retry>=*event)continue;
  cpu_event(h,"async_RRD_wake",p.frontier,0,SIZE_MAX,"\\"old_next_event\\":"+std::to_string(*event)+",\\"retry_edge\\":"+std::to_string(retry)+",\\"backend_node\\":"+std::to_string(*head->backend)+",\\"backend_end\\":"+std::to_string(node.end)+",\\"head_COM\\":"+std::to_string(head->com_cycle));
  event=retry;
 }
}
''')
new=dict(inv);new['riscv/iris_async_RRD_wake.inc']=sha(S/'riscv/iris_async_RRD_wake.inc');changed={n:sha(S/n)for n in new if n not in inv or sha(S/n)!=inv[n]};subprocess.run(['git','-C',str(S),'add','-N','--',*new],check=True);(O/'preparation.json').write_text(json.dumps({'schema':'iris.C12_async_RRD_wake_preparation.v1','source':str(S),'default_OFF':True,'parent_fca1_manifest_sha256':sha(C/'manifest.json'),'changed_source_sha256':changed,'logging_only_options':['IRIS_CPU_DIAGNOSTIC_MCYCLEROI=3 groups successful returningMCYCLE reads; no boot/preparation outsideROI','IRIS_CPU_DIAGNOSTIC_EVENTS comma-separated event kinds; no timing filters'],'hardware_contacted':False,'latencies_intervals_capacities_or_can_dispatch_changed':False},indent=2)+'\n');print(json.dumps({'changed':list(changed)}))
