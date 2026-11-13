#!/usr/bin/env python3
"""Run exact buffered overlap ELF, typed readback, then normal HTIF completion."""
import argparse,hashlib,json,os,re,signal,struct,subprocess,time
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from iris_model.empirical_run import descriptor,checked_inputs
from iris_model.graph_run_buffered import kill_owned
from timing.memory_routes_current_audit_v2 import Elf

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def load(p):return json.loads(Path(p).read_text())
def decode(raw,corpus,layout):
 lines=raw.splitlines()
 if any(l!=':'and not re.fullmatch(r'0x[0-9a-f]{16}',l)for l in lines):raise ValueError('Unexpected debugger/error output')
 words=[int(l,16)for l in lines if l!=':'];cases=corpus['cases'];n=len(cases)
 if len(words)!=1+n*14+n*64+3 or words[0]!=0 or words[-3:]!=[0,n,0]:raise ValueError('Incomplete or failed stable readback')
 records=[];checked=0
 for i,c in enumerate(cases):
  v=words[1+14*i:1+14*(i+1)]
  if v[:6]!=[c[k]for k in('hart','fp8','edge','count','rotate','trial')]:raise ValueError('Actual case metadata differs from frozen table')
  if not 0<=v[6]<v[7]<v[8]<v[9]or not v[10]or v[12]or v[13]:raise ValueError('Invalid ordered CSR boundary or guest error')
  rawdata=b''.join(x.to_bytes(8,'little')for x in words[1+n*14+64*i:1+n*14+64*(i+1)])
  if c['hart']<2:
   data=list(struct.unpack('<128I',rawdata));expected=[]
   for tile in range(4):
    count=c['count']//4 if c['rotate']else 0 if tile else c['count']
    scalar=struct.unpack('<I',struct.pack('<f',float(count)))[0]if c['fp8']else count
    expected.extend([scalar]*c['edge']+[0]*(32-c['edge']))
   if data!=expected:raise ValueError('Independent128-word matrix row golden mismatch')
   checksum=sum(data);checked+=128
  else:
   if rawdata[:c['edge']]!=bytes([c['count']+1])*c['edge']or any(rawdata[c['edge']:]):raise ValueError('Independent vector byte/padding mismatch')
   checksum=sum(rawdata[:c['edge']]);checked+=c['edge']
  if v[11]!=checksum:raise ValueError('Stored checksum differs from per-element golden')
  record=dict(c);record.update(dict(zip(layout['row_fields'],v)));record['issue_cycles']=v[7]-v[6];record['fence_drain_cycles']=v[8]-v[7];record['dependent_readout_cycles']=v[9]-v[8];record['total_cycles']=v[9]-v[6];record['pass']=True;records.append(record)
 return records,checked

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--model',type=Path,default=ROOT/'build/empirical-hybrid7bd5-reference-guard-v4/manifest.json');p.add_argument('--controlled-stop',action='store_true');p.add_argument('--functional',action='store_true');p.add_argument('--seed',type=int,default=0);p.add_argument('--timeout',type=float,default=180);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 def interrupted(*unused):raise KeyboardInterrupt('owned local run interrupted')
 signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGHUP,interrupted)
 started=time.monotonic();proc=None;report={'schema':'iris.overlap_completion_execution.v1','pass':False,'status':'preflight','hardware_contacted':False,'global_heldout_timings_consumed':False,'timing_reference_available':False}
 def save():(out/'run.json').write_text(json.dumps(report,indent=2)+'\n')
 save()
 try:
  build=a.build.resolve();elf=build/'overlap.elf';layout=load(build/'readback-layout.json');corpus=load(build/'corpus.json');model=descriptor(a.model.resolve());actual=Elf(elf)
  if layout['elf_sha256']!=sha(elf)or len(corpus['cases'])!=layout['cases']:raise ValueError('Exact case/layout/ELF required')
  for name,obj in layout['objects'].items():
   if actual.symbol(name)!=(obj['address'],obj['size']):raise ValueError('ELF symbol bounds mismatch')
  addr=lambda n:layout['objects'][n]['address']
  if actual.read(addr('overlap_done'),8)!=b'\xff'*8:raise ValueError('Known file-backed sentinel required')
  n=layout['cases'];commands=['rs 0',f'while mem {addr("overlap_done"):x} ffffffffffffffff',f'mem {addr("overlap_done"):x}']
  commands += [f'mem {addr("overlap_records")+128*i+8*j:x}'for i in range(n)for j in range(14)]
  commands += [f'mem {x:x}'for x in range(addr('overlap_words'),addr('overlap_words')+n*512,8)]
  commands += [f'mem {addr(k):x}'for k in('overlap_done','overlap_finished','overlap_failed')]+(['q']if a.controlled_stop else['rs'])
  cmd=out/'readback.commands';cmd.write_text('\n'.join(commands)+'\n');launch=list(model['launch_args'])
  if a.functional:launch=[x for x in launch if not x.startswith('--iris-timing-fixture=')]
  else:launch+=['--iris-timing-trace='+str(out/'native-summary.json')]
  argv=[model['binary'],'-d','--debug-cmd='+str(cmd),'--isa='+model['per_hart_isa']['2'],'-p3','-m'+','.join(f'{b:#x}:{s:#x}'for b,s in model['memory_regions']),*launch,*['--hart-isa='+str(h)+':'+model['per_hart_isa'][str(h)]for h in range(3)],'--iris-schedule-seed='+str(a.seed),str(elf)]
  inputs=dict(model['execution_input_sha256']);inputs.update({str(x.resolve()):sha(x)for x in(Path(__file__),elf,build/'build.json',build/'corpus.json',build/'readback-layout.json',cmd)})
  checked_inputs(inputs);env=dict(os.environ)
  for k in('IRIS_EMPIRICAL_FEATURES','IRIS_EMPIRICAL_ASYNC_TRACE'):env.pop(k,None)
  if not a.functional:env.update(IRIS_EMPIRICAL_FEATURES=str(out/'features.jsonl'),IRIS_EMPIRICAL_ASYNC_TRACE=str(out/'async.jsonl'))
  report.update(status='running',argv=argv,input_sha256=inputs,ELF_sha256=sha(elf),native_binary_sha256=model['native_binary_sha256'],fixture_scope='removed explicitly for functional numeric mode'if a.functional else'manifest-selected fitted timing unchanged',seed=a.seed,functional_mode=a.functional);save()
  with(out/'stdout').open('wb')as stdout,(out/'stderr').open('wb')as stderr:
   proc=subprocess.Popen(argv,stdout=stdout,stderr=stderr,env=env,start_new_session=True);report['owned_child_pid']=proc.pid;save()
   try:code=proc.wait(timeout=a.timeout);timed=False
   except(subprocess.TimeoutExpired,KeyboardInterrupt):kill_owned(proc);code=proc.returncode;timed=True
  report.update(exit_status=code,timed_out=timed)
  if code or timed:raise ValueError('Normal guest exit required; preserve partial logs')
  if not a.controlled_stop:
   from benchmarks.overlap_completion_v1.validate_console import validate
   validate((out/'stdout').read_text(),corpus)
  records,count=decode((out/'stderr').read_text(),corpus,layout)
  if not a.functional:
   prefixes=[json.loads(l)for l in(out/'features.jsonl').read_text().splitlines()]
   if len(prefixes)!=n*4:raise ValueError('Expected four actual cycle boundaries per case')
   for r in records:
    endpoints=[]
    for name in('start','issue_end','fence_end','drain_end'):
     ps=[q for q in prefixes if q['hart']==r['hart']and q['value']==r[name]and q.get('result_discarded')is False]
     if len(ps)!=1:raise ValueError('Ambiguous/missing actual CSR result join')
     q=ps[0];raw=actual.read(q['pc'],4)
     if int.from_bytes(raw,'little')!=q['raw']or(q['raw']>>20)!=q['csr']or q['csr']not in(0xb00,0xc00):raise ValueError('Actual CSR instruction differs from ELF')
     endpoints.append({k:q[k]for k in('sequence','pc','raw','csr','value','read_cycle','async_compute_pending','async_pending_count')})
    r['captured_CSR_endpoints']=endpoints
  (out/'regions.json').write_text(json.dumps(records,indent=2)+'\n');checked_inputs(inputs)
  report.update(**{'pass':True},status='controlled_post_ROI_readback_passed'if a.controlled_stop else'normal_guest_exit_and_independent_readback_passed',cases=n,numeric_elements_checked=count,normal_HTIF_exit=not a.controlled_stop,forced_debug_quit=a.controlled_stop,actual_cycle_endpoints=0 if a.functional else n*4)
 except(Exception,KeyboardInterrupt)as e:report.update(status='failed_or_interrupted',error=str(e))
 finally:
  if proc is not None and proc.returncode is None:kill_owned(proc)
  report['owned_process_cleanup_complete']=proc is None or proc.returncode is not None;report['host_seconds']=time.monotonic()-started;report['output_sha256']={p.name:sha(p)for p in out.iterdir()if p.is_file()and p.name!='run.json'};save()
 print(json.dumps({k:report.get(k)for k in('pass','status','cases','numeric_elements_checked','host_seconds','error')}))
 if not report['pass']:raise SystemExit(1)
if __name__=='__main__':main()
