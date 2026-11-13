#!/usr/bin/env python3
"""Read-only source/associated-SV and frozen actual-edge ingress audit.
No hardware, timing labels, native edits, fitted offsets or new RTL execution.
"""
import argparse,copy,gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
 if not ok:raise ValueError(msg)
SOURCES={
 'core':ROOT/'third_party/shuttle/src/main/scala/exu/Core.scala',
 'frontend':ROOT/'third_party/saturn/src/main/scala/shuttle/Frontend.scala',
 'pfc':ROOT/'third_party/saturn/src/main/scala/frontend/PipelinedFaultCheck.scala',
 'dispatch':ROOT/'third_party/saturn/src/main/scala/frontend/Dispatch.scala',
 'backend':ROOT/'third_party/saturn/src/main/scala/backend/Backend.scala',
 'queue':ROOT/'third_party/saturn/src/main/scala/common/DCEQueue.scala',
 'integration':ROOT/'third_party/saturn/src/main/scala/shuttle/Integration.scala',
 'core_sv':ROOT/'build/rtl-verilator/gen-collateral/ShuttleCore.sv',
 'frontend_sv':ROOT/'build/rtl-verilator/gen-collateral/SaturnShuttleFrontend.sv',
 'pfc_sv':ROOT/'build/rtl-verilator/gen-collateral/PipelinedFaultCheck.sv',
 'backend_sv':ROOT/'build/rtl-verilator/gen-collateral/VectorBackend.sv',
 'queue_sv':ROOT/'build/rtl-verilator/gen-collateral/DCEQueue.sv',
 'native_async':ROOT/'pipeline/riscv-isa-sim-warm-opu-v1/riscv/iris_empirical_async.inc',
 'native_issue':ROOT/'pipeline/riscv-isa-sim-warm-opu-v1/riscv/iris_shuttle_issue.cc',
 'native_adapter':ROOT/'pipeline/riscv-isa-sim-warm-opu-v1/riscv/iris_timing_adapter.cc',
 'native_opu':ROOT/'pipeline/riscv-isa-sim-warm-opu-v1/riscv/iris_opu_entry_overlap.inc',
 'C12_opu':ROOT/'pipeline/riscv-isa-sim-warm-opu-tk124-v1/riscv/iris_opu_entry_overlap.inc'}
