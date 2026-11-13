#!/usr/bin/env python3
"""Exercise two pending numeric owners at a real CLINT edge under source fetch."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--uart',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);base=json.loads((ROOT/'build/empirical-async-two-metrics-v1/selected/report.json').read_text())['argv'];all_two=set();cases=[];original=ROOT/'build/empirical-async-two-first-v1/two.fixture'
 for extra in range(8):
  for kind in['unrolled','shifted']:
   d=out/f'latency{extra}-{kind}';d.mkdir();elf=ROOT/f'build/empirical-async-two-irq-{kind}-guest-v1/guest.elf';fixture=d/'fixture';text=original.read_text()+'\nshuttle_frontend source-C++-M-mode 1 16\nicache_service empirical-shared-L2 1 1 explicit-synthetic-IRQ-guard\nempirical_rocket_packets source-IBuf-demand-4B-v1\n'
   for h in range(3):text+=f'resource empirical.IRQ-vector{h} 1\nempirical_family {h} rvv.integer empirical.IRQ-vector{h} {extra} 0 1 SYNTHETIC_IRQ_GUARD '+('0'*64)+' core_cycles\n'
   fixture.write_text(text);argv=[x for x in base if not x.startswith(('--iris-timing-fixture=','--iris-timing-trace='))];argv[0]=str(a.binary.resolve());argv=['--extlib='+str(a.uart.resolve())if x.startswith('--extlib=')else x for x in argv];argv[-1]=str(elf);argv[-1:-1]=['--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(d/'summary.json')];t=time.monotonic();r=subprocess.run(argv,capture_output=True,env=dict(os.environ,IRIS_EMPIRICAL_ASYNC_TRACE=str(d/'async.jsonl')),timeout=90);elapsed=time.monotonic()-t;(d/'stdout').write_bytes(r.stdout);(d/'stderr').write_bytes(r.stderr);assert r.returncode==0,(extra,kind,r.stderr.decode());numeric=[list(map(int,x.split()[1:]))for x in r.stdout.decode().splitlines()if x.startswith('IRIS_ASYNC_TWO_IRQ ')];assert len(numeric)==3 and all(x[-2:]==[1,1027]for x in numeric)
   events=[json.loads(x)for x in(d/'async.jsonl').read_text().splitlines()];begins={(x['hart'],x['backend_node']):x for x in events if x['event']=='begin'};pubs={(x['hart'],x['backend_node']):x for x in events if x['event']=='publish'};cancels={(x['hart'],x['backend_node']):x for x in events if x['event']=='cancel'};assert set(begins)==set(pubs)|set(cancels)and not set(pubs)&set(cancels)
   for key,b in begins.items():
    if key not in pubs:continue
    assert pubs[key]['cycle']>=b['com']and pubs[key]['cycle']>b['ex']
    if'prior_backend_node'in b:
     prior=(b['hart'],b['prior_backend_node']);assert b['prior_com']<=b['ex']and b['prior_backend_end']<=b['ex']and pubs[prior]['cycle']<=b['ex']
   two=sorted({x['hart']for x in events if x['event']=='interrupt_pre_completion'and x['pending']==2});all_two.update(two);summary=json.loads((d/'summary.json').read_text());assert summary['async_owner_limit']==2 and not any(summary['pending_async_backends']);case={'argv':argv,'exit_status':r.returncode,'host_seconds':elapsed,'two_pending_before_completion_harts':two,'begin_count':len(begins),'publish_count':len(pubs),'input_sha256':{str(x):sha(x)for x in[a.binary.resolve(),a.uart.resolve(),elf,fixture,Path(__file__).resolve()]}};(d/'report.json').write_text(json.dumps(case,indent=2)+'\n');cases.append(str(d/'report.json'));print(extra,kind,two,flush=True)
  if all_two=={0,1,2}:break
 assert all_two=={0,1,2},all_two
 report={'schema':'iris.source_frontend.two_owner_IRQ_phase_guards.v1','pass':True,'all3_two_pending_on_actual_timer_transition':True,'binary_sha256':sha(a.binary),'uart_sha256':sha(a.uart),'synthetic_fixture_scope':'explicit backend-latency phase sweep, no calibration or FPGA fit; original source/frontend/CSR/IRQ policies unchanged','reports':{x:sha(x)for x in cases},'timing_certified':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
