#!/usr/bin/env python3
"""Second stdlib-only operator audit: independent canonical math and evidence.

Only byte transport, managed-lifecycle and artifact-ID functions are reused from
an explicitly digest-pinned independent memory auditor. No operator validator,
preparer, analyzer, simulator or compiler module is imported.
"""
import argparse,ast,collections,datetime,hashlib,importlib.util,json,math,re,struct,tarfile
from pathlib import Path

HELPER_SHA='5a041201107ff63e7a757b4eb06322ffb08c9ed04eb0237b3b2e9c360e0185cf'
ARCHIVE_SHA='3336c6860cef53cb918cdd04f075aa72c6f9c2db2e5cfc8a0f1d9407c88ac56a'
ELF_SHA='af22419f8b095dfce0cf388468b0d0d88c251b130172ba3719b5e16154ca36f4'
CORPUS_SHA='3a989364d75d0754825c5716d0eb632af5e767b313234be1addbcecc62b2c41c'
ROLE='model_operator_protected_validation_v1'
MODELS=(('gemma4-e4b',2560,'google/gemma-4-E4B-it','4ecc2ba63bcac23ba4a767fc87025b1450f84c9c','33b10c02df3c2e8536cf323d29d53262aaa2f4d11dbe19bc729373fbe90295d4'),('gpt-oss-20b',2880,'openai/gpt-oss-20b','6cee5e81ee83917806bbde320786a8fb61efebee','3a2a26ded679375b7928ddeca59764df7cea83220c1961035f6d6e232659e9ce'),('meta-official-reference',4096,None,'689c7f261b9c5514636ecc3c5fefefcbb3e6eed7','b409ea3db2a4029afd4129246d3b5e76ea95b6503364842545403dbcd7476281'),('tinyllama-base',2048,'TinyLlama/TinyLlama-1.1B-intermediate-step-1431k-3T','59f6f375b26bde864a6ca194a9a3044570490064','7ef24df4204405995b8a3936355171b0d80f64fc3bc0ca5991158eaa5c75de50'))

def need(ok,message):
 if not ok:raise ValueError(message)
def hb(raw):return hashlib.sha256(raw).hexdigest()
def hf(path):
 h=hashlib.sha256()
 with Path(path).open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def pairs(items):
 r={}
 for k,v in items:need(k not in r,'Duplicate JSON key');r[k]=v
 return r
def js(raw):return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in()).throw(ValueError('Nonfinite JSON constant')))
def ui(x,bits=64):return type(x)is int and 0<=x<1<<bits
def same(a,b):return type(a)is type(b)and a==b
def fnv(raw):
 value=14695981039346656037
 for byte in raw:value=((value^byte)*1099511628211)&0xffffffffffffffff
 return value
def word_bytes(words):return b''.join(x.to_bytes(4,'little')for x in words)

def canonical():
 rows=[]
 for trial in range(3):
  for name,k,model,revision,source in MODELS:
   for workers in(1,2):
    for variant in('shipped','twin'):
     rows.append(dict(case_id='model.operator.batch.v1.%s.workers%d.%s.trial%d'%(name,workers,variant,trial),name=name,k=k,model_id=model,revision=revision,config_sha256=source,workers=workers,variant=variant,trial_id=trial,active_harts=list(range(workers))+[2],parent='%s.workers%d.%s'%(name,workers,variant)))
 need(len(rows)==48,'Independent canonical case count');return rows

def math_case(k,trial):
 """Independent i,j,k signed-byte multiply with explicit modulo32 each add."""
 output=[]
 for i in range(2):
  for j in range(32):
   accumulator=0
   for q in range(k):
    au=(17*i+11*q+3+19*trial)%256;bu=(13*q+7*j+5+23*trial)%256
    av=au-256 if au>=128 else au;bv=bu-256 if bu>=128 else bu
    accumulator=(accumulator+av*bv)&0xffffffff
   output.append(accumulator)
 quantized=[]
 for bits in output:
  signed=bits-0x100000000 if bits&0x80000000 else bits
  # Division by2^10 is exact for the bounded32-bit integer in binary64.
  rounded=math.floor((signed+512)/1024);clamped=max(-128,min(127,rounded))
  quantized.append(struct.unpack('<I',struct.pack('<f',float(clamped)))[0])
 a=bytes((17*i+11*q+3+19*trial)%256 for i in range(2)for q in range(k))
 b=bytes((13*q+7*j+5+23*trial)%256 for q in range(k)for j in range(32))
 return dict(accumulator_u32=output,W8A8_f32_words=quantized,producer_hash=fnv(a+b+word_bytes([x^0xffffffff for x in output])))

