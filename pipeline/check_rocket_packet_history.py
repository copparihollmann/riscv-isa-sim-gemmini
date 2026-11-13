#!/usr/bin/env python3
"""Compare complete small-guest history modes and actual source-fetch observations."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--uart',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 original=ROOT/'build/rocket-packet-native-first-v1/report.json';base=json.loads(original.read_text())['argv'];source=ROOT/'build/rocket-packet-native-first-v1/first.fixture';runs={};inputs=[Path(__file__).resolve(),a.binary.resolve(),a.uart.resolve(),original,source,Path(base[-1]),ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb'];before={str(x):sha(x)for x in inputs}
 for history in['bounded','full']:
  d=out/history;d.mkdir();text=source.read_text();old='empirical_profile experimental-effective-services unfitted-bounded-v1 bounded';assert text.count(old)==1;fixture=d/'fixture';fixture.write_text(text.replace(old,old[:-7]+history));argv=[x for x in base if not x.startswith(('--iris-timing-fixture=','--iris-timing-trace='))];argv[0]=str(a.binary.resolve());argv=['--extlib='+str(a.uart.resolve())if x.startswith('--extlib=')else x for x in argv];argv[-1:-1]=['--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(d/'graph.json')];env=dict(os.environ,IRIS_EMPIRICAL_FEATURES=str(d/'features.jsonl'),IRIS_ROCKET_PACKET_TRACE=str(d/'packets.jsonl'));t=time.monotonic();r=subprocess.run(argv,capture_output=True,env=env,timeout=120);elapsed=time.monotonic()-t;(d/'stdout').write_bytes(r.stdout);(d/'stderr').write_bytes(r.stderr);assert r.returncode==0,(history,r.stderr.decode());assert b'IRIS_SATURN_LIVE_VALUES 8 6 64\n'in r.stdout and b'IRIS_SATURN_LIVE_DONE 3\n'in r.stdout;rows=[json.loads(x)for x in(d/'features.jsonl').read_text().splitlines()];graph=json.loads((d/'graph.json').read_text());runs[history]={'rows':rows,'graph':graph,'host_seconds':elapsed,'argv':argv,'stdout':r.stdout,'stderr':r.stderr}
 assert runs['bounded']['stdout']==runs['full']['stdout'];assert runs['bounded']['stderr']==runs['full']['stderr'];assert runs['bounded']['rows']==runs['full']['rows'];assert (out/'bounded/packets.jsonl').read_bytes()==(out/'full/packets.jsonl').read_bytes();assert runs['bounded']['graph']['cycles']==runs['full']['graph']['cycles']
 observed=[];older=[]
 for r in runs['bounded']['rows']:
  f=r.get('pending_instruction_fetch');phase=r.get('source_fetch_clock_phase')
  if not f or not phase:continue
  assert f['node']>0 and f['owner']>0 and f['bytes']==64
  if f['issued']:assert f['start'] is not None and f['end'] is not None and f['end']>0
  else:assert f['start'] is None and f['end'] is None and not phase['final_graph_completed']
  assert 0<=r['source_fetch_sampled_beats']<8 and phase['source_period']>0 and phase['next_source_edge']>=r['read_cycle']
  assert phase['last_source_commit_edge']==phase['next_source_edge']-phase['source_period']
  if r['source_fetch_final_D_input_present']:assert r['source_fetch_sampled_beats']==7
  if f['end'] is not None and f['end']<r['read_cycle']:
   assert phase['final_graph_completed'] and r['source_fetch_final_D_input_present'] and r['source_fetch_sampled_beats']==7
   assert phase['last_source_commit_edge']<=f['end']<=r['read_cycle']<=phase['next_source_edge'];older.append(r)
  observed.append(r)
 assert observed,'actual source refill observation required';assert all(sha(path)==digest for path,digest in before.items());report={'schema':'iris.Rocket_packet.history_and_fetch_observation_parity.v1','pass':True,'input_sha256':before,'complete_prefix_records_identical':len(runs['bounded']['rows']),'actual_source_fetch_observations':len(observed),'held_final_D_older_than_read_witnesses':len(older),'older_held_D_phase_qualified':bool(older),'stdout_and_guest_counter_bytes_identical':True,'packet_accept_and_redirect_streams_identical':True,'scope':'actual K1 full guest exit and finite direct-response source-Icache observation path; unseen off-edge/CDC carry phase remains unqualified','runs':{k:{x:v for x,v in r.items()if x in['host_seconds','argv']}for k,r in runs.items()},'artifact_sha256':{str(q.relative_to(out)):sha(q)for q in out.rglob('*')if q.is_file()},'timing_certified':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'report_sha256':sha(out/'report.json'),'source_fetch_observations':len(observed)}))
if __name__=='__main__':main()
