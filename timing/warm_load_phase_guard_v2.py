#!/usr/bin/env python3
"""Finite opt-in warm-hit fallback, knownness and selector refusal controls."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,time
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--binary',type=Path,required=True);p.add_argument('--uart',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True);a=p.parse_args();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
 template=json.loads((R/'build/warm-load-phase-native-v2/argv.json').read_text());rows=[]
 tests=[('coherence-opaque-copy',R/'build/empirical-load-front-guest-v2/guest.elf',0,None)]+[('undefined-consumer-h'+str(h),R/('build/empirical-load-front-undefined-h'+str(h)+'-v1/guest.elf'),1,None)for h in range(3)]
 tests +=[('unknown-selector',R/'build/warm-load-phase-guest-v2/guest.elf',1,a.fixture.read_text().replace('dram-L1-hit-Shuttle-COM-forward-v2','unknown-load-policy')),('duplicate-selector',R/'build/warm-load-phase-guest-v2/guest.elf',1,a.fixture.read_text()+'\nempirical_load_front dram-L1-hit-latched-response-v1\n')]
 for name,elf,expect,override in tests:
  d=o/name;d.mkdir();fixture=a.fixture.resolve()
  if override is not None:fixture=d/'bad.fixture';fixture.write_text(override)
  argv=[str(a.binary.resolve()),*['--extlib='+str(a.uart.resolve())if x.startswith('--extlib=')else'--iris-timing-fixture='+str(fixture)if x.startswith('--iris-timing-fixture=')else'--iris-timing-trace='+str(d/'summary.json')if x.startswith('--iris-timing-trace=')else x for x in template[1:]]];argv[-1]=str(elf);paths=[Path(__file__).resolve(),a.binary.resolve(),a.uart.resolve(),fixture,elf,R/'board/evidence/bootrom.rv64.img',R/'board/build/iris.dtb'];before={str(x):sha(x)for x in paths};start=time.monotonic();cp=subprocess.run(argv,capture_output=True,timeout=120);(d/'stdout').write_bytes(cp.stdout);(d/'stderr').write_bytes(cp.stderr);assert before=={str(x):sha(x)for x in paths}
  if expect==0:
   fields=[x.split()for x in cp.stdout.decode().splitlines()if x.startswith('IRIS_LOAD_FRONT ')];passed=cp.returncode==0 and len(fields)==3 and all(int(x[2])==0 and int(x[4])==7 for x in fields)and {int(x[1])for x in fields}=={0,1,2}
  elif override is not None:passed=cp.returncode!=0 and b'unsupported empirical load front'in cp.stderr
  else:passed=cp.returncode==1 and ('IRIS_UNDEFINED_STATE hart='+name[-1]+' ').encode()in cp.stderr
  row=dict(name=name,pass_=passed,argv=argv,exit_status=cp.returncode,expected_exit_status=expect,host_seconds=time.monotonic()-start,input_sha256=before,stdout_sha256=sha(d/'stdout'),stderr_sha256=sha(d/'stderr'));(d/'report.json').write_text(json.dumps(row,indent=2)+'\n');rows.append(row);print(name,passed,cp.returncode,cp.stderr.decode()[-200:],flush=True)
 report=dict(schema='iris.warm_load_phase_guard_controls.v1',pass_=all(x['pass_']for x in rows),runs=rows,hardware_contacted=False,phase_whole_SoC_certified=False);report['pass']=report.pop('pass_');(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');raise SystemExit(0 if report['pass']else 1)
if __name__=='__main__':main()