def math_all():return{(k,t):math_case(k,t)for _name,k,*_ in MODELS for t in range(3)}

def check_corpus(corpus,calculations):
 need(corpus.get('schema')=='iris.model_operator_validation_batch.v1'and corpus.get('split_id')=='iris-model-operator-protected-validation-v1','Exact protected corpus')
 for key,want in [('trials',3),('required_regions',120),('full_int32_words',3072),('full_W8A8_words',3072)]:need(same(corpus.get(key),want),'Corpus typed count '+key)
 need(corpus.get('all_cases_validation_only')is True and corpus.get('TinyLlama_protected_validation_only')is True and corpus.get('calibration_usable')is False and corpus.get('full_model_qualified')is False and corpus.get('exact_Llama2_checkpoint_admitted')is False,'Protected policy/fullmodel boundary')
 wanted=canonical();need(type(corpus.get('cases'))is list and len(corpus['cases'])==48,'Complete case corpus')
 for c,w in zip(corpus['cases'],wanted):
  for key in ['case_id','workers','variant','trial_id','active_harts']:need(same(c.get(key),w[key]),'Corpus canonical order/control '+key)
  need(all(ui(h)for h in c['active_harts']),'Typed corpus active harts')
  need(c.get('semantic_parent_case_id')==w['parent']and c.get('validation_only')is True and c.get('calibration_usable')is False,'Case validation-only lineage')
  s=c['source_case'];need(s.get('case_id')==w['name']and s.get('model_id')==w['model_id']and s.get('revision')==w['revision']and s.get('source_config_sha256')==w['config_sha256'],'Exact model/source identity')
  need(s.get('shape_mnk')==[2,32,w['k']]and all(type(x)is int for x in s['shape_mnk'])and same(s.get('workers'),w['workers'])and same(s.get('physical_harts'),3)and same(s.get('cpu_producer_hart'),2),'Source shape and physical placement')
  need(s.get('weights_used')is False and s.get('checkpoint_numeric_policy_qualified')is False and s.get('fit_eligible')is False,'No checkpoint/quantizer/fitting claim')
  need(s.get('validation_only')is(w['name']=='tinyllama-base'),'TinyLlama protection')
  if w['name']=='meta-official-reference':need(s.get('exact_checkpoint_admitted')is False and s.get('requested_model_id')=='meta-llama/Llama-2-7b-hf','Official Meta reference is not gated checkpoint admission')
  g=calculations[(w['k'],w['trial_id'])]
  need(set(c['expected_words'])==set(g),'Full independent mathematical corpus')
  for key in ['accumulator_u32','W8A8_f32_words']:need(type(c['expected_words'][key])is list and len(c['expected_words'][key])==64 and all(ui(x,32)for x in c['expected_words'][key])and c['expected_words'][key]==g[key],'Independent corpus fullwords '+key)
  need(ui(c['expected_words']['producer_hash'])and c['expected_words']['producer_hash']==g['producer_hash'],'Independent producer corpus')
  checks={str(h):fnv(word_bytes(g['accumulator_u32'][h*(64//w['workers']):(h+1)*(64//w['workers'])]))for h in range(w['workers'])};checks['2']=g['producer_hash']
  need(c['expected_checksums']==checks and all(ui(x)for x in c['expected_checksums'].values()),'Independent perhart corpus checksum')
 return wanted

def check_uart(raw,wanted,calculations):
 text=raw.decode('utf-8','strict');need('IRIS_FATAL'not in text and 'IRIS_PROBE_TIMEOUT'not in text,'No fatal/timeout console')
 regions=[];outputs=[];done=[]
 for line in text.splitlines():
  for prefix,dest in [('IRIS_REGION ',regions),('IRIS_WORDS ',outputs),('IRIS_BATCH_DONE ',done)]:
   if line.startswith(prefix):dest.append(js(line[len(prefix):]))
 need(len(regions)==120 and len(outputs)==48,'Complete actual rows/outputs')
 need(done==[dict(failed=0,cases=48,regions=120,trials=3)]and all(type(v)is int for v in done[0].values()),'Unique typed normal completion')
 index=0;previous={};placements=collections.Counter();by_kind=collections.Counter()
 for c,out in zip(wanted,outputs):
  need(out.get('case_id')==c['case_id']and set(out)=={'case_id','accumulator_u32','W8A8_f32_words'},'Unique full output case/order')
  g=calculations[(c['k'],c['trial_id'])]
  for key in ['accumulator_u32','W8A8_f32_words']:need(type(out[key])is list and len(out[key])==64 and all(ui(v,32)for v in out[key])and out[key]==g[key],'Independent perword numerical mismatch '+key)
  for hart in c['active_harts']:
   row=regions[index];index+=1
   need(row.get('case_id')==c['case_id']and same(row.get('hart'),hart),'Typed physical hart/case order')
   for key in ['hart','trial_id','start_cycle','end_cycle','instret_delta','checksum','expected_checksum','failed_words']:need(ui(row.get(key)),'Unsigned actual field '+key)
   need(same(row['trial_id'],c['trial_id'])and row.get('suite')=='model_operator_validation'and row.get('region')==('producer'if hart==2 else'compiler_kernel'),'Exact ROI trial/role')
   need(row['end_cycle']>row['start_cycle']>=previous.get(hart,0)and row['instret_delta']>0,'Actual typed counter interval/retirement')
   previous[hart]=row['end_cycle'];count=64//c['workers'];gold=g['producer_hash']if hart==2 else fnv(word_bytes(g['accumulator_u32'][hart*count:(hart+1)*count]))
   need(row['checksum']==row['expected_checksum']==gold and row['failed_words']==0 and row.get('pass')is True,'Independent actual ROI checksum/failure')
   placements[hart]+=1;by_kind[c['variant']]+=1
 need(index==120 and dict(placements)=={0:48,2:48,1:24},'All expected physical roles')
 return regions,dict(cases=48,regions=120,int32_words=3072,W8A8_words=3072,trials=3,by_hart=dict(placements),by_variant=dict(by_kind),shipped_and_scalar_twin_all_words_independently_match=True)

def additional_lifecycle(m,current,ids):
 need(m.get('campaign_role')==ROLE and m.get('validation_only')is True and m.get('TinyLlama_protected')is True and m.get('calibration_usable')is False and m.get('hardware_source_association_verified')is False,'Exact protected experiment role')
 need(m.get('console_process_exit_codes')==[0]and all(type(x)is int for x in m['console_process_exit_codes']),'Actual console process exits')
 grant=m['launch_authorization_receipt']['authorization'];issued=datetime.datetime.fromisoformat(grant['issued_at_utc'].replace('Z','+00:00'));expires=datetime.datetime.fromisoformat(grant['expires_at_utc'].replace('Z','+00:00'));need(issued.utcoffset()is not None and expires>issued and hb(grant['instruction'].encode())==grant['instruction_sha256'],'Typed explicit user grant/time/hash')
 for c in m['commands']:
  need(type(c['phase_index'])is int and type(c['returncode'])is int,'Boolean phase/exit values refused');start=datetime.datetime.fromisoformat(c['started_at_utc'].replace('Z','+00:00'));need(issued<=start and start+datetime.timedelta(seconds=c['host_elapsed_seconds'])<=expires,'Authorization current for actual phase')
 for entry in m['safety_inspections']:
  r=entry['report'];need(r['inspection_complete']is True and r['inspection_errors']==[]and r['busy_processes']==[]and r['device_holders']==[]and r['launch_authorization_verified']is True,'Complete idle/holder/authorization inspection')
  need(r['launch_authorization']['authorization_id']==grant['authorization_id']and r['launch_authorization']['boot_id']==grant['boot_id'],'Phase authorization identity')
 need(m['private_directory']==dict(path=m['remote_simulation_dir'],uid=1003,mode=448),'Private owned runtime directory')
 need(m['input_sha256']==current['input_sha256']and m['prepared_file_sha256']==current['prepared_file_sha256'],'Capture/current immutable input declarations')
 need(len(m['input_sha256'])==337 and len(m['prepared_file_sha256'])==299,'Exact source/preparation coverage')
 for name,wanted in m['input_sha256'].items():need(Path(name).is_absolute()and re.fullmatch('[0-9a-f]{64}',wanted)and ids.get('job/prepared-inputs/'+wanted)==wanted,'Named source snapshot missing/different '+name)
 return dict(source_inputs=337,prepared_files=299,complete_idle_phase_checks=len(m['safety_inspections']),actual_console_exit_codes=[0],authorization_current_at_all_phases=True)

def check_prepared(m,ids,runtime):
 private=m['remote_simulation_dir'];need(private=='/scratch/agustin/firesim/'+m['lock_token'],'Owned private token path');line=('    default_simulation_dir: '+private+'\n').encode();need(runtime.count(line)==1,'Unique runtime path');reconstructed=runtime.replace(line,b'    default_simulation_dir: /scratch/firesim\n',1);need(hb(reconstructed)==m['prepared_runtime_sha256']and ids['job/manager/config_runtime.yaml']==m['execution_runtime_sha256'],'Only exact private-directory runtime transform')
 for name,wanted in m['prepared_file_sha256'].items():need((hb(reconstructed)if name=='manager/config_runtime.yaml'else ids.get('job/'+name))==wanted,'Prepared bytes changed '+name)
 return dict(prepared_files=299,only_private_runtime_path_changed=True,prepared_runtime_sha256=m['prepared_runtime_sha256'],execution_runtime_sha256=m['execution_runtime_sha256'])

def audit(job,output):
 job=Path(job).resolve();output=Path(output).resolve();need(not output.exists()and job!=output and job not in output.parents,'Fresh output outside job');output.mkdir(parents=True);helper=Path(__file__).with_name('audit_memory_routes_current_independent.py');need(hf(helper)==HELPER_SHA,'Pinned independent transport helper changed');spec=importlib.util.spec_from_file_location('pinned_memory_transport',helper);transport=importlib.util.module_from_spec(spec);spec.loader.exec_module(transport)
 report=dict(schema='iris.model_operator_second_independent_audit.v1',**{'pass':False},stdlib_only=True,operator_validator_imports=False,independent_i_j_k_uint8_wrap32_math=True,reused_helper_sha256=HELPER_SHA,reused_functions=['read_archive','check_lifecycle','artifact_identities'],hardware_contacted=False,global_v6_data_accessed=False,all_cases_protected_validation_only=True,fitting_allowed=False,full_model_qualified=False,source_image_association_verified=False,timing_accuracy_qualified=False,auditor_sha256=hf(__file__))
 try:
  current=js((job/'run.json').read_bytes());cap=current['capture'];need(cap['status']=='captured'and cap['returncode']==0 and current['cleanup_status']=='passed','Completed capture/cleanup');archive=Path(cap['archive']);need(cap['archive_sha256']==ARCHIVE_SHA and hf(archive)==ARCHIVE_SHA,'Exact actual outer archive')
  data,ids,total=transport.read_archive(archive,cap['captured_run_manifest_sha256']);m=js(data['job/run.json']);lifecycle=transport.check_lifecycle(m,current,ids);managed=additional_lifecycle(m,current,ids)
  prepared=check_prepared(m,ids,data['job/manager/config_runtime.yaml'])
  need(ids['job/manager/workloads/iris-batch/batch.elf']==m['elf_sha256']==ELF_SHA,'Exact approved compiled ELF');need(ids['job/corpus.json']==m['corpus_sha256']==CORPUS_SHA,'Exact protected corpus bytes')
  with tarfile.open(archive,'r:gz')as t:
   extra={name:t.extractfile(name).read()for name in ['job/cases.json','job/launch-authorization.json']}
   for _name,_k,_model,_rev,source_sha in MODELS:
    name='job/prepared-inputs/'+source_sha;extra[name]=t.extractfile(name).read();need(hb(extra[name])==source_sha,'Exact archived source config')
  need(js(extra['job/launch-authorization.json'])==m['launch_authorization_receipt'],'Actual authorization snapshot')
  for name,k,model,revision,source_sha in MODELS:
   raw=extra['job/prepared-inputs/'+source_sha]
   if model is None:
    tree=ast.parse(raw.decode());args=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name=='ModelArgs');dim=next(n.value.value for n in args.body if isinstance(n,ast.AnnAssign)and getattr(n.target,'id',None)=='dim');need(same(dim,k),'Official reference default only')
   else:
    cfg=js(raw);cfg=cfg.get('text_config',cfg);need(same(cfg['hidden_size'],k),'Source K')
    if name=='gemma4-e4b':need(cfg['layer_types'][0]=='sliding_attention'and same(cfg['head_dim'],256)and same(cfg['num_attention_heads'],8),'Gemma sliding-Q width')
    if name=='gpt-oss-20b':need(same(cfg['num_local_experts'],32),'GPT router output width')
  calculations=math_all();corpus=js(data['job/corpus.json']);wanted=check_corpus(corpus,calculations);generic=js(extra['job/cases.json']);need(generic==m['cases']and len(generic)==48,'Archived actual host case table')
  for c,w in zip(generic,wanted):
   need(c['id']==w['case_id']and c['active_harts']==w['active_harts']and all(ui(h)for h in c['active_harts'])and same(c['trial_id'],w['trial_id'])and c['parent_case_id']==w['parent']and c['corpus_split']=='iris-model-operator-protected-validation-v1','Host case canonical controls')
   g=calculations[(w['k'],w['trial_id'])];checks=[0,0,g['producer_hash']]
   for h in range(w['workers']):n=64//w['workers'];checks[h]=fnv(word_bytes(g['accumulator_u32'][h*n:(h+1)*n]))
   need(c['expected_checksums_by_hart']==checks and all(ui(v)for v in c['expected_checksums_by_hart']),'Host independent perhart goldens')
  logs=[name for name in data if name.endswith('/uartlog')];primary=[name for name in logs if name.startswith('job/manager/results-workload/')];need(len(primary)==1 and set(logs)<={primary[0],'job/optional-observability/uartlog'},'Unique managed actual UART');need(all(data[name]==data[primary[0]]for name in logs),'Cleanup UART copies identical')
  rows,numeric=check_uart(data[primary[0]],wanted,calculations);artifacts=transport.artifact_identities(m,ids);need(hf(archive)==ARCHIVE_SHA,'Archive changed during audit');(output/'regions.json').write_text(json.dumps(rows,indent=2)+'\n');(output/'uartlog').write_bytes(data[primary[0]]);(output/'corpus.json').write_bytes(data['job/corpus.json']);(output/'independent-math.json').write_text(json.dumps({str(k)+'.trial'+str(t):v for(k,t),v in calculations.items()},indent=2)+'\n')
  report.update(archive_sha256=ARCHIVE_SHA,all_inventory_bytes_rehashed=True,archived_files=len(ids),archived_bytes_rehashed=total,ELF_sha256=ELF_SHA,corpus_sha256=CORPUS_SHA,numeric=numeric,managed=managed,prepared=prepared,lifecycle=lifecycle,artifacts=artifacts,source_model_identities=[dict(name=n,K=k,model_id=model,revision=rev,source_sha256=source)for n,k,model,rev,source in MODELS],source_runtime_only_private_path_transform_verified=True,exact_gated_Llama2_checkpoint_admitted=False,TinyLlama_validation_only=True,weights_or_quantization_conversion_qualified=False,guest_uart=dict(member=primary[0],sha256=ids[primary[0]]),regions_sha256=hf(output/'regions.json'));report['pass']=True
 except(OSError,ValueError,KeyError,TypeError,IndexError,StopIteration,SyntaxError,struct.error,tarfile.TarError,UnicodeError)as error:report['error']=str(error)
 (output/'report.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('job',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=audit(a.job,a.output);print(json.dumps({k:r.get(k)for k in['pass','archived_files','numeric','error']}));raise SystemExit(0 if r['pass']else 1)
