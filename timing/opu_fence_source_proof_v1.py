#!/usr/bin/env python3
"""Close actual full-unit tail observations and independent Core port tests."""
import hashlib,json
from pathlib import Path
R=Path(__file__).resolve().parents[1];B=R/'build/opu-fence-source-v1'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 scan=json.loads((B/'tail-numeric-join.json').read_text());rows=[json.loads(l)for l in(B/'core-check-v2.stdout').read_text().splitlines()];assert rows[-1]['status']=='passed'and rows[-1]['runs']==48 and len(rows)==49
 cases=rows[:-1];lookup={(r['seed'],r['external_busy_mask'],r['fence']):r for r in cases}
 for seed in(1,17,31):
  for mask in range(8):
   x,y=[lookup[seed,mask,w]for w in(0x0ff0000f,0x0330000f)];assert all(x[k]==y[k]for k in('RRD','COM','CSR_RRD','CSR_COM'))and x['COM']==x['RRD']+3 and x['CSR_RRD']==x['RRD']+1 and x['CSR_COM']==x['RRD']+6
 assert scan['counts']==[4,8,0]and all(w['full_backend_busy']==w['trap_check_busy']==w['all_input_issue_queues_occupancy']==w['seq_busy']==w['TLreader_busy']==w['TLwriter_busy']==w['VU_busy']==0 and w['fp8_history']in(1,2,3)for w in scan['first_witnesses'])
 w=next(w for w in scan['first_witnesses']if w['hart']==1 and w['edge']==38700);assert w['owned_MRF_FP8_commits_next2edges']>0
 files=[Path(__file__).resolve(),R/'timing/opu_fence_tail_source_v1.py',R/'timing/opu_fence_core_source_check.cpp',R/'timing/opu_fence_core_source_check_v2.cpp',B/'core-check',B/'core-check.stdout',B/'core-check.stderr',B/'core-check-v2',B/'core-check-v2.stdout',B/'core-check-v2.stderr',B/'tail-scan.json',B/'tail-numeric-join.json',R/'iris_model/saturn_capture.py',R/'build/shuttle-lsu-phase-source-v1/build.json',R/'build/shuttle-lsu-phase-source-v1/initialize.hpp',R/'build/shuttle-lsu-phase-source-v1/obj/VShuttleLSUPhase__ALL.a',R/'build/shuttle-lsu-phase-source-v1/obj/verilated.o',R/'build/shuttle-lsu-phase-source-v1/obj/verilated_threads.o',R/'build/saturn-timing-activity-capture-v1/vme/activity.bin.gz',R/'build/saturn-timing-activity-capture-v1/vme/report.json',R/'build/saturn-timing-activity-contract-v2/contract.json',R/'build/saturn-timing-activity-schema-v1/schema.json',R/'build/saturn-timing-native-v1/compute/ports.json',R/'build/saturn-timing-native-v1/rocket/ports.json',R/'build/saturn-timing-ownership-proof-v2/vme-seed0-events.ndjson.gz',R/'build/saturn-timing-ownership-proof-v2/report.json']
 source_refs=[]
 for name,fragment in[
 ('third_party/shuttle/src/main/scala/exu/Core.scala','val rrd_fence_stall'),
 ('third_party/shuttle/src/main/scala/exu/Core.scala','val ex_fcsr_data_hazard'),
 ('third_party/saturn/src/main/scala/shuttle/Integration.scala','io.backend_busy   := vu.io.busy'),
 ('third_party/saturn/src/main/scala/shuttle/Frontend.scala','io.core.trap_check_busy := pfc.io.busy || ifc.io.busy'),
 ('third_party/saturn/src/main/scala/backend/Backend.scala','io.busy := vdq.io.deq.valid'),
 ('third_party/saturn/src/main/scala/mem/Mem.scala','io.busy := liq_valids.orR || siq_valids.orR'),
 ('third_party/saturn/src/main/scala/mem/TLInterface.scala','io.mem_busy := reader.module.io.busy || writer.module.io.busy'),
 ('third_party/saturn/src/main/scala/mem/SGTLInterface.scala','io.mem_busy := accessors.map(_.module.io.busy).orR'),
 ('hardware/evidence/outer-product-sequencer.scala','io.busy := valid'),
 ('hardware/evidence/outer-product-sequencer.scala','fp8_hist_valid := (fp8_hist_valid << 1) | (do_mm && mm_fp8)'),
 ('hardware/evidence/outer-product-unit.scala','def fp8MaccLatency = 2'),
 ('third_party/rocket-chip/src/main/scala/rocket/IDecode.scala','FENCE->     List(')]:
  p=R/name;text=p.read_text();assert fragment in text;files.append(p);source_refs.append(dict(path=str(p),line=text[:text.index(fragment)].count('\n')+1,literal=fragment,sha256=sha(p)))
 out=dict(schema='iris.OPU_FM0_FENCE_source_proof.v1',**{'pass':True},core_actual_runs=48,core_reset_seeds=[1,17,31],eligible_FM0_encodings=[0x0ff0000f,0x0330000f],FENCE_I_and_other_encodings_excluded=True,both_fences_have_identical_source_predicate_and_phase=True,Core_RRD_stall='EX|MEM|COM|integer-scoreboard|FP-scoreboard|!DCache.ordered|RoCCbusy|backend_busy|trap_check_busy',full_backend_busy='VU.busy|TLmem_busy|SGmem_busy|VMUbusy',VU_busy='VDQ.valid|allSeq.busy|allVectorEXU.busy',VMU_busy='LIQvalids|SIQvalids',TLbusy='reader.inflights|writer.inflights',trap_check_busy='PFC.busy|IFC.busy',FP8_tail_excluded_from_source_busy=True,source_tail_witnesses=scan['first_witnesses'],actual_future_MRF_publication_after_fullbusy_clear=True,Core_FENCE_COM_after_RRD=3,Core_next_CSR_RRD_after_FENCE_RRD=1,Core_next_CSR_COM_after_FENCE_RRD=6,legacy_native_immediate_CSR_static_join='ConservativeFENCE3 +nextCSR3 canmatchR+6 despitelaterCSR_RRD; no blanketpureFENCE rewrite justified forimmediateCSR alone. Nativefinitewitness stillrequired.',preedge_guard='If lastqueue.step(E) consumedtail, preedgeE wasbusy; onlynextsourceedge canuseempty poststate. Do notallowCPU dispatchusingpostedge q.empty on E.',safe_change='Release only FM0FENCE admission onfullsourcebusy/front/queueclear, preservelateMRFownership androwmove/RAW/IRQguards; sourceCPUCOM mayalreadyfollow thelastnumericwrite.',numeric_and_domain_scope='Raw control flags qualified byactualreset andsourcevalid-only equations. No arbitrary numericdefinedness inferred. Wholeunitobservations andCorephysicalboundarytests areseparate; no wholeCPU+VUloop/FPGA/2%certificate.',source_refs=source_refs,input_sha256={str(p):sha(p)for p in files},hardware_actions=False,hardware_error_labels_used=False,native_modified=False)
 (B/'report.json').write_text(json.dumps(out,indent=2)+'\n');print(sha(B/'report.json'))
if __name__=='__main__':main()
