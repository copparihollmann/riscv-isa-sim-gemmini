#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,os,subprocess,sys,time
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R));from iris_model.graph_run_buffered import kill_owned
from spike.empirical_launch_v2 import launcher_text
O=R/'build/C12-VADD-EG-OPU-journal-parity-v1';O.mkdir();parent=R/'build/C12-VADD-EG-frozen-3a5f5857-v1';current=R/'build/C12-VADD-EG-frozen-35a80496-v2';fixture=R/'build/C12-VADD-EG-inputs-v2/ON.fixture';refpath=R/'build/opu-fence-ON-fullcell-TK4-v1/report.json';ref=json.loads(refpath.read_text());sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();runs=[];inputs=[Path(__file__),parent/'manifest.json',current/'manifest.json',fixture,refpath,Path(ref['argv'][-1])]
for name,cap,trace in [('parent3a-traceON',parent,True),('new35-traceON',current,True),('new35-traceOFF',current,False)]:
 d=O/name;d.mkdir();launch=d/'spike';launch.write_text(launcher_text(cap/'spike',sha(cap/'spike'),Path(sys.executable).resolve(),sha(Path(sys.executable).resolve())));launch.chmod(0o755);inputs.extend([cap/'spike',cap/'libsifive_uart.so']);argv=[str(launch)if i==0 else'--iris-timing-fixture='+str(fixture)if x.startswith('--iris-timing-fixture=')else'--iris-timing-trace='+str(d/'summary.json')if x.startswith('--iris-timing-trace=')else'--extlib='+str(cap/'libsifive_uart.so')if x.startswith('--extlib=')else x for i,x in enumerate(ref['argv'])];env={k:v for k,v in os.environ.items()if not k.startswith(('IRIS_EMPIRICAL_','IRIS_CPU_DIAGNOSTIC_'))};env['IRIS_EMPIRICAL_FEATURES']=str(d/'features.jsonl')
 if trace:env['IRIS_EMPIRICAL_ASYNC_TRACE']=str(d/'async.jsonl')
 start=time.monotonic()
 with(d/'stdout').open('wb')as so,(d/'stderr').open('wb')as se:
  p=subprocess.Popen(argv,env=env,stdout=so,stderr=se,start_new_session=True)
  try:c=p.wait(timeout=180);timed=False
  except subprocess.TimeoutExpired:kill_owned(p);c=p.returncode;timed=True
 row=dict(name=name,argv=argv,exit_status=c,timed_out=timed,host_seconds=time.monotonic()-start,**{'pass':c==0 and not timed and'OPU_GUARD_PASS'in(d/'stdout').read_text()and not(d/'stderr').read_bytes()},normal_guest_exit=c==0 and not timed,numeric_words=ref['numeric_words'],input_sha256={str(p):sha(p)for p in(cap/'spike',cap/'libsifive_uart.so',fixture,Path(argv[-1]))},output_sha256={str(p):sha(p)for p in d.iterdir()if p.is_file()});(d/'run.json').write_text(json.dumps(row,indent=2)+'\n');runs.append(row);assert row['pass'],row
for name in('stdout','stderr','features.jsonl','summary.json'):
 values=[(O/x/name).read_bytes()for x in('parent3a-traceON','new35-traceON','new35-traceOFF')];assert values[0]==values[1]==values[2],('Logging changed model/numeric/counter output',name)
events=[json.loads(l)for l in(O/'new35-traceON/async.jsonl').read_text().splitlines()];com={};reserved={};kmicro={};written={}
for e in events:
 key=e.get('hart'),e.get('instruction')
 if e['event']=='opu_functional_COM':
  assert key not in com and e['geometry_authority']=='checked_architectural_COM'and e['kind']=='matrix_multiply';assert(e['TM'],e['TN'],e['TK'])==(e['controller_TM'],e['controller_TN'],e['controller_TK']);assert e['raw']&0x7f==0x77 and e['destination_encoding']==(e['raw']>>7)&31 and e['vs1']==(e['raw']>>15)&31 and e['vs2']==(e['raw']>>20)&31;com[key]=e
 elif e['event']=='opu_microissue_reserved':reserved[key,e['entry'],e['seq']]=e
 elif e['event']=='opu_K_microissue':kmicro[key,e['entry'],e['cycle']]=e
 elif e['event']=='opu_K_write_owner':
  k=(key,e['entry'],e['k']);assert k not in written and key in com and e['projected_MRF_published']is e['last_k'];written[k]=e
for (key,entry,seq),r in reserved.items():
 k=kmicro[key,entry,seq];w=written[key,entry,k['k']];assert w['cycle']==r['write']and w['macs']==r['macs']==k['macs']and w['last_k']==k['last_k']and w['cells']==w['macs'];assert w['last_k']==(w['k']+1==com[key]['TK'])and com[key]['cycle']<seq
assert len(written)==len(reserved)==len(kmicro)and com
for key,c in com.items():assert sum(w['macs']for (owner,entry,k),w in written.items()if owner==key)==c['TM']*c['TN']*c['TK']
r=dict(schema='iris.C12_VADD_EG_OPU_authoritative_journal_controls.v1',**{'pass':True},actual_normal_runs=3,independent_fullMRF_words_per_run=ref['numeric_words'],parent_new_and_trace_toggle_stdout_counter_summary_byte_parity=True,authoritative_COM_records=len(com),unique_entry_K_write_owner_records=len(written),logical_MAC_sum_from_actual_owner_completions=sum(e['macs']for e in written.values()),all_entry_K_and_geometry_joins_complete=True,intermediate_K_projected_MRF_published=False,TMOVE_authoritative_journal_qualified=False,CPU_COMplus1_bridge_qualified=False,physical_hardware_utilization_or_bandwidth_claim=False,native_or_fixture_changed_during_tests=False,hardware_or_protected_labels_consumed=False,runs=runs,input_sha256={str(p):sha(p)for p in inputs});(O/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'pass':True,'COM':len(com),'K_writes':len(written),'report_sha256':sha(O/'report.json')}))
