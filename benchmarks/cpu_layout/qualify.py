#!/usr/bin/env python3
import copy,hashlib,itertools,json,pathlib
from verify import validate
ROOT=pathlib.Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def main():
 p=ROOT/'build/cpu-layout-v1';proof=json.loads((p/'binary-proof.json').read_text());reports=[];neg=[]
 for seed in [0,17]:
  r=json.loads((p/f'seed{seed}/results.json').read_text());assert r['exit_status']==0;lines=(p/f'seed{seed}/stdout').read_text().splitlines();rows=validate(lines,proof);reports.append({'seed':seed,'regions':len(rows),'exit_status':0,'host_seconds':r['host_seconds'],'results_sha256':sha(p/f'seed{seed}/results.json'),'stdout_sha256':sha(p/f'seed{seed}/stdout'),'no_op_controls':9})
  for field in ['checksum','loop_pc','instret_delta']:
   altered=list(lines);i=next(i for i,s in enumerate(altered) if s.startswith('IRIS_REGION '));bad=json.loads(altered[i][len('IRIS_REGION '):]);bad[field]+=1;altered[i]='IRIS_REGION '+json.dumps(bad)
   try:validate(altered,proof)
   except ValueError:neg.append({'seed':seed,'field':field,'rejected':True})
   else:raise ValueError('Corruption control accepted')
 cases=[]
 for mode,offset,n,rep in itertools.product(('compact','wide'),range(0,64,2),(16,64,256,1024),range(3)):
  cases.append({'id':f'cpu.layout.{mode}.off{offset}.n{n}.repeat{rep}','parent_case_id':f'cpu.layout.{mode}.off{offset}.n{n}','active_harts':[0,1,2],'region':'loop','expected_checksums_by_hart':[h+1+3*n for h in range(3)],'corpus_split':'cpu-layout-fit-v1','repeat_id':rep,'mode':mode,'loop_offset':offset,'n':n})
 for rep in range(3):cases.append({'id':f'cpu.layout.noop.off8.n0.repeat{rep}','parent_case_id':'cpu.layout.noop.off8.n0','active_harts':[0,1,2],'region':'loop','expected_checksums_by_hart':[1,2,3],'corpus_split':'cpu-layout-fit-v1','repeat_id':rep,'mode':'noop','loop_offset':8,'n':0})
 (p/'cases.json').write_text(json.dumps({'schema':'iris.cpu_layout_cases.v1','cases':cases,'required_regions':2313,'fitting_only':True,'global_heldout':False},indent=2)+'\n');sources=[ROOT/('benchmarks/cpu_layout/'+f) for f in ['main.c','generate.py','build.py','verify.py','qualify.py']];report={'schema':'iris.cpu_layout_qualification.v1','status':'passed','elf_sha256':sha(p/'batch.elf'),'binary_proof_sha256':sha(p/'binary-proof.json'),'functional':reports,'negative_controls':neg,'support_source_sha256':{str(f):sha(f) for f in sources},'hardware_contacted':False,'real_timing_qualified':False};(p/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
 ready={'schema':'iris.cpu_layout_ready.v1','status':'ready_for_root_managed_preparation','elf':str(p/'batch.elf'),'elf_sha256':sha(p/'batch.elf'),'cases_path':str(p/'cases.json'),'cases_sha256':sha(p/'cases.json'),'required_regions':2313,'parent_layouts':256,'main_regions':2304,'noop_regions':9,'harts':3,'fitting_only':True,'global_heldout':False,'numeric_goldens':'(hart+1)+3*N; counter_end=N; exactIRdelta3*N+2Shuttle/3Rocket','qualification_sha256':sha(p/'qualification.json'),'binary_proof_sha256':sha(p/'binary-proof.json'),'build_sha256':sha(p/'build.json'),'source_inputs_sha256':json.loads((p/'build.json').read_text())['input_sha256'],'support_source_sha256':report['support_source_sha256'],'proposed_runtime':{'target_cycles':1900000000,'host_workload_watchdog_seconds':360,'profile_interval_target_cycles':1000000},'conditions':{'measured_loop_pc_not_function_entry':True,'all_records_stored_before_UART_output':True,'cache_condition':'Fence.I beforefirstcall ofeachmode/offset/N;3immediatecalls;entry/paddingcanwarmline,nocoldtagclaim','uart_inside_measured_cases':False},'source_frozen_for_preparation':True,'hardware_contacted':False,'full_2pct_certified':False,'source_image_association_verified':False,'operator_policy':'Rootsolelaunch;fullmanagedkill/infrasetup/runworkload/kill withinspection/sharedlock/ownedcleanup/capture.'};(p/'ready.json').write_text(json.dumps(ready,indent=2)+'\n');print('READY',sha(p/'ready.json'))
if __name__=='__main__':main()
