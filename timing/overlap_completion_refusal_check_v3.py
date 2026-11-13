#!/usr/bin/env python3
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
from iris_model.graph_run_buffered import kill_owned
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);ap.add_argument('--parent-run',required=True);a=ap.parse_args();o=Path(a.output).resolve();o.mkdir(parents=True,exist_ok=False)
 build=json.load(open(ROOT/'build/overlap-completion-console-guest-v1/build.json'));parent=json.load(open(a.parent_run));source=ROOT/'timing/overlap_completion_refusal_guest_v2.c'
 assembly=o/'long.S';assembly.write_text('.text\n.option norvc\n.globl long_same\n.type long_same,@function\nlong_same:\n'+'.4byte 0xf2881077\n'*1024+'ret\n.size long_same,.-long_same\n')
 cases=[]
 for mode,expected in [(0,'IRIS_OPU_ENTRY_MM_TK1_POSITIVE_SHAPE_SCOPE'),(1,'IRIS_OPU_ENTRY_MM_TK1_POSITIVE_SHAPE_SCOPE'),(2,'IRIS_UNDEFINED_STATE'),(3,'IRIS_OPU_ENTRY_ACTIVE_IRQ_CONTEXT_PHASE_UNMODELED')]:
  d=o/str(mode);d.mkdir();elf=d/'guard.elf';cmd=build['argv'][:];idx=cmd.index(str(ROOT/'benchmarks/overlap_completion_v1/guest_console.c'));cmd[idx]=str(source);cmd[idx+1]=str(assembly);cmd[cmd.index('-o')+1]=str(elf);cmd.insert(1,f'-DGUARD_MODE={mode}');r=subprocess.run(cmd,capture_output=True);(d/'build.stdout').write_bytes(r.stdout);(d/'build.stderr').write_bytes(r.stderr)
  if r.returncode:raise RuntimeError(r.stderr.decode())
  argv=[x for x in parent['argv'] if x!='-d'and not x.startswith('--debug-cmd=')and not x.startswith('--iris-timing-trace=')];argv[-1]=str(elf);env=dict(os.environ)
  for k in ('IRIS_EMPIRICAL_FEATURES','IRIS_EMPIRICAL_ASYNC_TRACE'):env.pop(k,None)
  t=time.monotonic();p=None
  with(d/'stdout').open('wb')as so,(d/'stderr').open('wb')as se:
   p=subprocess.Popen(argv,stdout=so,stderr=se,env=env,start_new_session=True)
   try:code=p.wait(timeout=40)
   except subprocess.TimeoutExpired:kill_owned(p);code=p.returncode
  text=(d/'stderr').read_text();ok=code!=0 and expected in text
  # The knownness guard's stable prefix differs from old architectural trap wording.
  if mode==2:ok=code!=0 and 'IRIS_UNDEFINED_STATE' in text and 'unit=VRF' in text
  row=dict(mode=mode,pass_=ok,expected=expected,exit_status=code,host_seconds=time.monotonic()-t,argv=argv,ELF_sha256=sha(elf),stderr=text);row['pass']=row.pop('pass_');cases.append(row)
  if not ok:break
 j={'schema':'iris.opu_entry_refusal_guards.v1','pass':len(cases)==4 and all(x['pass']for x in cases),'cases':cases,'hardware_contacted':False,'input_sha256':{str(p):sha(p)for p in (source,Path(__file__).resolve(),assembly,Path(a.parent_run).resolve())}};(o/'report.json').write_text(json.dumps(j,indent=2)+'\n');print(json.dumps({'pass':j['pass'],'cases':[(x['mode'],x['pass'],x['stderr'][:200])for x in cases]}));return 0 if j['pass']else 1
if __name__=='__main__':raise SystemExit(main())
