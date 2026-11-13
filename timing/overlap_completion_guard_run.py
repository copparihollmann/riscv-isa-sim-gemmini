#!/usr/bin/env python3
import argparse,hashlib,json,os,signal,struct,subprocess,time
from pathlib import Path
from iris_model.graph_run_buffered import kill_owned
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--build',required=True);ap.add_argument('--output',required=True);ap.add_argument('--parent-run',required=True);ap.add_argument('--functional',action='store_true');ap.add_argument('--timeout',type=float,default=120);a=ap.parse_args();o=Path(a.output).resolve();o.mkdir(parents=True,exist_ok=False);b=Path(a.build).resolve();j=json.load(open(b/'build.json'));parent=json.load(open(a.parent_run));argv=parent['argv'][:];elf=b/'guard.elf';assert sha(elf)==j['ELF_sha256'];argv[-1]=str(elf)
 obj=j['objects'];cmds=['rs 0',f'while mem {obj["opu_guard_done"]["address"]:x} ffffffffffffffff']
 for name in ('opu_guard_done','opu_guard_errors','opu_guard_cases','opu_guard_words','opu_guard_wrong_words'):
  p=obj[name];cmds +=[f'mem {x:x}'for x in range(p['address'],p['address']+p['size'],8)]
 cmds+=['rs'];commands=o/'commands';commands.write_text('\n'.join(cmds)+'\n');argv=[('--debug-cmd='+str(commands)if x.startswith('--debug-cmd=')else'--iris-timing-trace='+str(o/'summary.json')if x.startswith('--iris-timing-trace=')else x)for x in argv]
 if a.functional:argv=[x for x in argv if not x.startswith('--iris-timing-fixture=')and not x.startswith('--iris-timing-trace=')]
 env=dict(os.environ);env.pop('IRIS_EMPIRICAL_FEATURES',None);env.pop('IRIS_EMPIRICAL_ASYNC_TRACE',None)
 if not a.functional:env['IRIS_EMPIRICAL_ASYNC_TRACE']=str(o/'async.jsonl')
 r={'schema':'iris.opu_entry_fullcell_guards.v1','pass':False,'status':'running','argv':argv,'hardware_contacted':False,'functional_only':a.functional,'input_sha256':{str(p):sha(p)for p in(Path(__file__).resolve(),b/'build.json',elf,Path(a.parent_run).resolve(),commands)}}
 for x in argv:
  p=Path(x.split('=',1)[1])if x.startswith(('--extlib=','--iris-timing-fixture='))else None
  if p and p.is_file():r['input_sha256'][str(p)]=sha(p)
 p=None;t=time.monotonic()
 def save():(o/'report.json').write_text(json.dumps(r,indent=2)+'\n')
 save()
 try:
  with(o/'stdout').open('wb')as so,(o/'stderr').open('wb')as se:
   p=subprocess.Popen(argv,stdout=so,stderr=se,env=env,start_new_session=True);r['owned_pid']=p.pid;save()
   try:code=p.wait(timeout=a.timeout)
   except subprocess.TimeoutExpired:kill_owned(p);raise RuntimeError('owned timeout; partial logs preserved')
  r['exit_status']=code
  if code:raise RuntimeError('native failed')
  if(o/'stdout').read_text()!='OPU_GUARD_PASS\n':raise RuntimeError('normal HTIF/numeric completion banner required')
  lines=(o/'stderr').read_text().splitlines();raw=[l for l in lines if l!=':'];values=[int(l,16)for l in raw];assert all(l.startswith('0x')and len(l)==18 for l in raw)
  if values[:3]!=[0,0,24]:raise RuntimeError('done/errors/cases mismatch')
  words=list(struct.unpack('<'+str(2*(len(values)-3))+'I',b''.join(v.to_bytes(8,'little')for v in values[3:])))
  expected=[]
  for h in range(2):
   for fp in range(2):
    for size in(8,16,32):
     for pattern in range(2):
      for tile in range(4):
       for row in range(32):
        for col in range(32):
         initial=512+64*tile+row+col;product=(2**(row%4)*2**(col%3))if fp else(1+row%4)*(1+col%3);v=initial+(64*product if row<size and col<size else 0)
         expected.append(struct.unpack('<I',struct.pack('<f',float(v)))[0]if fp else 0x70000000+v)
  for h in range(2):
   for tile in range(4):
    for row in range(32):
     for col in range(32):expected.append(0x70000000+512+64*tile+row+col)
  if words!=expected:raise RuntimeError('independent all-MRF word mismatch')
  r.update(numeric_words=len(words),normal_HTIF_guest_exit=True,source_queue_capacity_test=False)
  if not a.functional:
   trace=[json.loads(l)for l in(o/'async.jsonl').read_text().splitlines()];bad=set(j['wrongpath_MM_PCs'].values());cancel=[x for x in trace if x['event']=='opu_front_cancel'];accepted=[x for x in trace if x['event']=='opu_front_accept'and x['pc']in bad];writes=[x for x in trace if x['event']=='opu_microissue_reserved'and x['pc']in bad]
   if not accepted or len(cancel)<len(accepted)or writes:raise RuntimeError('wrongpath MM front/cancel/no-source-write proof missing')
   queues=[x for x in trace if x['event']=='opu_queue_edge'];r.update(wrongpath_front_accepts=len(accepted),wrongpath_cancels=len(cancel),wrongpath_source_microissues=len(writes),backend_queue_peak=max(x['vdq_before']+x['iq_before']+x['seq_before']for x in queues),VDQ_peak=max(x['vdq_before']for x in queues),IQ_peak=max(x['iq_before']for x in queues),VDQ_full_edges=sum(not x['input_ready']for x in queues))
   if r['backend_queue_peak']>8 or r['VDQ_peak']>4 or r['IQ_peak']>3:raise RuntimeError('backend source capacity exceeded')
  r.update(pass_=True,status='normal_guest_and_independent_fullword_guards_passed')
 except Exception as e:r.update(error=str(e),status='failed')
 finally:
  if p and p.poll()is None:kill_owned(p)
  r['host_seconds']=time.monotonic()-t;r['pass']=r.pop('pass_',False);save()
 print(json.dumps({k:r.get(k)for k in('pass','status','error','numeric_words','wrongpath_front_accepts','wrongpath_cancels','backend_queue_peak','VDQ_full_edges','host_seconds')}))
 return 0 if r['pass']else 1
if __name__=='__main__':raise SystemExit(main())