def source_checks(texts):
 checks=[]
 def has(name,fragment):need(fragment in texts[name],name+': '+fragment);checks.append(dict(file=str(SOURCES[name]),line=texts[name][:texts[name].index(fragment)].count('\n')+1,source_fragment=fragment))
 for name,fragment in [
 ('core','ex_uops_reg(i).valid := rrd_uops(i).valid && !rrd_stall(i)'),
 ('core','mem_uops_reg(i).valid := ex_uops_reg(i).valid && !flush_rrd_ex && !ex_stall'),
 ('core','com_uops_reg(i).valid := mem_uops_reg(i).valid && !kill_mem'),
 ('core','v.ex.fire := !ex_stall && !flush_rrd_ex'),
 ('core','v.ex.valid && !v.ex.ready'),
 ('core','val is_youngest = uop.xcpt || uop.csr_en || uop.system_insn'),
 ('core','val vec_bsy = io.vector.map(v => v.backend_busy || v.trap_check_busy)'),
 ('core','(ex_bsy || mem_bsy || com_bsy || isboard_bsy || fsboard_bsy || !io.dmem.ordered || io.rocc.busy || vec_bsy)'),
 ('core','v.mem.kill := kill_mem'),
 ('core','when (io.vector.get.com.block_all)'),
 ('frontend','pfc.io.s0.in.valid        := io.core.ex.valid && !ifc.io.busy && !(replayed && !io.issue.ready)'),
 ('frontend','io.core.ex.ready          := !ifc.io.busy && !(replayed && !io.issue.ready)'),
 ('frontend','pfc.io.s1.kill := io.core.mem.kill || !RegEnable(io.core.ex.fire, io.core.ex.valid)'),
 ('frontend','io.core.wb.block_all        := ifc.io.busy || (pfc.io.s2.inst.valid && !pfc.io.s2.retire && !pfc.io.s2.internal_replay.valid)'),
 ('frontend','pfc.io.s2.issue.ready := !ifc.io.busy && io.issue.ready'),
 ('pfc','s1_valid := io.s0.in.fire'),('pfc','s2_valid := s1_valid && !io.s1.kill'),
 ('pfc','when (!io.s2.issue.ready || (io.s2.scalar_store_pending && s2_inst.vmu))'),
 ('dispatch','io.issue.ready := vat_available && io.dis.ready   && (!issue_inst.vmu || io.mem.ready) && !hwacha_block'),
 ('backend','val vdq = Module(new DCEQueue(new VectorIssueInst, vParams.vdqEntries))'),
 ('queue','val pipe:           Boolean = false'),('queue','val flow:           Boolean = false'),
 ('queue','io.deq.valid := !empty'),('queue','io.enq.ready := !full'),
 ('integration','io.backend_busy   := vu.io.busy || tl_if.module.io.mem_busy || sg_if.map(_.module.io.mem_busy).getOrElse(false.B) || vmu.io.busy'),
 ('backend','io.busy := vdq.io.deq.valid || allSeqs.map(_.io.busy).orR || vxus.flatten.map(_.io.busy).asUInt.orR'),
 ('core_sv','assign io_vector_ex_fire = ~ex_stall & ~flush_rrd_ex;'),
 ('frontend_sv','assign io_core_ex_ready = ~_ifc_io_busy & ~(replayed & ~io_issue_ready);'),
 ('pfc_sv','s1_valid <= io_s0_in_valid;'),('pfc_sv','s2_valid <= s1_valid & ~io_s1_kill;'),
 ('backend_sv','DCEQueue vdq ('),('queue_sv','assign io_enq_ready = ~full;'),('queue_sv','assign io_deq_valid = ~empty;'),
 ('native_async','return head->com_cycle<=edge&&(head->done||(node.issued&&!node.cancelled&&node.end<=edge));'),
 ('native_async','if(!actor->done||!actor->retired)return;'),
 ('native_async','std::memcpy(v.reg_file,actor->after_vrf.data(),actor->after_vrf.size());'),
 ('native_issue','instruction.com_cycle=future_cycle(instruction.ex_release,divider,2);'),
 ('native_adapter','if(profile_.empirical_async&&empirical_async_[hart]&&!pure_candidate(hart,fetch))throw iris_timing_wait{};'),
 ('native_opu','a->opu_available=r.com_cycle/divider+1;'),
 ('C12_opu','a->opu_available=r.com_cycle/divider+1;')]:has(name,fragment)
 return checks

