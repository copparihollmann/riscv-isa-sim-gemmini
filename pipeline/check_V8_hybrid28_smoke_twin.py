#!/usr/bin/env python3
"""Exact frozen V8/legacy28-mode smoke and known RAS-sensitive Merlin twin."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from benchmarks.validate_console import validate
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
B=ROOT/'build/empirical-read-overlap-response-frozen-7bd58b4f';fixture=ROOT/'build/empirical-V8-hybrid28-inputs-v1/hybrid.fixture';O=ROOT/'build/empirical-V8-hybrid28-smoke-twin-v1';O.mkdir(exist_ok=False);runs=[]
base=json.load(open(ROOT/'build/empirical-priority-28a0-selected-selftest-v2/smoke/report.json'))['argv']
for kind,elf in [('smoke',ROOT/'benchmarks/build/smoke.elf'),('twin',ROOT/'build/empirical-compute-525-merlin-gemm-h1-v1/twin.elf')]:
 d=O/kind;d.mkdir();argv=[str(B/'spike')]+[('--extlib='+str(B/'libsifive_uart.so')if x.startswith('--extlib=')else x)for x in base[1:-1]if not x.startswith(('--iris-timing-fixture=','--iris-timing-trace='))]+['--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(d/'summary.json'),str(elf)]
 inputs=[Path(__file__).resolve(),B/'manifest.json',B/'spike',B/'libsifive_uart.so',fixture,elf];hashes={str(p):sha(p)for p in inputs};t=time.monotonic();r=subprocess.run(argv,capture_output=True,timeout=180,env=dict(os.environ,IRIS_EMPIRICAL_FEATURES=str(d/'features.jsonl')));elapsed=time.monotonic()-t;(d/'stdout').write_bytes(r.stdout);(d/'stderr').write_bytes(r.stderr)
 report={'kind':kind,'pass':False,'argv':argv,'returncode':r.returncode,'host_seconds':elapsed,'input_sha256':hashes};(d/'report.json').write_text(json.dumps(report,indent=2)+'\n');assert r.returncode==0,(kind,r.stderr.decode())
 if kind=='smoke':proof=validate(r.stdout.decode(),json.load(open(ROOT/'benchmarks/calibration-corpus.json')),3,True)
 else:
  golden=ROOT/'build/empirical-compute-525-merlin-gemm-h1-v1/golden.json';want=json.load(open(golden));seen={}
  for line in r.stdout.decode().splitlines():
   if line.startswith(('ACC_I32 ','W8A8_F32 ')):
    fields=line.split();seen[fields[0]]=list(map(int,fields[2:]));assert int(fields[1])==len(seen[fields[0]])
  assert seen['ACC_I32']==want['accumulator_u32'] and seen['W8A8_F32']==want['w8a8_f32_words'];proof={'full_accumulator_words':len(seen['ACC_I32']),'full_w8a8_words':len(seen['W8A8_F32']),'known_strict_source_RAS_sensitive_twin_ELF':sha(elf),'golden_sha256':sha(golden)}
 summary=json.load(open(d/'summary.json'));assert summary['fast_source_frontend_enabled']is False;assert summary['source_cuts_evaluated']is False;assert 'read_overlap_scope'in summary
 assert all(sha(p)==h for p,h in hashes.items());report.update({'pass':True,'proof':proof,'frontend_mode':'legacy empirical approximation; source frontend/RAS disabled by exact legacy directives','warm_read_accepts':summary['warm_read_accepts'],'read_dependencies_omitted':summary['compatible_read_dependencies_omitted'],'source_image_association_verified':False,'timing_accuracy_certified':False});(d/'report.json').write_text(json.dumps(report,indent=2)+'\n');runs.append({'kind':kind,'report_sha256':sha(d/'report.json')});print(kind,elapsed,flush=True)
(O/'report.json').write_text(json.dumps({'schema':'iris.V8_hybrid28_smoke_twin.v1','pass':True,'runs':runs,'fixture_sha256':sha(fixture),'new_model_epoch':True,'coefficients_changed':False,'qualification_transferred':False,'v6_reference_consumed':False},indent=2)+'\n');print(sha(O/'report.json'))
