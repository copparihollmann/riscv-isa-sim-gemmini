#!/usr/bin/env python3
"""Freeze the independent frontend-OFF scalar-FADD mechanism finding, no labels."""
import collections,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 out=ROOT/'build/scalar-FADD-legacy-front-source-audit-v2';out.mkdir();native=ROOT/'pipeline/riscv-isa-sim-scalar-L2hit-v1/riscv';old=json.loads((ROOT/'build/scalar-fadd-candidate-next-v1/source-inventory.json').read_text());new=json.loads((ROOT/'build/scalar-L2hit-frozen-e8edb584/native-inventory.json').read_text());key='riscv/iris_scalar_fadd.inc';assert old['pipeline/riscv-isa-sim-scalar-fadd/'+key]==new[key]==sha(native/'iris_scalar_fadd.inc')
 ref=ROOT/'build/scalar-fadd-phase-closure-v1/report.json';prior=json.loads(ref.read_text());citations=[]
 for c in prior['source_citations']:
  p=Path(c['path']);assert sha(p)==c['sha256'];citations.append({k:c[k]for k in['path','sha256','line_ranges','claim']})
 on=ROOT/'build/scalar-FADD-legacy-front-e8ed-directed-ON-v1';result=json.loads((on/'report.json').read_text());rows=[]
 for name in ('dep','indep'):
  r=json.loads((on/name/'report.json').read_text());assert r['pass']is True
  events=[json.loads(s)for s in(on/name/'events.jsonl').read_text().splitlines()];ex=[e for e in events if e['event']=='scalar_fadd_EX'];com={(e['hart'],e['instruction']):e for e in events if e['event']=='scalar_fadd_COM'};wr={(e['hart'],e['instruction']):e for e in events if e['event']=='scalar_fadd_FPR_WRITE'};spans=[]
  for h in(0,1,2):
   accepted=[e for e in ex if e['hart']==h];gaps=[b['cycle']-a['cycle']for a,b in zip(accepted,accepted[1:])];min_gap=min(gaps)
   for x in accepted:
    key=(h,x['instruction']);assert com[key]['cycle']==x['cycle']+2 and wr[key]['cycle']==x['write']==x['cycle']+(4 if h<2 else 3)
   if name=='dep':assert min_gap==(5 if h<2 else 4)
   else:assert min_gap==1
   spans.append(dict(hart=h,actual_accepted=len(accepted),EX_min_gap=min_gap,EX_gap_histogram=dict(collections.Counter(gaps)),peak=r['metrics'][h]['peak'],FPR_write_minus_EX=4 if h<2 else 3,COM_minus_EX=2))
  rows.append(dict(case=name,source_phase_joins=len(ex),harts=spans))
 irq=json.loads((on/'irq/summary.json').read_text());numeric=(on/'irq/stdout').read_text().splitlines();assert len(numeric)==3 and all(s.startswith('SCALAR_EDGE ')and int(s.split()[2])==0 for s in numeric)
 paths=[Path(__file__).resolve(),ref,ROOT/'build/scalar-fadd-whole-RTL-proof-v2/report.json',ROOT/'build/scalar-fadd-RTL-control-v2/stdout',ROOT/'build/scalar-L2hit-frozen-e8edb584/manifest.json',ROOT/'build/scalar-L2hit-frozen-e8edb584/spike',ROOT/'build/scalar-L2hit-frozen-e8edb584/libsifive_uart.so',ROOT/'build/scalar-FADD-legacy-front-e8ed-inputs-v1/receipt.json',ROOT/'build/scalar-FADD-legacy-front-e8ed-inputs-v1/ON.fixture',ROOT/'build/scalar-FADD-legacy-front-e8ed-inputs-v1/OFF.fixture',on/'report.json',native/'iris_scalar_fadd.inc',native/'iris_shuttle_issue.cc',native/'iris_empirical_features.inc']
 for name in ('dep','indep','irq'):paths.extend(on/name/x for x in ['report.json','stdout','stderr','summary.json','events.jsonl'])
 r=dict(schema='iris.scalar_FADD_frontend_independent_source_mechanism.v1',status='qualified_finite_mechanism_with_explicit_IRQ_phase_coverage_gap',source_primitive_byteidentical_phase_qualified_9b4932=True,source_FADD_optin='empirical_scalar_fadd source-HSD-pipeline-v1',source_frontend_enabled=False,strict_RAS_dependency=False,source_edges=rows,phase_derivation='Shuttle EX reads FPR; scoreboard becomes ready at physical FPR write, no FPR bypass: next dependent EX earliest write+1. Rocket may admit ID at physical write, reads FPR at following EX: next dependent EX earliest write+1. Actor write latencies4/3 andCOM+2 were previously observed on actual saved wholeCPU.',independent_FP_admission_peak_per_hart=[4,4,3],max_source_FADD_accepts_per_hart_edge=1,postCOM_FPR_flags_FS_publication=True,FCSR_per_operation_flag_delta_OR=True,feature_schema='scalar.fadd.fp16/fp32/fp64; generic scalar.fp remains distinct and no old fitted coefficient is relabeled',unchanged_selected_parameter_bytes=True,actual_phase_checks_without_fitting=True,directed_modes_passed=['dep','indep','flags','round','kill','unknown-h0','unknown-h1','unknown-h2'],IRQ=dict(numerics_and_exit_passed_all3=True,exact_delivery_phase_qualified=False,pending_arrival_witness_all3=False,deferral_edges=[x['irq_drain_edges']for x in irq['scalar_fadd_metrics']],original_test_failure_preserved=str(on/'irq/report.json')),limitations=['Only finite nonmemory FADD H/S/D in M-mode with correct operand/control knownness; other FP/shared CP/context domains conservatively drain.','Source counters/frontend/memory history and instruction footprint also affect ROI timing; independent unrolled body has a different Icache footprint than short dependent loop.','Saved-source 288FADD/9region phase proof and component140504checks qualify local phases, not arbitrary wholeSoC or deployedimage equivalence.','No current new576allcase result until normalexit+allregionsvalidator pass.'],source_citations=citations,hardware_contacted=False,global_heldout_timings_consumed=False,reserved_hardware_timing_labels_consumed=False,parameter_fit_performed=False,source_image_association_verified=False,full_2pct_certified=False,input_sha256={str(p):sha(p)for p in paths})
 (out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(status=r['status'],report_sha256=sha(out/'report.json'))))
if __name__=='__main__':main()
