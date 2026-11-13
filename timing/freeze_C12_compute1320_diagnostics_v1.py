#!/usr/bin/env python3
"""Close two byte-bound source diagnostics without fitting or model selection."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def main():
 p=argparse.ArgumentParser()
 for n in('inherited','zero','derivation','output'):p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);der=json.loads(a.derivation.read_text());need(der['pass']is True and der['exactly14_lines']is True and der['only_setup_and_work_tokens_changed']is True and der['all_other_bytes_identical']is True,'Exact14-family source derivation required');need(sha(der['parent'])==der['parent_sha256']and sha(der['fixture'])==der['fixture_sha256'],'Fixture derivation unchanged')
 native=ROOT/'build/warm-OPU-TK124-frozen-c12a08f7-v1';capsule=json.loads((native/'manifest.json').read_text());runs={};inputs={str(Path(__file__).resolve()):sha(Path(__file__).resolve()),str(a.derivation.resolve()):sha(a.derivation)}
 for mode,d in(('inherited',a.inherited.resolve()),('zero_adjustment',a.zero.resolve())):
  path=d/'run.json';r=json.loads(path.read_text());need(r.get('pass')is True and r.get('timed_out')is False and r.get('debugger_exit_status')==0,'Completed own source replay required '+mode)
  need(r['normal_guest_exit_verified']is False and r['intentional_postmeasurement_debugger_stop']is True and r['whole_run_timing_or_speed_claim']is False,'Exact controlled-stop scope required')
  need(r['regions']==1320 and r['complete_per_element_goldens']==184128 and r['actual_CSR_ELF_endpoint_joins']==3960 and r['actual_mcycle_prefix_records']==3960,'Full numeric and actual CSR endpoint gates required')
  expected_fixture=der['parent']if mode=='inherited'else der['fixture'];wanted='--iris-timing-fixture='+expected_fixture;need(wanted in r['argv'],'Exact own fixture required')
  need(r['input_sha256'].get(str(native/'spike'))==capsule['binary_sha256']and r['input_sha256'].get(str(native/'libsifive_uart.so'))==capsule['uart_sha256'],'Exact C12 native/UART required')
  for q,h in r['input_sha256'].items():need(sha(q)==h,'Changed replay input '+q)
  for q,h in r['output_sha256'].items():need(sha(q)==h,'Changed replay output '+q)
  rows=[json.loads(x)for x in(d/'regions.jsonl').read_text().splitlines()];need(len(rows)==1320 and {x['hart']for x in rows}=={0,1},'Both complete compute-hart result sets required')
  inputs[str(path)]=sha(path);inputs.update(r['input_sha256']);inputs.update(r['output_sha256'])
  runs[mode]={'path':str(path),'sha256':sha(path),'regions':1320,'checked_elements':184128,'actual_CSR_ELF_endpoint_joins':3960,'fixture_sha256':sha(expected_fixture),'native_binary_sha256':capsule['binary_sha256'],'UART_sha256':capsule['uart_sha256'],'host_seconds':r['host_seconds'],'normal_guest_exit_verified':False,'intentional_postmeasurement_debugger_stop':True}
 report={'schema':'iris.C12_compute1320_source_diagnostics.v1','pass':True,'runs':runs,'derivation':str(a.derivation.resolve()),'derivation_sha256':sha(a.derivation),'native_binary_sha256':capsule['binary_sha256'],'inherited_costs_are_newly_calibrated':False,'zero_adjustment_is_a_fit':False,'parameters_fitted':False,'model_selection_performed':False,'calibrated_provider_available':False,'fixed7108_fitting_plan_changed':False,'hardware_or_reserved_timing_labels_consumed':False,'hardware_contacted':False,'whole_CPU_timing_certified':False,'source_image_association':False,'timing_2pct_certified':False,'scope':'Same exact1320ELF and frozen C12;14 eligible h0/1 family setup/work changes only; memory/cache transport and II, hart2, source OPU controller, vme.zero and source flags unchanged. Actual measured regions and guest element checks/CSR joins, not normal HTIF or whole-run timing.','input_sha256':inputs}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'report':str(out/'report.json'),'sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
