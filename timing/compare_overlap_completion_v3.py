#!/usr/bin/env python3
"""All168 overlap comparisons from freshly archive-derived reference and raw native bytes.

Root invokes the actual hardware comparison. Component tests use synthetic labels.
There is no fitting and no hardware operation.
"""
import argparse,collections,hashlib,json,re,struct,subprocess,sys,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R));sys.path.insert(0,str(R/'timing'))
from compare_pow2_native import sha,load,need,inventory,metrics,grouped
from iris_model.guest_regions import Instructions
ELF_SHA='deec529e973d47413de419018d328582564a18b979c7e6b93f6c323507b27940'
FIELDS=('start','issue_end','fence_end','drain_end');HW_FIELDS=('start_cycle','issue_end_cycle','fence_end_cycle','end_cycle')
def integer(v):
 need(type(v)is int and 0<=v<1<<64,'Typed uint64 architectural field');return v

def golden(c):
 if c['hart']==2:return [c['count']+1]*c['edge']
 out=[]
 for j in range(128):
  tile,col=divmod(j,32);n=(c['count']//4 if c['rotate']else c['count']if tile==0 else 0)if col<c['edge']else 0
  out.append(struct.unpack('<I',struct.pack('<f',float(n)))[0]if c['fp8']else n)
 return out

def raw_decode(text,corpus):
 lines=text.splitlines();need(all(x==':'or re.fullmatch('0x[0-9a-f]{16}',x)for x in lines),'Exact debugger transcript, no fatal/trap noise')
 words=[int(x,16)for x in lines if x!=':'];cases=corpus['cases'];need(len(cases)==168 and [x['id']for x in cases]==list(range(168)),'Canonical168cases')
 need(len(words)==1+168*14+168*64+3 and words[0]==0 and words[-3:]==[0,168,0],'Complete stable finished sentinel/count/errors')
 rows=[];checked=0;prior={}
 for i,c in enumerate(cases):
  v=words[1+i*14:1+(i+1)*14];need(v[:6]==[c[k]for k in('hart','fp8','edge','count','rotate','trial')],'Compiled metadata/actual index order')
  need(0<=v[6]<v[7]<v[8]<v[9] and v[10]>0 and v[12:]==[0,0],'Strict positive four-boundary observation and no error')
  need(v[6]>=prior.get(c['hart'],0),'Forward perhart regions');prior[c['hart']]=v[9]
  raw=b''.join(x.to_bytes(8,'little')for x in words[1+168*14+i*64:1+168*14+(i+1)*64]);want=golden(c)
  actual=list(struct.unpack('<128I',raw))if c['hart']<2 else list(raw[:c['edge']]);need(actual==want and v[11]==sum(want),'Independent every-word/active-byte golden')
  # The console does not qualify h2padding. Native storage-tail bytes are not
  # promoted to hardware numerical coverage by this comparator.
  checked+=len(want);row=dict(c);row.update(dict(zip(('hart','fp8','edge','count','rotate','trial',*FIELDS,'instret','checksum','failed','expected'),v)));rows.append(row)
 need(checked==19872,'Exact qualified numerical elements')
 return rows,checked

def join_prefix(path,rows,elf):
 features=[json.loads(s)for s in path.read_text().splitlines()];need(len(features)==672,'Exact672 actualCSR events')
 insns=Instructions(elf,R/'board/evidence/bootrom.rv64.img');index={};last={};used=set()
 for f in features:
  for k in ('hart','sequence','pc','raw','csr','value','read_cycle'):integer(f[k])
  h=f['hart'];need(h<3 and f['sequence']>last.get(h,-1),'Monotonic perhart actualCSR sequence');last[h]=f['sequence']
  raw=insns.read(f['pc']);need(f['raw']==raw and raw&127==0x73 and raw>>20==f['csr']and f['csr']in(0xb00,0xc00)and (raw>>15)&31==0 and (raw>>12)&7 in(2,3,6,7)and f.get('result_discarded')is False,'Actual returning mcycle instruction in exactELF')
  key=h,f['value'];need(key not in index,'Unique observed CSR value');index[key]=f
 for row in rows:
  endpoints=[]
  for field in FIELDS:
   key=row['hart'],row[field];need(key in index and key not in used,'Unique owned actual endpoint');used.add(key);endpoints.append(index[key])
  need(all(endpoints[i]['sequence']<endpoints[i+1]['sequence']and endpoints[i]['read_cycle']<endpoints[i+1]['read_cycle']for i in range(3)),'Forward physical read phases')
  row['actual_CSR_endpoints']=endpoints
 need(len(used)==672,'No omitted/reused CSR boundary')
 return dict(actual_CSR_ELF_joins=672,fullword_or_activebyte_numerical_elements=19872)

def native(run,corpus,elf):
 rr=load(run/'run.json');need(rr['schema']=='iris.overlap_completion_execution.v1'and rr['pass']is True and rr['exit_status']==0 and rr['timed_out']is False and rr['functional_mode']is False and rr['cases']==168 and rr['actual_cycle_endpoints']==672,'Complete actual timed readback run')
 controlled=rr['status']=='controlled_post_ROI_readback_passed';normal=rr['status']=='normal_guest_exit_and_independent_readback_passed'
 need(controlled or normal,'Explicit completion scope');need(rr['forced_debug_quit']is controlled and rr['normal_HTIF_exit']is normal,'Debugger/normal completion distinction')
 inventory(rr['input_sha256'])
 for name,h in rr['output_sha256'].items():need(Path(name).name==name and sha(run/name)==h,'Bound raw native output')
 need(rr['ELF_sha256']==sha(elf)==ELF_SHA and rr['input_sha256'].get(rr['argv'][-1])==ELF_SHA,'Same exact compiled overlapELF')
 rows,checked=raw_decode((run/'stderr').read_text(),corpus);proof=join_prefix(run/'features.jsonl',rows,elf);saved=load(run/'regions.json');need(len(saved)==168,'Full cached observation')
 for row,old in zip(rows,saved):
  need(all(old.get(k)==v for k,v in row.items()if k!='actual_CSR_endpoints'),'Raw readback must agree with cached region metadata/counters')
  expected=[{k:x[k]for k in('sequence','pc','raw','csr','value','read_cycle','async_compute_pending','async_pending_count')}for x in row['actual_CSR_endpoints']]
  need(old['captured_CSR_endpoints']==expected,'Recomputed actualCSR ownership agrees with saved receipt')
 return rows,dict(proof,normal_HTIF_exit=normal,intentional_postmeasurement_quit=controlled,native_binary_sha256=rr['native_binary_sha256'],native_host_seconds=rr['host_seconds']),rr

def verify_reference(job,hardware):
 hr=load(hardware/'report.json');need(hr['status']=='passed'and hr['archive_verified']is True and hr['regions']==168 and hr['boundary_values']==672 and hr['total_instret_deltas']==168,'Complete strict overlap hardware analysis')
 inventory(hr['input_sha256']);need(sha(job/'run.json')==hr['current_manifest_sha256'],'Exact analysis-bound hardwarejob')
 current=load(job/'run.json');need(current['capture']['archive_sha256']==hr['archive_sha256'],'Exact currentlycaptured archive')
 for name,h in hr['output_sha256'].items():need(Path(name).name==name and sha(hardware/name)==h,'Original derived hardware output digest')
 with tempfile.TemporaryDirectory(prefix='overlap-reference-rederive-')as tmp:
  fresh=Path(tmp)/'reference';argv=[sys.executable,str(R/'firesim/analyze_overlap_completion_v1.py'),str(job),'--output',str(fresh)];cp=subprocess.run(argv,capture_output=True,timeout=180);need(cp.returncode==0,'Strict actualarchive rederivation failed: '+cp.stderr.decode()[-500:]);new=load(fresh/'report.json');need(new['status']=='passed'and new['archive_verified']is True and new['archive_sha256']==hr['archive_sha256'],'Same strictlyverified archive')
  for name in ['corpus.json','regions.jsonl','observed.elf','uartlog']:need((fresh/name).read_bytes()==(hardware/name).read_bytes(),'Exact independent derived output: '+name)
 return load(hardware/'corpus.json'),[json.loads(s)for s in(hardware/'regions.jsonl').read_text().splitlines()],dict(archive_rederivation_verified=True,archive_sha256=hr['archive_sha256'],analyzer_command=argv,derived_sha256={n:sha(hardware/n)for n in['corpus.json','regions.jsonl','observed.elf','uartlog']})

def compare_rows(sw,hw,corpus):
 need(len(sw)==len(hw)==len(corpus['cases'])==168,'Every actual case/role retained')
 rows=[]
 for i,(s,h,c)in enumerate(zip(sw,hw,corpus['cases'])):
  need(c['id']==i and h['case_id']=='overlap.v1.case.'+str(i)and h['hart']==s['hart']==c['hart']and type(h['hart'])is int,'Exact canonical ordered case/hart join')
  for field in ['fp8','edge','count','rotate']:need(integer(h[field])==c[field]==s[field],'Exact case metadata')
  need(integer(h['trial'])==c['trial']==s['trial'],'Every declared trial')
  need(h['internal_split']==('reserved_validation'if c['edge']==(64 if c['hart']==2 else 16)else'train'),'Frozen whole-family split')
  need(h['independent_checksum_validated']is True and integer(h['failed_elements'])==0 and integer(h['checksum'])==s['checksum']==sum(golden(c)),'Typed independent actualreference golden')
  need(h['instret_scope']=='total_only'and h['region']=='total','Actualreference total-only retirement scope')
  a=[integer(h[k])for k in HW_FIELDS];b=[integer(s[k])for k in FIELDS];need(all(a[j]<a[j+1]and b[j]<b[j+1]for j in range(3)),'Strict forward fourphase counters');ir=integer(h['instret_delta']);need(ir>0 and integer(s['instret'])>0,'Positive totalinstructionretirement')
  row=dict(case_id=h['case_id'],semantic_case_id=c['case_id'],hart=c['hart'],fp8=c['fp8'],edge=c['edge'],count=c['count'],rotate=c['rotate'],trial=c['trial'],internal_split=h['internal_split'],native_instret=s['instret'],hardware_instret=ir,instret_equal=s['instret']==ir,instret_scope='total_only')
  for label,left,right in [('issue',0,1),('fence',1,2),('dependent_readout',2,3),('total',0,3)]:
   sc=b[right]-b[left];hc=a[right]-a[left];row['native_'+label+'_cycles']=sc;row['hardware_'+label+'_cycles']=hc;row[label+'_signed_error_percent']=100*(sc-hc)/hc
  rows.append(row)
 return rows

def summarize(rows):
 result={}
 for window in ['issue','fence','dependent_readout','total']:
  projected=[dict(x,signed_error_percent=x[window+'_signed_error_percent'])for x in rows];result[window]=dict(overall=metrics(projected),by_partition=grouped(projected,['internal_split']),by_hart=grouped(projected,['hart']),by_mechanism=grouped(projected,['hart','fp8','edge','count','rotate']))
 return result

def verify_prediction(prediction,run,rows,rr,scope):
 pred=load(prediction);inventory(pred['input_sha256'])
 need(pred['schema']=='iris.overlap_completion_frozen_prediction.v1'and pred['pass']is True and pred['ELF_sha256']==ELF_SHA,'Frozen prediction identity')
 for key,want in [('regions_checked',168),('numeric_elements_checked',19872),('actual_CSR_ELF_joins',672)]:need(type(pred[key])is int and pred[key]==want,'Typed frozen prediction geometry')
 need(pred['native_binary_sha256']==rr['native_binary_sha256'],'Same native prediction identity')
 uart=[x.split('=',1)[1]for x in rr['argv']if x.startswith('--extlib=')];need(len(uart)==1 and pred['uart_library_sha256']==sha(uart[0]),'Same actual paired UART')
 need(pred['input_sha256'].get(str(run/'run.json'))==sha(run/'run.json'),'Frozen prediction binds this exact actualrun')
 need(pred['normal_HTIF_guest_exit']is scope['normal_HTIF_exit'],'Identical normal/debugger completion scope')
 need(len(pred['regions'])==168 and all(all(pr.get(k)==row[k]for k in FIELDS)and pr['instret_delta']==row['instret']for pr,row in zip(pred['regions'],rows)),'Exact frozenprediction counters/totalIR')
 return True

def main(a):
 run,hw,job,out=[x.resolve()for x in(a.run,a.hardware,a.job,a.output)];need(not out.exists(),'Fresh comparison output')
 corpus,measured,reference=verify_reference(job,hw);rows,scope,rr=native(run,corpus,hw/'observed.elf');compared=compare_rows(rows,measured,corpus);summary=summarize(compared)
 if a.prediction:
  verify_prediction(a.prediction.resolve(),run,rows,rr,scope)
 out.mkdir(parents=True);(out/'regions.jsonl').write_text(''.join(json.dumps(x,sort_keys=True)+'\n'for x in compared));(out/'groups.json').write_text(json.dumps(summary,indent=2)+'\n')
 inputs=[Path(__file__).resolve(),run/'run.json',run/'stderr',run/'features.jsonl',run/'regions.json',hw/'report.json',hw/'corpus.json',hw/'regions.jsonl',hw/'observed.elf',job/'run.json',R/'firesim/analyze_overlap_completion_v1.py',R/'timing/compare_pow2_native.py']+([a.prediction.resolve()]if a.prediction else[])
 report=dict(schema='iris.overlap_completion_verified_comparison.v3',pass_=True,regions=168,actual_CSR_ELF_endpoints=672,qualified_numerical_elements=19872,total_instret_deltas=168,subwindow_instret_available=False,all_rows_retained=True,ELF_sha256=ELF_SHA,native_completion_scope=scope,verified_reference=reference,statistics=summary,cycle_sums_are_not_end_to_end=True,CLINT_available=False,global_hart_alignment_claimed=False,not_full_MRF_coverage=True,parameters_refit=False,reserved_reference_owner='root only; not shared with fitters',source_image_association_verified=False,timing_2pct_certified=False,hardware_contacted=False,input_sha256={str(p):sha(p)for p in inputs},output_sha256={p.name:sha(p)for p in out.iterdir()});report['pass']=report.pop('pass_');(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(pass_=True,regions=168,report_sha256=sha(out/'report.json'))))
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__)
 for key in ['run','hardware','job','output']:p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--prediction',type=Path);main(p.parse_args())
