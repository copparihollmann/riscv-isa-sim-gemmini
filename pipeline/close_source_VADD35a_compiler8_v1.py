#!/usr/bin/env python3
"""Bind actual35a native compiler-image executions; no old pass receipt reuse."""
import argparse,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(v,s):
 if not v:raise ValueError(s)
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--runs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();rpath=a.runs.resolve();r=json.loads(rpath.read_text());out=a.output.resolve();out.mkdir(exist_ok=False)
 need(r.get('pass')is True and len(r['cases'])==8,'All eight fresh normal native runs required');need(r['native_binary_sha256']=='35a804964d7882f36a8892d7672dcfbbc7becc89c87e2d830c149820c1291388'and r['uart_sha256']=='1723a1679f429b57d6a1aacf4a5f33e1f12c5cb35ccb8c4730975302ed60c6c0'and r['fixture_sha256']=='b1c752150d7c6b2427772076bf20e852a7d2142fdcc8b74c4dd380bf369eb328','Exact35a pair and fixed prospective fixture');need(r['actual_Merlin_adapter_or_provider_used']is False,'Native-only gate scope')
 for name,digest in r['input_sha256'].items():need(sha(name)==digest,'Changed input '+name)
 wanted={(op,n,kind)for op in('gemm','conv2d')for n in(1,2)for kind in('shipped','twin')};need({(x['op'],x['workers'],x['kind'])for x in r['cases']}==wanted,'Exact eight compiler cases')
 rows=[];ids=dict(r['input_sha256']);ids[str(rpath)]=sha(rpath);ids[str(Path(__file__).resolve())]=sha(__file__)
 for row in r['cases']:
  need(row['pass']is True and row['normal_guest_exit']is True and row['exit_status']==0 and row['timed_out']is False and row['accumulator_words']==4096 and row['w8a8_words']==4096,'Actual normal exit and full independent goldens')
  need(row['physical_harts']==3 and row['active_hart_ids']==list(range(row['workers']))and row['unstripped_ELF_fatal_parser_validated']is True,'Hart and fatal parser coverage')
  for name,digest in row['output_sha256'].items():need(sha(name)==digest,'Changed output '+name)
  folder=rpath.parent/row['name'];summary=json.loads((folder/'summary.json').read_text());need(summary['calibration_identity']=='iris-C12-source-VADD-fixed-costs-v1','Actual native selected fixture identity');need(len(summary['retired_instructions'])==3 and all(n>0 for n in summary['retired_instructions']),'All three physical harts actually booted/retired')
  argv=row['argv'];need('-p3'in argv and sum(x.startswith('--iris-timing-fixture=')for x in argv)==1,'Unique actual fixture/3harts')
  per={}
  for v in argv:
   if v.startswith('--hart-isa='):
    h,isa=v.split('=',1)[1].split(':',1);need(h not in per,'Duplicate perhartISA');per[h]=isa
  need(set(per)=={'0','1','2'}and all(all(e in per[str(h)].split('_')for e in('zvt32t','zvti8i32mm','zvtofp8fmm'))for h in(0,1))and not any(e in per['2'].split('_')for e in('zvt32t','zvti8i32mm','zvtofp8fmm')),'Heterogeneous functional ISA limits preserved')
  rows.append(dict(name=row['name'],normal_exit=True,accumulator_words=4096,w8a8_words=4096,active_harts=row['active_hart_ids'],actual_kernel_CSR_regions=row['regions'],fatal_symbol_to_PC=row['fatal_symbol_to_PC'],retired_instructions=summary['retired_instructions'],model_cycles=summary['cycles'],pending_async_backends_at_exit=summary['pending_async_backends'],VADD_metrics=summary['vadd_EG_metrics'],FADD_metrics=summary['fadd_EG_metrics'],OPU_metrics=summary['opu_entry_metrics']))
  for p in folder.iterdir():
   if p.is_file():ids[str(p)]=sha(p)
 report=dict(schema='iris.source_VADD35a_compiler8_closure.v1',**{'pass':True},native_binary_sha256=r['native_binary_sha256'],uart_sha256=r['uart_sha256'],fixture_sha256=r['fixture_sha256'],capsule_manifest_sha256=r['source_capsule_manifest_sha256'],cases=rows,total_INT32_words=32768,total_W8A8_words=32768,physical_harts=3,timed_compute_harts=[0,1],hart2_functional_control_only=True,actual_fresh_native_executions=True,preserved_ELFs_no_new_compiler_invocation=True,all_fatal_symbol_maps_recorded=True,old_adapter_provider_default_or_source_changes=False,hardware_or_protected_labels_accessed=False,new_fitting_or_timing_acceptance_claim=False,source_image_attested=False,input_sha256=ids)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(pass_=True,cases=8,report_sha256=sha(out/'report.json'))))
if __name__=='__main__':main()
