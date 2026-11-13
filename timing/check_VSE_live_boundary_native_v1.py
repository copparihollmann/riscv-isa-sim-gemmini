#!/usr/bin/env python3
"""Own normal-ELF VSE quarantine/owner gates; synthetic service only."""
from pathlib import Path
import argparse,concurrent.futures,hashlib,json,os,signal,subprocess,time
R=Path(__file__).resolve().parents[1]
B=R/'build/spike-VSE-live-boundary-v1';P=R/'build/C12-VADD-EG-frozen-35a80496-v2';F=R/'build/C12-source-VADD-fixed-cost-inputs-v1/runtime.fixture'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def execute(d,native,uart,fixture,elf,seed=0):
 d.mkdir();template=json.loads((R/'build/saturn-native-first-v2/results.json').read_text())['argv'];argv=[]
 for i,x in enumerate(template):
  if i==0:x=str(native)
  elif x.startswith('--extlib='):x='--extlib='+str(uart)
  elif x.startswith('--iris-timing-fixture='):x='--iris-timing-fixture='+str(fixture)
  elif x.startswith('--iris-timing-trace='):x='--iris-timing-trace='+str(d/'summary.json')
  elif i==len(template)-1:x=str(elf)
  argv.append(x)
 argv.insert(-1,'--iris-schedule-seed='+str(seed));env={k:v for k,v in os.environ.items()if not k.startswith('IRIS_')};env.update(IRIS_EMPIRICAL_ASYNC_TRACE=str(d/'async.jsonl'),IRIS_EMPIRICAL_FEATURES=str(d/'features.jsonl'));start=time.perf_counter();timed=False
 with(d/'stdout').open('wb')as so,(d/'stderr').open('wb')as se:
  process=subprocess.Popen(argv,env=env,stdout=so,stderr=se,start_new_session=True)
  try:code=process.wait(timeout=90)
  except subprocess.TimeoutExpired:
   timed=True;os.killpg(process.pid,signal.SIGTERM)
   try:process.wait(timeout=3)
   except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
   code=process.returncode
 inputs=[native,uart,fixture,elf,R/'board/evidence/bootrom.rv64.img',R/'board/build/iris.dtb'];rep=dict(schema='iris.VSE_live_boundary_execution.v1',argv=argv,exit_status=code,timed_out=timed,host_seconds=time.perf_counter()-start,input_sha256={str(x):sha(x)for x in inputs},output_sha256={str(x):sha(x)for x in d.iterdir()if x.is_file()});(d/'run.json').write_text(json.dumps(rep,indent=2)+'\n');return rep
def positive(d,h,seed,ack):
 f=d.parent/(d.name+'.fixture');f.write_text(F.read_text()+'\nexperimental_vse_boundary SYNTHETIC-DIRECTED-TEST-ONLY-v1 '+str(h)+' '+str(ack)+' core_edges\n');elf=R/('build/VSE-live-boundary-guest-h'+str(h)+'-v1/guest.elf');r=execute(d,B/'spike',B/'libsifive_uart.so',f,elf,seed);checks=[]
 stdout=(d/'stdout').read_text();rows=[json.loads(x.split(' ',1)[1])for x in stdout.splitlines()if x.startswith('IRIS_VSE_BOUNDARY {')];gold=json.loads((elf.parent/'build.json').read_text());checks.extend([r['exit_status']==0,not r['timed_out'],len(rows)==1,'IRIS_VSE_BOUNDARY_DONE'in stdout,not(d/'stderr').read_text()])
 if rows:checks.append(rows[0]==dict(hart=h,checked_words=512,stored_words=193,mismatch_or=0,checksum=gold['independent_expected_checksum']))
 events=[json.loads(x)for x in(d/'async.jsonl').read_text().splitlines()];events=[x for x in events if x['event'].startswith('VSE_boundary_')];front=[x for x in events if x['event']=='VSE_boundary_checked_COM'];reserve=[x for x in events if x['event']=='VSE_boundary_reserve'];accept=[x for x in events if x['event']=='VSE_boundary_synthetic_request_accept'];ACK=[x for x in events if x['event']=='VSE_boundary_synthetic_response_publish'];release=[x for x in events if x['event']=='VSE_boundary_ordered_SIFQ_release'];key=lambda x:(x['command'],x['tag'],x['generation'])
 checks.extend([len(front)==8,len(reserve)==49,len(accept)==49,len(ACK)==49,len(release)==49,sum(x['bytes']for x in ACK)==772,len({key(x)for x in reserve})==49,[key(x)for x in release]==[key(x)for x in reserve],[key(x)for x in ACK]!=[key(x)for x in release],max(x['generation']for x in reserve)>1])
 maps=[{key(x):x for x in xs}for xs in(reserve,accept,ACK,release)]
 for k in maps[0]:
  if not all(k in m for m in maps):checks.append(False);continue
  a,b,c,e=(m[k]for m in maps);checks.extend([a['cycle']<b['cycle']<c['cycle']<=e['cycle'],c['cycle']-b['cycle']==ack+(0 if b['tag']&1 else 3),a['VRF_value_and_known_lease_checked']])
 for a,b in zip(front,front[1:]):checks.append(b['cycle']>max(x['cycle']for x in release if x['command']==a['command']))
 summary=json.loads((d/'summary.json').read_text())['VSE_live_boundary'];checks.append(summary['commands']==summary['completed']==8 and not summary['pending']and summary['ACKs']==summary['ordered_releases']==49)
 return dict(kind='positive',path=str(d),**{'pass':all(checks)},checks=len(checks),failed_checks=[i for i,x in enumerate(checks)if not x],normal_exit=r['exit_status']==0,synthetic_service=True,physical_or_timing_claim=False)
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--quick',action='store_true');a=p.parse_args();o=a.output.resolve();o.mkdir(exist_ok=False);reports=[]
 cases=[(0,0,20)]if a.quick else[(h,s,ack)for h in(0,1)for s in(0,17)for ack in(1,20,200)]
 with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:
  jobs=[pool.submit(positive,o/('h%d-seed%d-ACK%d'%c),*c)for c in cases]
  reports.extend(j.result()for j in jobs)
 report=dict(schema='iris.VSE_live_boundary_native_directed.v1',**{'pass':all(r['pass']for r in reports)},runs=reports,source_qualified_timing=False,physical_memory_backend_available=False,hardware_or_protected_labels_consumed=False,input_sha256={str(x):sha(x)for x in[Path(__file__),R/'timing/vse_live_boundary_v1.hpp',B/'pipeline-build.json']});(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':report['pass'],'report':str(o/'report.json'),'sha256':sha(o/'report.json')}));raise SystemExit(not report['pass'])
if __name__=='__main__':main()
