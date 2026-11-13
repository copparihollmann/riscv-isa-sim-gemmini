#!/usr/bin/env python3
"""Run one frozen broad campaign locally; no FPGA actions or timing claims."""
import argparse,hashlib,json,os,shutil,subprocess,time
from pathlib import Path
from validate import validate
R=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--binary',type=Path,default=R/'build/combined-frozen-35901887/spike');p.add_argument('--uart',type=Path,default=R/'build/combined-frozen-35901887/libsifive_uart.so');p.add_argument('--seed',type=int,default=0);p.add_argument('--timeout',type=int,default=900);a=p.parse_args();b=a.build.resolve();o=a.output.resolve()
 if o.exists():raise ValueError('Fresh run directory required')
 build=json.loads((b/'build.json').read_text());corpus=json.loads((b/'corpus.json').read_text());assert sha(b/'campaign.elf')==build['elf_sha256']
 for path,d in build['input_sha256'].items():assert sha(path)==sha(b/'inputs'/d)==d,('Changed build input',path)
 for path,d in corpus['parent_source_sha256'].items():assert sha(R/path)==d,('Parent source changed',path)
 o.mkdir();dtc=Path('/scratch/eygao/iris-cy/.conda-env/bin/dtc');rom=R/'board/evidence/bootrom.rv64.img';dtb=R/'board/build/iris.dtb';inputs=[a.binary.resolve(),a.uart.resolve(),rom,dtb,dtc,b/'campaign.elf',b/'build.json',b/'corpus.json',Path(__file__),Path(__file__).with_name('validate.py')];identities={str(p):sha(p) for p in inputs};(o/'inputs').mkdir()
 for path,d in identities.items():
  target=o/'inputs'/d
  if not target.exists():shutil.copyfile(path,target)
 dma='rv64gcv_zfh_zvfh_zvl256b_zvbb';compute='rv64gcv_zfh_zvfh_zba_zbb_zbs_zvbb_zvl256b_zvfofp8min_zvfbfmin_zvfbfa_zvt32t_zvti8i32mm_zvtofp8fmm'
 argv=[str(a.binary.resolve()),'--iris-vme','--isa='+dma,'--hart-isa=0:'+compute,'--hart-isa=1:'+compute,'--hart-isa=2:'+dma,'-p3','-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000','--extlib='+str(a.uart.resolve()),'--device=sifive_uart,0x10020000','--iris-bootrom='+str(rom),'--dtb='+str(dtb),'--iris-schedule-seed='+str(a.seed),str(b/'campaign.elf')];env=dict(os.environ,PATH=str(dtc.parent)+os.pathsep+os.environ.get('PATH',''));env.pop('IRIS_FATAL_PCS',None);started=time.monotonic();error=None
 with (o/'run.stdout').open('w')as stdout,(o/'run.stderr').open('w')as stderr:
  try:q=subprocess.run(argv,cwd=o,env=env,stdout=stdout,stderr=stderr,timeout=a.timeout);status=q.returncode
  except subprocess.TimeoutExpired:status=None;error='timeout'
 receipt={'schema':'iris.broad_campaign_functional_run.v1','argv':argv,'exit_status':status,'seed':a.seed,'host_seconds':time.monotonic()-started,'input_sha256':identities,'stdout_sha256':sha(o/'run.stdout'),'stderr_sha256':sha(o/'run.stderr'),'timing_certified':False,'calibration_usable':False,'hardware_contacted':False}
 try:
  if status!=0:raise ValueError(error or 'exit '+str(status))
  receipt.update(validate((o/'run.stdout').read_text(),corpus))
  for path,d in {**build['input_sha256'],**identities}.items():assert sha(path)==d,('Execution input changed',path)
 except (ValueError,KeyError,TypeError,AssertionError)as e:receipt.update(functional_checks_passed=False,error=str(e))
 (o/'run.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt,indent=2))
 if not receipt['functional_checks_passed']:raise SystemExit(1)
if __name__=='__main__':main()
