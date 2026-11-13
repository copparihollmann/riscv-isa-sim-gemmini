#!/usr/bin/env python3
"""New finite-scope rejection and exact OFF parity gates; no timing labels."""
from pathlib import Path
import argparse,concurrent.futures,hashlib,json,subprocess
from check_VSE_live_boundary_native_v1 import R,B,P,F,execute,sha
def negative(o,kind,expected):
 build=o/(kind+'-guest');subprocess.run(['python3',str(R/'benchmarks/vse_live_boundary_v1/build.py'),'--output',str(build),'--negative',kind],check=True,capture_output=True)
 f=o/(kind+'.fixture');f.write_text(F.read_text()+'\nexperimental_vse_boundary SYNTHETIC-DIRECTED-TEST-ONLY-v1 0 20 core_edges\n');d=o/kind;r=execute(d,B/'spike',B/'libsifive_uart.so',f,build/'guest.elf');stderr=(d/'stderr').read_text();ev=[json.loads(x)for x in(d/'async.jsonl').read_text().splitlines()]if(d/'async.jsonl').exists()else[]
 checks=[not r['timed_out'],r['exit_status']not in(None,0),expected in stderr,not any(x.get('event')=='VSE_boundary_synthetic_response_publish'for x in ev),'IRIS_VSE_BOUNDARY_DONE'not in(d/'stdout').read_text()]
 return dict(kind=kind,**{'pass':all(checks)},checks=checks,expected=expected,path=str(d))
def parser(o,name,line):
 f=o/(name+'.fixture');f.write_text(F.read_text()+'\n'+line+'\n');d=o/name;r=execute(d,B/'spike',B/'libsifive_uart.so',f,R/'build/VSE-live-boundary-guest-h0-v1/guest.elf');s=(d/'stderr').read_text();return dict(kind=name,**{'pass':r['exit_status']not in(None,0)and not r['timed_out']and'IRIS_VSE_BOUNDARY_'in s and not(d/'stdout').read_bytes()},path=str(d))
def parity(o,h,seed):
 elf=R/('build/VSE-live-boundary-guest-h'+str(h)+'-v1/guest.elf');d=o/('OFF-h%d-seed%d'%(h,seed));d.mkdir();runs=[]
 for name,n,u in[('parent',P/'spike',P/'libsifive_uart.so'),('new',B/'spike',B/'libsifive_uart.so')]:runs.append(execute(d/name,n,u,F,elf,seed))
 checks=[r['exit_status']==0 and not r['timed_out']for r in runs];compared={}
 for name in('stdout','stderr','summary.json','features.jsonl','async.jsonl'):
  a=(d/'parent'/name);b=(d/'new'/name);same=a.read_bytes()==b.read_bytes();checks.append(same);compared[name]={'equal':same,'parent_sha256':sha(a),'new_sha256':sha(b)}
 return dict(kind='OFF-parity',hart=h,seed=seed,**{'pass':all(checks)},path=str(d),compared=compared)
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();o=a.output.resolve();o.mkdir(exist_ok=False);cases=[('IRQ_ENABLE','IRIS_VSE_BOUNDARY_GLOBAL_IRQ_ENABLE_UNSUPPORTED'),('PENDING_IRQ','IRIS_VSE_BOUNDARY_PENDING_IRQ_UNSUPPORTED'),('BUSY_PEER','IRIS_VSE_BOUNDARY_PEER_NOT_QUIET'),('UNKNOWN_SOURCE','IRIS_VSE_BOUNDARY_UNDEFINED_VRF_SOURCE'),('MISALIGNED','IRIS_VSE_BOUNDARY_FINITE_ADDRESS_ALIGNMENT'),('WRONG_EEW','IRIS_VSE_BOUNDARY_REQUIRES_UNMASKED_UNITSTRIDE_NF1_VSE32')]
 with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:
  jobs=[pool.submit(negative,o,*c)for c in cases]+[pool.submit(parity,o,h,s)for h in(0,1)for s in(0,17)]+[pool.submit(parser,o,'production-unavailable','experimental_vse_boundary source-System-v6-production-v1'),pool.submit(parser,o,'wrong-hart','experimental_vse_boundary SYNTHETIC-DIRECTED-TEST-ONLY-v1 2 20 core_edges'),pool.submit(parser,o,'missing-explicit-test','experimental_vse_boundary synthetic 0 20 core_edges'),pool.submit(parser,o,'zero-ACK','experimental_vse_boundary SYNTHETIC-DIRECTED-TEST-ONLY-v1 0 0 core_edges')]
  results=[j.result()for j in jobs]
 report=dict(schema='iris.VSE_live_boundary_guards_and_OFF.v1',**{'pass':all(x['pass']for x in results)},cases=results,hardware_contacted=False,protected_labels_read=False,source_backend_available=False,input_sha256={str(x):sha(x)for x in[Path(__file__),R/'timing/check_VSE_live_boundary_native_v1.py',B/'pipeline-build.json']});(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':report['pass'],'report_sha256':sha(o/'report.json')}));raise SystemExit(not report['pass'])
if __name__=='__main__':main()
