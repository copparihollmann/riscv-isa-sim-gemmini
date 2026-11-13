#!/usr/bin/env python3
"""Execute the combined optional pipelines with forced deferred-store kills."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--uart',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 source=ROOT/'timing/empirical_fadd_store_interaction_guest.c';args=json.loads((ROOT/'build/empirical-owned-store-guest-v2/build.json').read_text())['argv'];args=[str(source)if x==str(ROOT/'timing/empirical_owned_store_guest.c')else x for x in args];args[-1]=str(out/'guest.elf');r=subprocess.run(args,capture_output=True);(out/'build.stdout').write_bytes(r.stdout);(out/'build.stderr').write_bytes(r.stderr);assert r.returncode==0,r.stderr
 base=json.loads((ROOT/'build/rocket-packet-native-first-v1/report.json').read_text())['argv'];runs={};details={}
 for history in ('bounded','full'):
  d=out/history;d.mkdir();text=(ROOT/'build/rocket-packet-native-first-v1/first.fixture').read_text().replace('unfitted-bounded-v1 bounded','unfitted-bounded-v1 '+history)
  text+='\nempirical_store_front owned-dirty-L1-COM-v1\nempirical_scalar_fadd source-HSD-pipeline-v1\nempirical_vme_work source-shape-subtiles-v1\n'
  for h in range(3):text+=f'resource empirical.interaction-store{h} 1\nempirical_family {h} memory.DRAM.store empirical.interaction-store{h} 20 0 1 SYNTHETIC_CROSS_FEATURE '+('0'*64)+' core_cycles\n'
  f=d/'fixture';f.write_text(text);argv=[x for x in base if not x.startswith(('--iris-timing-fixture=','--iris-timing-trace='))];argv[0]=str(a.binary.resolve());argv=['--extlib='+str(a.uart.resolve())if x.startswith('--extlib=')else x for x in argv];argv[-1]=str(out/'guest.elf');argv[-1:-1]=['--iris-timing-fixture='+str(f),'--iris-timing-trace='+str(d/'graph.json')];t=time.monotonic();r=subprocess.run(argv,capture_output=True,timeout=120,env=dict(os.environ,IRIS_EMPIRICAL_ASYNC_TRACE=str(d/'async.jsonl'),IRIS_EMPIRICAL_FEATURES=str(d/'features.jsonl')));elapsed=time.monotonic()-t;(d/'stdout').write_bytes(r.stdout);(d/'stderr').write_bytes(r.stderr);assert r.returncode==0,(history,r.stderr)
  numeric=[list(map(int,x.split()[1:]))for x in r.stdout.decode().splitlines()if x.startswith('IRIS_FADD_STORE ')];assert sorted(numeric)==[[h,0,0x43010000,227,1,0]for h in range(3)],numeric
  graph=json.loads((d/'graph.json').read_text());trace=[json.loads(x)for x in(d/'async.jsonl').read_text().splitlines()];fp=graph['scalar_fadd_metrics'];stores=graph['owned_store_front']['per_hart'];assert all(m['published']==128 and m['accepted']>128 and m['killed']>0 and not m['pending']for m in fp),fp;assert all(m['positive_cost_deferrals']>0 and not m['pending_accepted_response']for m in stores),stores
  ex={(e['hart'],e['instruction']):e for e in trace if e['event']=='scalar_fadd_EX'};pub={(e['hart'],e['instruction']):e for e in trace if e['event']=='scalar_fadd_FPR_WRITE'};com={(e['hart'],e['instruction']):e for e in trace if e['event']=='scalar_fadd_COM'};killed=ex.keys()-pub.keys();assert all(any(h==hart for h,_ in killed)for hart in range(3))
  for key,e in pub.items():assert key in com and e['cycle']==ex[key]['write']>com[key]['cycle']
  for key in killed:assert key not in com
  if history=='full':
   nodes={n['id']:n for n in graph['events']}
   assert all(nodes[ex[key]['node']]['completed']and not nodes[ex[key]['node']].get('cancelled',False)for key in killed)
  details[history]={'host_seconds':elapsed,'killed_accepted_FP_owners':len(killed),'scalar_fadd_metrics':fp,'store_metrics':stores,'architectural_retired':graph['retired_instructions'],'simulated_MIPS':sum(graph['retired_instructions'])/elapsed/1e6};runs[history]={'stdout':r.stdout,'stderr':r.stderr,'prefix':(d/'features.jsonl').read_bytes(),'trace':(d/'async.jsonl').read_bytes(),'cycles':graph['cycles'],'retired':graph['retired_instructions']};(d/'run.json').write_text(json.dumps({'pass':True,'argv':argv,**details[history]},indent=2)+'\n')
 assert runs['bounded']==runs['full'],'combined mode changes with history retention'
 report={'schema':'iris.scalar_FADD_owned_store_interaction.v1','pass':True,'binary_sha256':sha(a.binary),'uart_sha256':sha(a.uart),'source_sha256':sha(source),'checker_sha256':sha(__file__),'ELF_sha256':sha(out/'guest.elf'),'build_argv':args,'independent_goldens':'128 exact single-precision adds:129.0, final SD227, IRQ1, FFLAGS0 on all3','bounded_full_guest_counter_prefix_trace_byte_parity':True,'synthetic_costs_only':True,'details':details,'timing_certified':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(sha(out/'report.json'))
if __name__=='__main__':main()
