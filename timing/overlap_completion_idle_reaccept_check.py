#!/usr/bin/env python3
import argparse,hashlib,json,os,struct,subprocess,time
from pathlib import Path
from iris_model.graph_run_buffered import kill_owned
from timing.memory_routes_current_audit_v2 import Elf
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);ap.add_argument('--parent-run',required=True);a=ap.parse_args();o=Path(a.output).resolve();o.mkdir(parents=True,exist_ok=False);src=ROOT/'timing/overlap_completion_idle_reaccept_guest.c';assembly=ROOT/'build/overlap-completion-fullcell-guards-guest-v1/kernels.S'
 j=json.load(open(ROOT/'build/overlap-completion-console-guest-v1/build.json'));cmd=j['argv'][:];idx=cmd.index(str(ROOT/'benchmarks/overlap_completion_v1/guest_console.c'));cmd[idx]=str(src);cmd[idx+1]=str(assembly);elf=o/'guest.elf';cmd[cmd.index('-o')+1]=str(elf);r=subprocess.run(cmd,capture_output=True);(o/'build.stdout').write_bytes(r.stdout);(o/'build.stderr').write_bytes(r.stderr);assert not r.returncode
 e=Elf(elf);done=e.symbol('idle_reaccept_done')[0];base,size=e.symbol('idle_reaccept_words');commands=o/'commands';commands.write_text('\n'.join(['rs 0',f'while mem {done:x} ffffffffffffffff',f'mem {done:x}']+[f'mem {v:x}'for v in range(base,base+size,8)]+['rs'])+'\n');p=json.load(open(a.parent_run));argv=p['argv'][:];argv[-1]=str(elf);argv=[('--debug-cmd='+str(commands)if x.startswith('--debug-cmd=')else'--iris-timing-trace='+str(o/'summary.json')if x.startswith('--iris-timing-trace=')else x)for x in argv];env=dict(os.environ);env.pop('IRIS_EMPIRICAL_FEATURES',None);env['IRIS_EMPIRICAL_ASYNC_TRACE']=str(o/'async.jsonl');t=time.monotonic()
 with(o/'stdout').open('wb')as so,(o/'stderr').open('wb')as se:
  proc=subprocess.Popen(argv,stdout=so,stderr=se,env=env,start_new_session=True)
  try:code=proc.wait(timeout=120)
  except subprocess.TimeoutExpired:kill_owned(proc);code=proc.returncode
 ok=code==0 and(o/'stdout').read_text()=='IDLE_REACCEPT_PASS\n';result={'schema':'iris.opu_entry_idle_reaccept.v1','pass':False,'argv':argv,'exit_status':code,'host_seconds':time.monotonic()-t,'hardware_contacted':False,'normal_guest_exit':ok,'input_sha256':{str(p.resolve()):sha(p)for p in(src,assembly,elf,commands,Path(__file__),Path(a.parent_run))}}
 if ok:
  ls=[x for x in(o/'stderr').read_text().splitlines()if x!=':'];vs=[int(x,16)for x in ls];words=struct.unpack('<4096I',b''.join(x.to_bytes(8,'little')for x in vs[1:]));assert vs[0]==0 and list(words)==[0]*3072+[1]*1024
  tr=[json.loads(l)for l in(o/'async.jsonl').read_text().splitlines()];bad={e.symbol(f'wrongpath_MM_{k}')[0]for k in range(16)};acc=[x for x in tr if x['event']=='opu_front_accept'and x['pc']in bad];canc={(x['hart'],x['instruction'])for x in tr if x['event']=='opu_front_cancel'};assert acc and all((x['hart'],x['instruction'])in canc for x in acc);assert not any(x['event']=='opu_microissue_reserved'and x['pc']in bad for x in tr)
  result.update(pass_=True,numeric_words=4096,wrongpath_front_accepts=len(acc),new_after_idle_microissues=sum(x['event']=='opu_microissue_reserved'for x in tr));result['pass']=result.pop('pass_')
 (o/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result.get(k)for k in('pass','normal_guest_exit','numeric_words','wrongpath_front_accepts','new_after_idle_microissues','host_seconds')}));return 0 if result['pass']else 1
if __name__=='__main__':raise SystemExit(main())
