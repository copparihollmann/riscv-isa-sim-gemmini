#!/usr/bin/env python3
"""Close finite source-mechanism evidence without asserting FPGA timing accuracy."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);a=ap.parse_args();o=Path(a.output).resolve();o.mkdir(parents=True,exist_ok=False)
 paths={
 'source_queue':'build/overlap-completion-queue-source-differential-v2/report.json',
 'source_sequencer':'build/overlap-completion-entry-schedule-differential-v1/report.json',
 'native_source_reconstruction':'build/opu-entry-overlap-frozen-b6ee38ea-v2/verification.json',
 'finite_ON_168':'build/overlap-completion-entry-queue-final-ON-v1/run.json',
 'full_MRF_wrongpath':'build/overlap-completion-fullcell-guards-final-ON-v1/report.json',
 'idle_cancel_reaccept':'build/overlap-completion-idle-reaccept-final-v1/report.json',
 'refusals':'build/overlap-completion-refusal-guards-v5/report.json',
 'fetch_boundary_refusal':'build/overlap-completion-fetch-boundary-refusal-proof-v1/report.json',
 'OFF_same_ELF_parity':'build/overlap-completion-b6ee-OFF-parity-v1/report.json',
 'OFF_canonical32':'build/overlap-completion-b6ee-functional32-OFF-v1/results.json',
 'OFF_Zephyr5':'build/overlap-completion-b6ee-Zephyr5-OFF-v1/report.json',
 'OFF_package':'build/overlap-completion-queue-OFF-package-selftest-v1/report.json',
 'OFF_launcher7':'build/overlap-completion-b6ee-launcher7-v1/report.json',
 'boundary_source_audit':'build/overlap-completion-boundary-source-audit-v1/report.json',
 'model_prediction':'build/overlap-completion-b6ee-prediction-v2/prediction.json'}
 evidence={}
 for name,path in paths.items():
  p=ROOT/path;j=json.load(open(p));passed=j.get('pass')is True or j.get('status','').startswith('passed_');assert passed,name;evidence[name]={'path':str(p),'sha256':sha(p)}
 r=json.load(open(ROOT/paths['full_MRF_wrongpath']));assert r['numeric_words']==106496 and r['normal_HTIF_guest_exit']is True
 j=json.load(open(ROOT/paths['finite_ON_168']));assert j['normal_HTIF_exit']is False and j['forced_debug_quit']is True and j['actual_cycle_endpoints']==672
 # Independent exact ownership joins, not only aggregate cancellation counts.
 trp=ROOT/'build/overlap-completion-fullcell-guards-final-ON-v1/async.jsonl';tr=[json.loads(l)for l in trp.read_text().splitlines()];b=json.load(open(ROOT/'build/overlap-completion-fullcell-guards-guest-v1/build.json'));bad=set(b['wrongpath_MM_PCs'].values());acc={(x['hart'],x['instruction'])for x in tr if x['event']=='opu_front_accept'and x['pc']in bad};cancel={(x['hart'],x['instruction'])for x in tr if x['event']=='opu_front_cancel'};iss=[x for x in tr if x['event']=='opu_microissue_reserved'];pub=[x for x in tr if x['event']=='opu_entry_publish'];assert len(acc)==30 and acc<=cancel and not any((x['hart'],x['instruction'])in acc for x in iss);assert len(iss)==len(pub)==12288 and sum(x['macs']for x in iss)==2752512 and all(x['pc']for x in iss)
 report={'schema':'iris.opu_entry_finite_readiness.v1','pass':True,'ready_for_scoped_component_integration':True,'native_binary_sha256':'b6ee38eabfeb8b0db18cf9a731b46f1aaee958088c2df19dda89d5feafc349f7','UART_sha256':'9e009ea0e5e545c692183bde7ad165890c01fc59d576f41cb69af2d36190ff2b','mode_default':'OFF','default_provider_changed':False,'ON_full_OS_timing_available':False,'ON_normal_exit_full_MRF_words':106496,'ON_controlled_readback168_words':19872,'wrongpath_actual_front_accepts_canceled':30,'wrongpath_physical_microissues_MAC_credit':0,'completed_source_entry_events':12288,'source_event_logical_MACs':2752512,'source_queue_checks':321456,'evidence':evidence,'input_sha256':{str(p):sha(p)for p in(Path(__file__).resolve(),trp,ROOT/'build/overlap-completion-fullcell-guards-guest-v1/build.json',ROOT/'build/opu-entry-overlap-frozen-b6ee38ea-v2/manifest.json')},'scope':['Conditional source VDQ4(no pipe)/IQ3(pipe)/one OPU sequencer and perentry FP8 history','Only finite positive TM/TN<=32 TK1, stable defined VRF, compute harts0/1, M-mode; initialized MRF required','Conservative predictive CPU admission and COM+1 availability are explicit unqualified bridge policy','FENCE/config wait for all owned physical writes conservatively; source backend_busy may clear earlier','Active IRQ context and unsupported MM CPU fetch boundary refuse; no unknown reset relaxation','Callback-clock occupancy is simulation bookkeeping; only zero-duration source write points carry completion MAC credit','Retired-prefix MAC features describe architectural intent separately from source completion events'],'failed_epochs_preserved':['build/overlap-completion-failed-native-ba88-v1','build/overlap-completion-initial-unbounded-native-db2d-v1','build/overlap-completion-queue-native-bdc-preserved-v1','build/overlap-completion-MRF-version-diagnostic-v3','build/opu-entry-overlap-frozen-b6ee38ea-v1/freeze-failure.json'],'timing_reference_consumed':False,'reserved_reference_consumed':False,'parameters_fitted':False,'FPGA_image_association':False,'timing_2pct_certified':False,'full_model_certified':False,'hardware_contacted':False}
 (o/'readiness.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'sha256':sha(o/'readiness.json'),'evidence_groups':len(evidence)}))
if __name__=='__main__':main()
