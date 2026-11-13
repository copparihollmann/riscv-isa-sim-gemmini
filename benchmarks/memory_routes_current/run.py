#!/usr/bin/env python3
"""Normal-exit three-hart functional gate for the new repeated memory ELF."""
import argparse,json,os,subprocess,time
from pathlib import Path
from build import ROOT,sha
from validate import validate,check_elf
def run(build,out,seed,binary,uart):
 out.mkdir(parents=True,exist_ok=False);b=json.loads((build/'build.json').read_text());corpus=json.loads((build/'corpus.json').read_text());elf=build/'memory-routes.elf';check_elf(elf,corpus,json.loads((build/'readback-layout.json').read_text()))
 for p,h in b['input_sha256'].items():
  if sha(p)!=h or sha(build/'inputs'/h)!=h:raise ValueError('Changed build input '+p)
 dma='rv64gcv_zfh_zvfh_zvl256b_zvbb';compute='rv64gcv_zfh_zvfh_zba_zbb_zbs_zvbb_zvl256b_zvfofp8min_zvfbfmin_zvfbfa_zvt32t_zvti8i32mm_zvtofp8fmm'
 argv=[str(binary),'--iris-vme','--isa='+dma,'--hart-isa=0:'+compute,'--hart-isa=1:'+compute,'--hart-isa=2:'+dma,'-p3','-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000','--extlib='+str(uart),'--device=sifive_uart,0x10020000','--iris-bootrom='+str(ROOT/'board/evidence/bootrom.rv64.img'),'--dtb='+str(ROOT/'board/build/iris.dtb'),'--iris-schedule-seed='+str(seed),str(elf)]
 files=[Path(__file__).resolve(),Path(__file__).with_name('validate.py'),build/'build.json',build/'corpus.json',elf,binary,uart,ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb'];inputs={str(p):sha(p)for p in files};env=dict(os.environ);env.pop('IRIS_FATAL_PCS',None);start=time.monotonic();r=subprocess.run(argv,capture_output=True,env=env,timeout=180);elapsed=time.monotonic()-start;(out/'run.stdout').write_bytes(r.stdout);(out/'run.stderr').write_bytes(r.stderr)
 if r.returncode:raise ValueError('Functional guest failed '+r.stderr.decode())
 proof=validate(r.stdout.decode(),corpus)
 if any(sha(p)!=h for p,h in inputs.items()):raise ValueError('Execution input changed')
 report={'schema':'iris.memory_routes_current_functional.v1','pass':True,'seed':seed,'exit_status':r.returncode,'normal_guest_exit_verified':True,'argv':argv,'host_seconds':elapsed,'elf_sha256':sha(elf),'stdout_sha256':sha(out/'run.stdout'),'stderr_sha256':sha(out/'run.stderr'),'input_sha256':inputs,'proof':proof,'hardware_contacted':False,'timing_certified':False};(out/'run.json').write_text(json.dumps(report,indent=2)+'\n');return report
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,required=True);p.add_argument('--binary',type=Path,default=ROOT/'build/combined-frozen-35901887/spike');p.add_argument('--uart',type=Path,default=ROOT/'build/combined-frozen-35901887/libsifive_uart.so');a=p.parse_args();r=run(a.build.resolve(),a.output.resolve(),a.seed,a.binary.resolve(),a.uart.resolve());print(json.dumps({'pass':r['pass'],'seed':r['seed'],'host_seconds':r['host_seconds'],'regions':r['proof']['regions']}))
