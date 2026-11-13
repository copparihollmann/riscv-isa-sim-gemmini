"""Actual normal359 single-case stage diagnostic; no hardware and no timing fit."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
from validate import validate
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,required=True);p.add_argument('--negative',action='store_true');a=p.parse_args();b=a.build.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 parent=json.loads((ROOT/'build/rvv-identify-TK-v4/seed0/run.json').read_text());argv=parent['argv'][:-1]+[str(b/'guest.elf')];argv=[('--iris-schedule-seed='+str(a.seed))if x.startswith('--iris-schedule-seed=')else x for x in argv];build=json.loads((b/'build.json').read_text());assert build['skip_kernel']is a.negative
 ids=dict(build['input_sha256']);ids.update({str(p):sha(p)for p in[Path(__file__).resolve(),b/'guest.elf',b/'build.json',Path(argv[0]),ROOT/'build/combined-frozen-35901887/libsifive_uart.so',ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb']});assert all(sha(p)==h for p,h in ids.items());env=dict(os.environ);env.pop('IRIS_FATAL_PCS',None);start=time.monotonic();code=None;timed=False;error=None;proof=None
 with(out/'stdout').open('wb')as stdout,(out/'stderr').open('wb')as stderr:
  try:code=subprocess.run(argv,stdout=stdout,stderr=stderr,env=env,timeout=120).returncode
  except subprocess.TimeoutExpired:timed=True
 try:
  assert not timed and(code!=0 if a.negative else code==0);proof=validate((out/'stdout').read_text(),a.negative);assert all(sha(p)==h for p,h in ids.items())
 except(Exception)as e:error=str(e)or type(e).__name__
 r=dict(schema='iris.hart2_256_probe_functional.v1',**{'pass':error is None},normal_exit=not timed and code==0,expect_negative=a.negative,exit_status=code,timed_out=timed,seed=a.seed,host_seconds=time.monotonic()-start,argv=argv,input_sha256=ids,stdout_sha256=sha(out/'stdout'),stderr_sha256=sha(out/'stderr'),proof=proof,error=error,diagnostic_only=True,calibration_usable=False,hardware_contacted=False);(out/'run.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r[k]for k in('pass','seed','host_seconds','error')}));raise SystemExit(0 if r['pass']else 1)
if __name__=='__main__':main()
