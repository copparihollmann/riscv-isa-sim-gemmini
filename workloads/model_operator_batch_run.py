#!/usr/bin/env python3
"""Run the new batch on the immutable359 functional pair, preserving failures."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
from model_operator_batch_validate import validate
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,required=True);p.add_argument('--negative',action='store_true');p.add_argument('--timeout',type=int,default=300);a=p.parse_args();build=a.build.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);r=json.loads((build/'build.json').read_text());corpus=json.loads((build/'corpus.json').read_text());elf=build/'batch.elf'
 if r['elf_sha256']!=sha(elf)or r['corpus_sha256']!=sha(build/'corpus.json')or r['deliberate_noop_negative']!=a.negative:raise ValueError('Exact build/negative identity')
 inputs=dict(r['input_sha256']);paths=[Path(__file__),Path(__file__).with_name('model_operator_batch_validate.py'),build/'build.json',build/'corpus.json',build/'binary-proof.json',elf];native=ROOT/'build/combined-frozen-35901887/spike';uart=native.with_name('libsifive_uart.so');rom=ROOT/'board/evidence/bootrom.rv64.img';dtb=ROOT/'board/build/iris.dtb';paths.extend([native,uart,rom,dtb]);inputs.update({str(p.resolve()):sha(p)for p in paths})
 for name,d in inputs.items():
  if sha(name)!=d:raise ValueError('Changed input '+name)
 compute='rv64gcv_zfh_zvfh_zba_zbb_zbs_zvbb_zvl256b_zvfofp8min_zvfbfmin_zvfbfa_zvt32t_zvti8i32mm_zvtofp8fmm'
 argv=[str(native),'--iris-vme','--isa=rv64gcv_zfh_zvfh_zvl256b_zvbb','--hart-isa=0:'+compute,'--hart-isa=1:'+compute,'--hart-isa=2:rv64gcv_zfh_zvfh_zvl256b_zvbb','-p3','-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000','--extlib='+str(uart),'--device=sifive_uart,0x10020000','--iris-bootrom='+str(rom),'--dtb='+str(dtb),'--iris-schedule-seed='+str(a.seed),str(elf)]
 start=time.monotonic();code=None;timeout=False
 with(out/'stdout').open('wb')as stdout,(out/'stderr').open('wb')as stderr:
  try:code=subprocess.run(argv,stdout=stdout,stderr=stderr,timeout=a.timeout,env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH'])).returncode
  except subprocess.TimeoutExpired:timeout=True
 result=dict(schema='iris.model_operator_batch_functional_run.v1',**{'pass':False},seed=a.seed,argv=argv,returncode=code,timed_out=timeout,timeout_seconds=a.timeout,host_seconds=time.monotonic()-start,deliberate_noop_negative=a.negative,elf_sha256=sha(elf),native_sha256=sha(native),uart_sha256=sha(uart),input_sha256=inputs,stdout_sha256=sha(out/'stdout'),stderr_sha256=sha(out/'stderr'),hardware_contacted=False,calibration_usable=False)
 try:
  if a.negative:
   text=(out/'stdout').read_text();rows=[json.loads(x[len('IRIS_REGION '):])for x in text.splitlines()if x.startswith('IRIS_REGION ')];compute=[x for x in rows if x['hart']!=2];failed=sum(x['failed_words']for x in compute)
   if timeout or code==0 or len(rows)!=120 or failed!=3072 or any(x['pass']for x in compute):raise ValueError('Actual omitted-kernel control did not fail all3072 output words')
   result['proof']=dict(fresh_output_omission_detected=True,failed_compute_words=failed,regions=len(rows))
  else:
   if timeout or code!=0:raise ValueError('Guest did not exit successfully')
   result['proof']=validate((out/'stdout').read_text(),corpus)
  for name,d in inputs.items():
   if sha(name)!=d:raise ValueError('Input changed during execution')
  result['pass']=True
 except(ValueError,KeyError,TypeError)as error:result['error']=str(error)
 (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result.get(k)for k in ['pass','seed','host_seconds','proof','error']}))
 return 0 if result['pass']else 1
if __name__=='__main__':raise SystemExit(main())
