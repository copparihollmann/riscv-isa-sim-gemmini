#!/usr/bin/env python3
"""Run the actual finite K1 ELF with live CPU→source Saturn/physical publication."""
import argparse,hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from spike.run_functional import command
from pipeline.saturn_live_manifest import generate
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--binary',type=Path,default=ROOT/'build/spike-saturn-live-v1/spike');p.add_argument('--seed',type=int,default=1);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);binary=a.binary.resolve();plugin=binary.with_name('libsifive_uart.so');elf=ROOT/'build/saturn-timing-live-guest-v1/guest.elf';admission=elf.with_name('admission.json');manifest=out/'native.manifest';manifest.write_text(generate(elf,admission))
 fixture=out/'explicit.fixture';lines=[]
 for line in(ROOT/'pipeline/rocket-source-synthetic.fixture').read_text().splitlines():
  if line.startswith('base_hz '):line='base_hz 500000000'
  elif line.startswith('rtc_divider '):line='rtc_divider 1000'
  elif line.startswith('max_cycles '):line='max_cycles 5000000'
  elif line.startswith('hart '):line=' '.join([*line.split()[:2],'1','source'])
  elif line.startswith('shuttle_frontend '):line=f'shuttle_frontend saved-rtl-M-mode {a.seed} 16'
  lines.append(line)
 lines.append('saturn_live finite-integer-K1-hart0 '+str(manifest));fixture.write_text('\n'.join(lines)+'\n');graph=out/'graph.json';argv=command(binary,elf);argv=['--extlib='+str(plugin)if x.startswith('--extlib=')else x for x in argv];argv[-1:-1]=['--iris-bootrom='+str(ROOT/'board/evidence/bootrom.rv64.img'),'--dtb='+str(ROOT/'board/build/iris.dtb'),'--iris-timing-fixture='+str(fixture),'--iris-timing-trace='+str(graph)]
 files=[Path(__file__).resolve(),ROOT/'pipeline/saturn_live_manifest.py',ROOT/'pipeline/rocket-source-synthetic.fixture',ROOT/'spike/run_functional.py',elf,admission,binary,plugin,ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb'];before={str(x):sha(x)for x in files};start=time.perf_counter();timed=False
 try:r=subprocess.run(argv,text=True,capture_output=True,timeout=180,env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH']));stdout,stderr,status=r.stdout,r.stderr,r.returncode
 except subprocess.TimeoutExpired as e:stdout=e.stdout or b'';stderr=e.stderr or b'';stdout=stdout.decode()if isinstance(stdout,bytes)else stdout;stderr=stderr.decode()if isinstance(stderr,bytes)else stderr;status=None;timed=True
 (out/'stdout').write_text(stdout);(out/'stderr').write_text(stderr);passed=status==0 and'IRIS_SATURN_LIVE_VALUES 8 6 64'in stdout and'IRIS_SATURN_LIVE_DONE 3'in stdout;findings={}
 if graph.exists():
  g=json.loads(graph.read_text());s=g.get('saturn_live',{});findings=dict(cycles=g['cycles'],retired=g['retired_instructions'],saturn=s);macs=[e for e in g['events']if e['name']=='INT8_MAC_edge'];overlaps=[]
  for m in macs:
   scalar=[e for e in g['events']if e['hart']==0 and e['resource']in('shuttle0.EX','shuttle0.MEM_ALU')and e['start']<=m['start']<e['end']and e['completed']and not e.get('squashed')];overlaps.append(dict(tick=m['start'],MACs=m['macs'],scalar_nodes=[e['id']for e in scalar],scalar_resources=[e['resource']for e in scalar]))
  findings['source_MAC_scalar_overlap']=overlaps
  passed &= len(macs)==4 and sum(m['macs']for m in macs)==1024 and all(x['scalar_nodes']for x in overlaps)and s.get('source_events',{}).get('COM_numeric_state_unchanged')==9 and s.get('source_accepted_commands')==9 and s.get('architecturally_retired_commands')==9 and not s.get('front_command_pending',True) and not any(s.get('pending_ownership',{}).values()) and s.get('private_intents_retained')==0
 if before!={str(x):sha(x)for x in files}:raise ValueError('live native gate inputs changed')
 report=dict(schema='iris.saturn.actual_native_CPU_unit_K1.v1',status='passed_actual_ELF_live_source_Saturn_numeric_publication'if passed else'preserved_failed_actual_ELF_live_Saturn_attempt',argv=argv,exit_status=status,timed_out=timed,input_sha256=before,binary_sha256=sha(binary),uart_sha256=sha(plugin),fixture_sha256=sha(fixture),manifest_sha256=sha(manifest),graph_sha256=sha(graph)if graph.exists()else None,stdout_sha256=sha(out/'stdout'),stderr_sha256=sha(out/'stderr'),host_seconds=time.perf_counter()-start,findings=findings,shared_memory_scope='explicit functional fixture; source scalar caches disabled',active_unit_hart=0,physical_harts=3,full_three_hart_source_memory=False,full_knownness_certified=False,timing_certified=False,held_out_2pct=False);(out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],host_seconds=report['host_seconds'],stdout=stdout[-1500:],stderr=stderr[-2000:],findings=findings)),flush=True);raise SystemExit(0if passed else 1)
if __name__=='__main__':main()
