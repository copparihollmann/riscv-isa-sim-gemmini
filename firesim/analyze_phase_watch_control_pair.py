#!/usr/bin/env python3
"""Offline paired evidence review; disabled noncompletion remains a failure."""
import argparse,datetime,hashlib,importlib.util,json,re,struct,sys,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
HELPER='5a041201107ff63e7a757b4eb06322ffb08c9ed04eb0237b3b2e9c360e0185cf'
ARCHIVES={'enabled':'589730a1e27b17d9bedcb69840bbad9940526b69efe7a2dd728852b3dcc32897','disabled':'37257c6fe7a7deda16179ce6ba5ba622e7df3a93a351fc87da84ddd2a1686176'}
ELFS={'enabled':'58280c6159245bac12cebbe1f0caa664ef7dd2d6e55502b86d4509a4cab5d444','disabled':'ee034bfcd6f20e1bb6dabf7e0f4c647da67d51609ec3cce44c54ce2d9193961a'}
def need(x,message):
 if not x:raise ValueError(message)
def hb(b):return hashlib.sha256(b).hexdigest()
def hf(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def pairs(kvs):
 o={}
 for k,v in kvs:need(k not in o,'Duplicate JSON key');o[k]=v
 return o
def js(raw):return json.loads(raw,object_pairs_hook=pairs)
def u(x):return type(x)is int and 0<=x<1<<64
def fnv(words):
 h=14695981039346656037
 for v in words:
  for b in struct.pack('<I',v):h=((h^b)*1099511628211)&0xffffffffffffffff
 return h
def independent_goldens():
 out=[]
 for dataset in range(3):
  values=[]
  for i in range(64):
   for j in range(64):
    acc=0
    for k in range(64):
     a=(17*i+11*k+3+5*dataset)%256;b=(13*k+7*j+5+9*dataset)%256
     a=a-256 if a>=128 else a;b=b-256 if b>=128 else b;acc=(acc+a*b)&0xffffffff
    values.append(acc)
  quant=[]
  for v in values:
   signed=v-(1<<32)if v&(1<<31)else v;q=max(-128,min(127,(signed+512)//1024));quant.append(struct.unpack('<I',struct.pack('<f',q))[0])
  out.append(dict(accumulator_u32=values,w8a8_f32_words=quant,accumulator_checksum=fnv(values),w8a8_checksum=fnv(quant)))
 return out
def numeric(text,corpus,variant,goldens):
 enabled=variant=='enabled';phases=2 if enabled else 1;get=lambda prefix:[js(s[len(prefix)+1:])for s in text.splitlines()if s.startswith(prefix+' ')]
 need(type(corpus.get('watchdog_enabled'))is bool and corpus['watchdog_enabled']is enabled and corpus['variant']==variant,'Typed watchdog variant')
 need(corpus.get('diagnostic_only')is True and corpus.get('fitting_allowed')is False,'Diagnostic only policy')
 need(not get('IRIS_DIAG_TIMEOUT')and not get('IRIS_HELDOUT_FATAL'),'No target diagnostic timeout/fatal')
 need(get('IRIS_DIAG_WATCHDOG')==([dict(hart=1,no_progress_ms=5000)]if enabled else[]),'Actual watchdog startup/hart')
 wantphases=[dict(phase=p,op='gemm',workers=1,kind='shipped'if p==0 else'twin')for p in range(phases)]
 need(get('IRIS_HELDOUT_PHASE')==wantphases,'Exact observed phase summaries')
 need(get('IRIS_UART_PROFILE')==[dict(requested_baud=3676470,clock_hz=500000000,divisor=135)],'Source UART profile')
 for tag in ['IRIS_DIAG_WATCHDOG','IRIS_DIAG_DONE','IRIS_BATCH_DONE','IRIS_UART_PROFILE','IRIS_HELDOUT_PHASE']:
  for value in get(tag):need(all(type(v)is int for v in value.values()if not isinstance(v,str)),'No bool masquerading as count '+tag)
 need(get('IRIS_DIAG_DONE')==([dict(phases=2,failed=0)]if enabled else[]),'No false diagnostic DONE')
 need(get('IRIS_BATCH_DONE')==([dict(failed=0,cases=32,regions=32,trials=5)]if enabled else[]),'No false batch DONE')
 need(re.findall(r'COMMAND_EXIT_CODE="([0-9]+)"',text)==(['0']if enabled else['124']),'Actual normal/host-timeout exit')
 for phase in range(1):
  for dataset in range(3):
   g=corpus['goldens'][phase][dataset];want=goldens[dataset]
   need(g['accumulator_u32']==want['accumulator_u32']and g['w8a8_f32_words']==want['w8a8_f32_words']and all(type(v)is int for v in g['accumulator_u32']+g['w8a8_f32_words']),'Independent full mathematical corpus')
 outputs=get('IRIS_HELDOUT_RESULT');need(len(outputs)==15*phases,'Complete observed phase output count')
 for index,v in enumerate(outputs):
  phase,job=divmod(index,15);g=goldens[job%3];want=dict(phase=phase,job=job,encoding='checked-word-hashes-v1',word_count=4096,accumulator_checksum=g['accumulator_checksum'],w8a8_checksum=g['w8a8_checksum'],mismatching_int32_words=0,mismatching_w8a8_words=0)
  need(v==want and all(type(v[k])is type(want[k])for k in want),'Independent per-invocation full-word checksums')
 producers=get('IRIS_HELDOUT_PRODUCER');need(len(producers)==phases,'Observed hart2 producer summaries');pg=fnv([7+(job%3)*8+n for job in range(15)for n in range(8)])
 for phase,v in enumerate(producers):
  need(v['phase']==phase and type(v['phase'])is int and v['hart']==2 and type(v['hart'])is int and v['jobs']==15 and type(v['jobs'])is int and v['vector_checksum']==pg and type(v['vector_checksum'])is int and v['vme_refused']is True,'Physical hart2 producer/refusal')
  need(len(v['overlap_masks'])==15 and all(type(x)is int and 0<=x<=1 for x in v['overlap_masks'])and any(v['overlap_masks'][:2]),'Actual overlap masks')
 rows=get('IRIS_REGION');need(len(rows)==16*phases,'Exact observed phase ROI count');cases=[c for phase in range(phases)for c in [corpus['cases'][16*phase+15],*corpus['cases'][16*phase:16*phase+15]]];need(len(corpus['cases'])==32,'Full32 source declaration');previous={}
 for row,c in zip(rows,cases):
  h=c['active_harts'][0];need(row['case_id']==c['id']and row['region']==c['region']and row['hart']==h and type(row['hart'])is int,'Canonical case/role/phase order')
  for k in ['start_cycle','end_cycle','instret_delta','checksum']:need(u(row[k]),'Typed ROI field '+k)
  need(row['end_cycle']>row['start_cycle']>=previous.get(h,0)and row['instret_delta']>0,'Observed counter progress');previous[h]=row['end_cycle'];need(row['checksum']==c['expected_checksums_by_hart'][h]and row['pass']is True,'Independent source ROI checksum')
  need(row.get('parent_case_id')==c['parent_case_id'],'Exact source case lineage')
  if h==0:
   need(row['checksum']==goldens[c['dataset_id']]['accumulator_checksum'],'Compute golden matches independent math')
   need(row.get('role')==('vme.compute'if '.shipped.'in c['id']else'scalar.compute')and row.get('hart_mask')==1 and type(row.get('hart_mask'))is int,'Compute role and mask')
   need(row.get('trial_id')==c['trial_id']and type(row.get('trial_id'))is int and row.get('dataset_id')==c['dataset_id']and type(row.get('dataset_id'))is int,'Typed trial/dataset')
  else:need(h==2 and row['checksum']==pg and row.get('role')=='pipeline.end_to_end'and row.get('scope')=='producer_entry_to_all_outputs_consumed','Producer golden and scope')
 return rows,dict(phases_completed=phases,jobs_numerically_checked=15*phases,regions=16*phases,embedded_int32_words_checked=4096*15*phases,embedded_W8A8_words_checked=4096*15*phases,full_math_recomputed=True,normal_completion=enabled,observed_exit_code=0 if enabled else 124,unobserved_phase1_claimed=False if not enabled else None)
def symbol(raw):
 need(raw[:7]==b'\x7fELF\x02\x01\x01','ELF64 little endian');so=struct.unpack_from('<Q',raw,40)[0];ss,sn=struct.unpack_from('<HH',raw,58);need(ss==64,'ELF section entry');secs=[struct.unpack_from('<IIQQQQIIQQ',raw,so+i*ss)for i in range(sn)];hits=[]
 for s in secs:
  if s[1]!=2:continue
  st=secs[s[6]];names=raw[st[4]:st[4]+st[5]]
  for pos in range(s[4],s[4]+s[5],s[9]):
   name,info,other,index,address,size=struct.unpack_from('<IBBHQQ',raw,pos)
   if name and names[name:].split(b'\0',1)[0]==b'iris_diag_watchdog_enabled':hits.append((address,size,index))
 need(len(hits)==1,'Unique actual watchdog symbol');address,size,index=hits[0];s=secs[index];need(size==1 and s[2]&2 and not s[2]&4 and s[1]!=8,'Retained allocated nonexec byte');return dict(address=address,file_offset=s[4]+address-s[3],size=1),secs
def pair_elf(on,off):
 a,sa=symbol(on);b,sb=symbol(off);need(a==b and sa==sb and len(on)==len(off),'Identical ELF tables/symbol addresses/length');diff=[i for i,(x,y)in enumerate(zip(on,off))if x!=y];need(diff==[a['file_offset']]and on[diff[0]]==1 and off[diff[0]]==0,'Actual captures differ only watchdog1/0 byte')
 need(all(on[s[4]:s[4]+s[5]]==off[s[4]:s[4]+s[5]]for s in sa if s[2]&4),'All executable sections identical');return dict(**a,differing_file_offsets=diff,all_other_ELF_bytes_identical=True,all_instruction_bytes_and_addresses_identical=True)
def lifecycle(m,current,ids,variant):
 expected='completed_uncertified'if variant=='enabled'else'failed';need(m['status']==current['status']==expected and m['cleanup_status']==current['cleanup_status']=='passed'and m.get('cleanup_error')is None and current.get('cleanup_error')is None,'Correct failed/completed outcome and owned cleanup')
 need((m.get('error')is None)if variant=='enabled'else m.get('error')=='Guest simulation console reports nonzero process exit: [124]','Correct host timeout failure reason')
 need(m['campaign_role']=='phase_watch_one_byte_control_v1'and m['diagnostic_only']is True and m['calibration_usable']is False and m['watch_pair_variant']==variant and m['watchdog_enabled']is(variant=='enabled'),'Exact diagnostic contract')
 grant=m['launch_authorization_receipt']['authorization'];lock=m['shared_lock'];need(lock['path']=='/scratch/firesim/iris-locks/fpga0'and lock['kind']=='exclusive_atomic_directory'and lock['uid']==grant['uid']==1003 and lock['boot_id']==grant['boot_id']and lock['authorization_id']==grant['authorization_id'],'Shared lock/user/boot ownership')
 begin=datetime.datetime.fromisoformat(grant['issued_at_utc'].replace('Z','+00:00'));end=datetime.datetime.fromisoformat(grant['expires_at_utc'].replace('Z','+00:00'));need(begin.tzinfo is not None and end>begin and hb(grant['instruction'].encode())==grant['instruction_sha256'],'Actual authorization bytes')
 need([c['task']for c in m['commands']]==['kill','infrasetup','runworkload','kill'],'Full lifecycle')
 for i,c in enumerate(m['commands'],1):
  need(type(c['phase_index'])is int and c['phase_index']==i and type(c['returncode'])is int and c['returncode']==0 and c['status']=='passed'and c['timed_out']is False and c['cleanup_phase']is(i==4),'Passed manager lifecycle with separate guest outcome')
  start=datetime.datetime.fromisoformat(c['started_at_utc']);need(begin<=start and start+datetime.timedelta(seconds=c['host_elapsed_seconds'])<=end,'Current actual phase grant')
  for suffix in ['stdout','stderr']:need(ids['job/'+c[suffix+'_path']]==c[suffix+'_sha256'],'Raw phase stream')
  for k,f in [('manager_sha256','prepared_manager_sha256'),('runtime_sha256','execution_runtime_sha256'),('hwdb_sha256','prepared_hwdb_sha256')]:need(c['actual_input_sha256'][k]==m[f],'Actual phase input')
 stages={e['stage']:e['report']for e in m['safety_inspections']}
 for stage in ['kill','infrasetup','runworkload','cleanup']:
  p=stages[stage];need(p['inspection_complete']is True and p['inspection_errors']==[]and p['boot_id']==grant['boot_id']and p['inspection_euid']==0 and p['launch_authorization_verified']is True and p['busy_processes']==[]and p['device_holders']==[],'Complete idle trusted phase safety')
 need(m['input_sha256']==current['input_sha256']and m['prepared_file_sha256']==current['prepared_file_sha256'],'Actual declarations immutable')
 for name,h in m['input_sha256'].items():need(Path(name).is_absolute()and ids.get('job/prepared-inputs/'+h)==h,'Named source snapshot missing')
 load=m['loader_override'];need(load['fesvr_step_size_target_cycles']==128 and load['target_cycle_bound']is None and load['remote_wall_watchdog_seconds']==600 and load['foreground']is True and load['driver_binary_unchanged']is True,'Same bounded source-supported loader')
 return[dict(task=c['task'],status=c['status'],host_elapsed_seconds=c['host_elapsed_seconds'])for c in m['commands']]
def review(enabled,disabled,output):
 need(not output.exists(),'Fresh output required');output.mkdir(parents=True);helper=R/'firesim/audit_memory_routes_current_independent.py';need(hf(helper)==HELPER,'Pinned archive reader');spec=importlib.util.spec_from_file_location('paired_memory_transport',helper);transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
 report=dict(schema='iris.actual_watchdog_one_byte_control_pair.v1',**{'pass':False},hardware_contacted=False,diagnostic_only=True,calibration_usable=False,timing_accuracy_qualified=False,source_image_association_verified=False,global_v6_reference_timing_labels_consumed=False,one_control_pair_only=True,universal_root_cause_proven=False,watchdog_is_a_hardware_fix=False,input_sha256={str(Path(__file__).resolve()):hf(__file__),str(helper):HELPER});records={};goldens=independent_goldens()
 try:
  for variant,job in [('enabled',enabled),('disabled',disabled)]:
   current=js((job/'run.json').read_bytes());cap=current['capture'];need(cap['status']=='captured'and cap['returncode']==0 and cap['archive_sha256']==ARCHIVES[variant]and hf(cap['archive'])==ARCHIVES[variant],'Exact successful quiescent archive')
   data,ids,total=transport.read_archive(cap['archive'],cap['captured_run_manifest_sha256']);m=js(data['job/run.json']);phases=lifecycle(m,current,ids,variant);need(ids['job/manager/workloads/iris-batch/batch.elf']==m['elf_sha256']==ELFS[variant],'Actual variant ELF')
   runtime=data['job/manager/config_runtime.yaml'];private=m['remote_simulation_dir'];need(private=='/scratch/agustin/firesim/'+m['lock_token'],'Owned run token path');old=('    default_simulation_dir: '+private+'\n').encode();need(runtime.count(old)==1,'Unique private runtime path');normal=runtime.replace(old,b'    default_simulation_dir: /scratch/firesim\n');need(hb(normal)==m['prepared_runtime_sha256']and ids['job/manager/config_runtime.yaml']==m['execution_runtime_sha256'],'Only private runtime transformation')
   for name,h in m['prepared_file_sha256'].items():need((hb(normal)if name=='manager/config_runtime.yaml'else ids.get('job/'+name))==h,'Prepared file changed')
   corpus=js(data['job/corpus.json']);need(ids['job/corpus.json']==m['corpus_sha256'],'Actual corpus bytes');logs=[n for n in data if n.endswith('/uartlog')];primary=[n for n in logs if n.startswith('job/manager/results-workload/')];need(len(primary)==1 and set(logs)<={primary[0],'job/optional-observability/uartlog'}and all(data[n]==data[primary[0]]for n in logs),'Unique consistent actual UART');text=data[primary[0]].decode();rows,numeric_report=numeric(text,corpus,variant,goldens)
   # Keep the existing full validator strict; it must accept enabled and refuse disabled.
   sys.path[:0]=[str(R/'zephyr'),str(R/'firesim')];from heldout_phase_watch_pair_validate import validate
   try:existing=validate(text,corpus['manifest'],corpus['cases'],corpus['goldens'],variant=='enabled');existing_accept=True
   except ValueError as e:existing=dict(error=str(e));existing_accept=False
   need(existing_accept is(variant=='enabled'),'Original full validator acceptance boundary preserved')
   (output/(variant+'.elf')).write_bytes(data['job/manager/workloads/iris-batch/batch.elf']);(output/(variant+'.uartlog')).write_bytes(data[primary[0]]);(output/(variant+'.regions.json')).write_text(json.dumps(rows,indent=2)+'\n');(output/(variant+'.manifest.json')).write_bytes(data['job/run.json'])
   report[variant]=dict(outcome='normal_completion'if variant=='enabled'else'FAILED_HOST_WATCHDOG_124',normal_completion=variant=='enabled',archive_sha256=ARCHIVES[variant],ELF_sha256=ELFS[variant],archive_files=len(ids),archive_bytes_rehashed=total,numeric=numeric_report,lifecycle=phases,source_inputs=len(m['input_sha256']),prepared_files=len(m['prepared_file_sha256']),original_full_validator_accepts=existing_accept,original_full_validator=existing,UART_sha256=ids[primary[0]],archive=str(cap['archive']))
   records[variant]=(m,ids,normal,corpus);report['input_sha256'][str(job/'run.json')]=hf(job/'run.json')
   for source in ['zephyr/heldout_phase_watch_pair_validate.py','zephyr/freeze_heldouts.py','zephyr/compiler_pipeline.py','zephyr/uart_profiles.py','firesim/batch_runner.py']:
    path=R/source;h=hf(path);need((m['runner_sha256']if source=='firesim/batch_runner.py'else m['input_sha256'].get(str(path)))==h and h in ids.values(),'Original full validator dependency bound '+source);report['input_sha256'][str(path)]=h
  on,off=records['enabled'],records['disabled'];report['actual_ELF_pair']=pair_elf((output/'enabled.elf').read_bytes(),(output/'disabled.elf').read_bytes())
  for field in ['image','driver','loader_override','prepared_manager_sha256','prepared_hwdb_sha256','prepared_runtime_sha256']:need(on[0][field]==off[0][field],'Same image/driver/config/loader '+field)
  a=js(json.dumps(on[3]));b=js(json.dumps(off[3]));[a.pop(k)for k in ['variant','watchdog_enabled']];[b.pop(k)for k in ['variant','watchdog_enabled']];need(a['manifest'].pop('ELF_sha256')==ELFS['enabled']and b['manifest'].pop('ELF_sha256')==ELFS['disabled'],'Explicit selected-variant manifest SHA');need(a==b,'Exact common math/case/parent manifest corpus')
  need(on[2]==off[2],'Normalized runtime bytes equal');samefiles=['manager/config_build.yaml','manager/config_build_recipes.yaml','manager/config_hwdb.yaml','manager/workloads/iris-batch.json','manager/firesim','manifest.json']
  for name in samefiles:need(on[1]['job/'+name]==off[1]['job/'+name],'Archived source manager/config byte mismatch '+name)
  report['artifact_identities']=transport.artifact_identities(on[0],on[1]);report['same_image_driver_and_configs_verified']=True;report['config_scope']='Exact archived config files and loader parameters equal; runtime differs only owned simulation directory; result paths and lifecycle times naturally distinct.'
  report['interpretation']='One managed enabled run completed both phases and one disabled run failed host watchdog after complete phase0. Same actual ELF except retained nonexec watchdog byte. The observer changes thread/timer/interrupt/scheduler/memory/FPU-owner history; no unique cause, remedy, universal liveness or timing-transfer claim.';report['pass']=True
 except(OSError,ValueError,KeyError,TypeError,IndexError,UnicodeError,struct.error,tarfile.TarError)as e:report['error']=str(e)
 report['artifact_sha256']={p.name:hf(p)for p in output.iterdir()if p.is_file()};(output/'report.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--enabled',type=Path,required=True);p.add_argument('--disabled',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=review(a.enabled.resolve(),a.disabled.resolve(),a.output.resolve());print(json.dumps({k:r.get(k)for k in ['pass','error','actual_ELF_pair']}));raise SystemExit(0 if r['pass']else 1)