def trace_checks(events):
 selected={i:[]for i in(1,2,3,4)}
 for x in events:
  c=x.get('command',{});seq=c.get('sequence')
  if x['hart']==1 and seq in selected and c.get('reset_epoch')==1:selected[seq].append(x)
 summaries=[]
 for seq,rows in selected.items():
  def one(kind):
   rr=[x for x in rows if x['kind']==kind];need(len(rr)==1,'One actual '+kind);return rr[0]
  ex=one('EX_fire');dispatch=one('dispatch_accept');front=one('PFC_front_permission');need(ex['command']['EX_fired']is True and ex['command']['EX_edge']==ex['source_edge'],'Actual EX owner')
  need(dispatch['source_edge']==front['source_edge']==ex['source_edge']+2,'EX+2 frontpermission and dispatch sameedge')
  need(dispatch['dispatch']['VAT_generation']==1 and dispatch['command']==ex['command'],'Stable accepted command/VAT generation')
  seqaccept=one('sequencer_accept');micro=[x['source_edge']for x in rows if x['kind']=='microissue'];writes=[x['source_edge']for x in rows if x['kind']=='VRF_bank_commit']
  need(micro and writes and min(micro)>=seqaccept['source_edge']+1 and min(writes)>min(micro),'Physical micro/write after accepted sequencer')
  summaries.append(dict(hart=1,command_sequence=seq,raw=ex['command']['instruction'],pc=ex['command']['pc'],EX=ex['source_edge'],front_permission=front['source_edge'],VDQ_enq=dispatch['source_edge'],sequencer_accept=seqaccept['source_edge'],first_microissue=min(micro),first_VRF_write=min(writes),last_VRF_write=max(writes)))
 need([s['EX']for s in summaries]==list(range(14986,14990)),'Actual consecutive accepted EX edges')
 need([s['VDQ_enq']for s in summaries]==list(range(14988,14992)),'Actual consecutive enqueue/COM frontpermission')
 need(summaries[3]['VDQ_enq']<summaries[0]['first_VRF_write'],'Multiple younger front retirements precede first older VRF write')
 return summaries

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 texts={k:p.read_text()for k,p in SOURCES.items()};checks=source_checks(texts)
 stream=ROOT/'build/saturn-timing-ownership-proof-v2/rvv-seed0-events.ndjson.gz'
 with gzip.open(stream,'rt')as f:events=[json.loads(x)for x in f]
 summaries=trace_checks(events);controls=[]
 def reject(name,fn):
  try:fn()
  except(ValueError,KeyError):controls.append(dict(name=name,rejected=True))
  else:raise ValueError('Mutation admitted '+name)
 for kind in('EX_fire','dispatch_accept','PFC_front_permission'):
  mutated=copy.deepcopy(events);x=next(x for x in mutated if x['hart']==1 and x.get('command',{}).get('sequence')==1 and x['kind']==kind);x['source_edge']+=1;reject(kind+' phase+1',lambda:trace_checks(mutated))
 mutated=[x for x in events if not(x['hart']==1 and x.get('command',{}).get('sequence')==1 and x['kind']=='EX_fire')];reject('missing actual EX owner',lambda:trace_checks(mutated))
 tt=dict(texts);tt['queue_sv']=tt['queue_sv'].replace('assign io_enq_ready = ~full;','assign io_enq_ready = io_deq_ready | ~full;');reject('pipe queue fabricated',lambda:source_checks(tt))
 tt=dict(texts);tt['frontend']=tt['frontend'].replace('io.core.ex.ready          := !ifc.io.busy && !(replayed && !io.issue.ready)','io.core.ex.ready          := !io.core.backend_busy');reject('wholebusy ingress fabricated',lambda:source_checks(tt))
 inputs={str(p):sha(p)for p in[Path(__file__).resolve(),*SOURCES.values(),stream,ROOT/'hardware/manifest.json',ROOT/'build/saturn-timing-ownership-proof-v2/report.json',ROOT/'build/saturn-timing-ownership-component-v1-final/report.json',ROOT/'build/warm-OPU-frozen-7108a6ec-v1/manifest.json',ROOT/'build/warm-OPU-TK124-frozen-c12a08f7-v1/manifest.json']}
 report=dict(schema='iris.shuttle_RVV_ingress_source_audit.v1',**{'pass':True},source_checks=checks,actual_saved_source_trace=summaries,corruption_controls=controls,input_sha256=inputs,actual_new_RTL_execution=False,actual_saved_source_replay_reused=True,hardware_contacted=False,hardware_timing_labels_consumed=False,native_modified=False,source_equations=dict(EX_ready='!IFCbusy && !(replayed && !dispatcher_ready)',PFC_S1='next(S0valid)',PFC_S2='next(S1valid && !MEMkill && previousEXfire)',nonmemory_no_fault_front='S2valid && dispatcher_ready; physicalCOM/frontpermission/VDQenqueue same sourceedge',VDQ='depth4; nonflow/nonpipe; enqready=!full preedge; deqvalid=!empty preedge',FENCE_RRD='pipeline|scalar_scoreboards|!DCache.ordered|RoCCbusy|backendbusy|trapcheckbusy',backendbusy='VDQnonempty|sequencerbusy|executionunitbusy|TLmem_busy|TCMmem_busy|VMUbusy; not generic numerical owner count'),native_extra_constraints=dict(minimum_RRD_spacing_from_COM_guard=2,derivation='olderCOM=olderRRD+3, candidateEX=candidateRRD+1; olderCOM<=candidateEX imposescandidateRRD>=olderRRD+2 even forindependent onebeat integerops',source_consecutive_EX_witness=True,whole_VRF_publication=True,ordinary_vector_requires_prior_wholebackend_by_nextEX=True,nonpure_boundary_drains_all_pending=True,OPU_enq_offer='COM+1 explicitunqualifiedbridge; oneedge laterthan matching S2/COM sourcefront'),scope='Exact source/associatedSV causalphase plus reused whole-saved-source frozen eventwitness; not deployedFPGA identity/fulltiming/wholeCPUintegration certification. Event numeric bitknownness is not inferred.')
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(pass_=True,report_sha256=sha(out/'report.json'),source_checks=len(checks),corruptions=len(controls))))
if __name__=='__main__':main()
