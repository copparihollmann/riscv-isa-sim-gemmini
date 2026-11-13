#!/usr/bin/env python3
"""Run an exact footprint ELF with normal HTIF exit and record raw evidence."""
import argparse,json,os,subprocess,time
from pathlib import Path
from build import ROOT,sha
from validate import validate,validate_corpus

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,required=True);p.add_argument('--expect-negative',action='store_true');a=p.parse_args();b=a.build.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);r=json.loads((b/'build.json').read_text());c=json.loads((b/'corpus.json').read_text());elf=b/'guest.elf';assert sha(elf)==r['ELF_sha256'];assert r['skip_kernel']is a.expect_negative
 for name,h in r['input_sha256'].items():assert sha(name)==h and sha(b/'inputs'/h)==h,name
 if not a.expect_negative:validate_corpus(c)
 binary=ROOT/'build/combined-frozen-35901887/spike';uart=binary.with_name('libsifive_uart.so');rom=ROOT/'board/evidence/bootrom.rv64.img';dtb=ROOT/'board/build/iris.dtb';dma='rv64gcv_zfh_zvfh_zvl256b_zvbb';compute='rv64gcv_zfh_zvfh_zba_zbb_zbs_zvbb_zvl256b_zvfofp8min_zvfbfmin_zvfbfa_zvt32t_zvti8i32mm_zvtofp8fmm';argv=[str(binary),'--iris-vme','--isa='+dma,'--hart-isa=0:'+compute,'--hart-isa=1:'+compute,'--hart-isa=2:'+dma,'-p3','-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000','--extlib='+str(uart),'--device=sifive_uart,0x10020000','--iris-bootrom='+str(rom),'--dtb='+str(dtb),'--iris-schedule-seed='+str(a.seed),str(elf)]
 inputs=dict(r['input_sha256']);inputs.update({str(p):sha(p)for p in[Path(__file__).resolve(),b/'build.json',elf,binary,uart,rom,dtb]});env=dict(os.environ);env.pop('IRIS_FATAL_PCS',None);start=time.monotonic();timed=False;code=None
 with(out/'stdout').open('wb')as stdout,(out/'stderr').open('wb')as stderr:
  try:code=subprocess.run(argv,env=env,stdout=stdout,stderr=stderr,timeout=180).returncode
  except subprocess.TimeoutExpired:timed=True
 elapsed=time.monotonic()-start;text=(out/'stdout').read_text();proof={};error=None
 try:
  if timed:raise ValueError('Owned180s bound reached')
  if a.expect_negative:
   rows=[json.loads(l[len('IRIS_REGION '):])for l in text.splitlines()if l.startswith('IRIS_REGION ')];done=[json.loads(l[len('IRIS_BATCH_DONE '):])for l in text.splitlines()if l.startswith('IRIS_BATCH_DONE ')];assert code!=0 and code is not None and len(rows)==1320 and all(x['pass']is False and (x['mismatch_or']!=0 or x['checksum']!=x['expected_checksum']) for x in rows)and done==[dict(failed=1320,cases=1320,regions=1320,trials=3)]
   proof=dict(actual_omitted_kernel_detected=True,failed_regions=1320)
  else:
   if code!=0:raise ValueError('Guest failed')
   proof=validate(text,c)
  if any(sha(p)!=h for p,h in inputs.items()):raise ValueError('Bound input changed')
 except(ValueError,AssertionError,KeyError,TypeError)as exc:error=str(exc)or type(exc).__name__
 report=dict(schema='iris.rvv_identify_functional_run.v1',**{'pass':error is None},argv=argv,seed=a.seed,expect_negative=a.expect_negative,normal_guest_exit_verified=not timed and code==0,exit_status=code,timed_out=timed,host_seconds=elapsed,elf_sha256=sha(elf),input_sha256=inputs,stdout_sha256=sha(out/'stdout'),stderr_sha256=sha(out/'stderr'),proof=proof,error=error,hardware_contacted=False,timing_certified=False);(out/'run.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report[k]for k in('pass','seed','host_seconds','proof','error')}));raise SystemExit(0 if report['pass']else 1)
if __name__=='__main__':main()
