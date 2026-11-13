#!/usr/bin/env python3
"""Read-only reproduction of an exact compiled twin's frontend RAS failure."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__)
 p.add_argument('--binary',type=Path,required=True);p.add_argument('--uart',type=Path,required=True)
 p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 original=ROOT/'build/empirical-compute-525-merlin-gemm-h1-v1'
 elf=original/'twin.elf';fixture=ROOT/'calibration/compute-fit-525-selected-v1/runtime.fixture'
 args=json.loads((ROOT/'build/rocket-packet-native-first-v1/report.json').read_text())['argv']
 args=[x for x in args if not x.startswith(('--iris-timing-fixture=','--iris-timing-trace='))]
 args=['--extlib='+str(a.uart.resolve())if x.startswith('--extlib=')else x for x in args]
 args[0]=str(a.binary.resolve());args[-1]=str(elf);args[-1:-1]=['--iris-timing-fixture='+str(fixture)]
 paths=[Path(__file__).resolve(),a.binary.resolve(),a.uart.resolve(),elf,fixture,
  ROOT/'pipeline/fast_source_frontend_merlin_ras_observer.cpp']
 inputs={str(p):sha(p)for p in paths};t=time.monotonic()
 r=subprocess.run(args,capture_output=True,timeout=180,env=dict(os.environ,
  IRIS_EMPIRICAL_FEATURES=str(out/'features.jsonl'),IRIS_RAS_CAPTURE=str(out/'physical-inputs')))
 (out/'stdout').write_bytes(r.stdout);(out/'stderr').write_bytes(r.stderr)
 assert all(sha(p)==h for p,h in inputs.items())
 before=[json.loads(x)for x in(original/'twin.features.jsonl').read_text().splitlines()]
 after=[json.loads(x)for x in(out/'features.jsonl').read_text().splitlines()]
 assert before==after,'diagnostic changed actual pre-failure prefix'
 errors=[json.loads(x.split(' ',1)[1])for x in r.stderr.decode().splitlines()if x.startswith('RAS_OBSERVER_FAILURE ')]
 assert r.returncode==1 and len(errors)==1 and errors[0]['edge']==1300498,errors
 report={'schema':'iris.merlin_RAS_readonly_diagnostic.v1','pass':True,'argv':args,
  'host_seconds':time.monotonic()-t,'returncode':r.returncode,'input_sha256':inputs,
  'original_prefix_dictionaries_equal':len(before),'failure':errors[0],
  'policy_changed':False,'source_or_image_association_certified':False}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
