#!/usr/bin/env python3
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);a=ap.parse_args();o=Path(a.output).resolve();o.mkdir(parents=True,exist_ok=False)
 parent=ROOT/'build/warm-OPU-TK124-c12-refusals-v1/report.json';src=json.load(open(parent));native=ROOT/'build/opu-fence-native-v1/spike';uart=ROOT/'build/opu-fence-native-v1/libsifive_uart.so';fixture=ROOT/'build/opu-fence-inputs-v1/ON.fixture'
 ins={str(p):sha(p)for p in(Path(__file__).resolve(),parent,native,uart,fixture)};cases=[];env=dict(os.environ)
 for k in('IRIS_EMPIRICAL_FEATURES','IRIS_EMPIRICAL_ASYNC_TRACE','IRIS_FATAL_PCS'):env.pop(k,None)
 for c in src['cases']:
  argv=c['argv'][:];argv[0]=str(native);argv=['--extlib='+str(uart)if v.startswith('--extlib=')else'--iris-timing-fixture='+str(fixture)if v.startswith('--iris-timing-fixture=')else v for v in argv];elf=Path(argv[-1]);assert sha(elf)==c['ELF_sha256'];ins[str(elf)]=sha(elf);t=time.monotonic();r=subprocess.run(argv,capture_output=True,timeout=30,env=env);d=o/str(c['mode']);d.mkdir();(d/'stdout').write_bytes(r.stdout);(d/'stderr').write_bytes(r.stderr);cases.append({'mode':c['mode'],'argv':argv,'exit_status':r.returncode,'expected':c['expected'],'pass':r.returncode!=0 and c['expected']in r.stderr.decode(),'host_seconds':time.monotonic()-t,'stdout_sha256':sha(d/'stdout'),'stderr_sha256':sha(d/'stderr')})
 # Source selector parser must reject both an unknown token and absence of C12.
 for name,text,expected in [('unknown-selector',fixture.read_text().replace('source-MM-only-FM0-busy-not-numeric-tail-v1','invented-v99'),'unsupported source OPU FENCE join'),('missing-entry', '\n'.join(v for v in fixture.read_text().splitlines()if not v.startswith('empirical_opu_entry '))+'\n','OPU FENCE specialization')]:
  f=o/(name+'.fixture');f.write_text(text);argv=src['cases'][0]['argv'][:];argv[0]=str(native);argv=['--extlib='+str(uart)if v.startswith('--extlib=')else'--iris-timing-fixture='+str(f)if v.startswith('--iris-timing-fixture=')else v for v in argv];r=subprocess.run(argv,capture_output=True,timeout=30,env=env);(o/(name+'.stderr')).write_bytes(r.stderr);cases.append({'name':name,'exit_status':r.returncode,'expected_substring':expected,'stderr':r.stderr.decode(),'pass':r.returncode!=0 and expected.lower()in r.stderr.decode().lower(),'fixture_sha256':sha(f)})
 report={'schema':'iris.opu_fence_refusal_guards.v1','pass':all(v['pass']for v in cases),'cases':cases,'input_sha256':ins,'hardware_contacted':False,'scope':'Existing shape/unknownVRF/activeIRQ guards unchanged under ON; invalid new selector and missing source entry refused before execution'};(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':report['pass'],'cases':len(cases)}));return 0 if report['pass']else 1
if __name__=='__main__':raise SystemExit(main())
