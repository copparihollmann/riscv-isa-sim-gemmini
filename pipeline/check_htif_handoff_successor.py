#!/usr/bin/env python3
"""Executed-ELF proof of known HTIF service at a debugger step boundary."""
import argparse,hashlib,json,os,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main(a):
 o=a.output.resolve();o.mkdir(exist_ok=False,parents=True);P=R/'build/empirical-read-overlap-response-frozen-7bd58b4f';rows=[]
 def run(label,argv,b,u,success):
  d=o/label;d.mkdir();args=[str(b)]+[('--extlib='+str(u)if x.startswith('--extlib=')else'--iris-timing-trace='+str(d/'summary.json')if x.startswith('--iris-timing-trace=')else x)for x in argv[1:]]
  t=time.monotonic();p=subprocess.run(args,capture_output=True,timeout=90,env=dict(os.environ,IRIS_EMPIRICAL_FEATURES=str(d/'features.jsonl')));dt=time.monotonic()-t;(d/'stdout').write_bytes(p.stdout);(d/'stderr').write_bytes(p.stderr);j={'label':label,'argv':args,'exit_status':p.returncode,'host_seconds':dt};(d/'run.json').write_text(json.dumps(j,indent=2)+'\n');assert(p.returncode==0)==success,(label,p.returncode,p.stderr);rows.append(j);return d
 # Same minimal ELFs: only whether a known tohost request exists differs.
 for kind in ['pending-exit','no-host-request']:
  for debug in ['normal','debug']:
   argv=json.load(open(R/'build/htif-debugger-wfi-minimal-v2'/kind/debug/'run.json'))['argv'];oldsuccess=kind=='pending-exit'and debug=='normal';newsuccess=kind=='pending-exit'
   before=run('parent-'+kind+'-'+debug,argv,P/'spike',P/'libsifive_uart.so',oldsuccess);after=run('new-'+kind+'-'+debug,argv,a.binary,a.uart,newsuccess)
   if kind=='no-host-request':assert(before/'stderr').read_bytes()==(after/'stderr').read_bytes()and b'IRIS_TIMING_NO_EVENT'in(after/'stderr').read_bytes()
 # Deliberately unknown RAM load transports an unknown payload to the aligned
 # tohost word. It must still fail as an observation or unknown-WFI refusal.
 d=o/'unknown-guest';d.mkdir();s=(R/'build/htif-debugger-wfi-minimal-v2/guest.c').read_text();s=s.replace('tohost=1;', '__asm__ volatile("li t0,0x84000000;ld t1,0(t0);la t0,tohost;sd t1,0(t0)":::"t0","t1","memory");');(d/'guest.c').write_text(s)
 cc=json.load(open(R/'build/full-graph-VME-guest-buffered-v3/build.json'))['argv'];cc=[str(d/'guest.c')if x.endswith('/full-graph-VME-guest-buffered-v3/guest.c')else x for x in cc];cc[-1]=str(d/'guest.elf');cc.insert(1,'-DHTIF_EXIT=1');p=subprocess.run(cc,capture_output=True);(d/'build.stdout').write_bytes(p.stdout);(d/'build.stderr').write_bytes(p.stderr);assert p.returncode==0
 for debug in ['normal','debug']:
  argv=json.load(open(R/'build/htif-debugger-wfi-minimal-v2/pending-exit'/debug/'run.json'))['argv'];argv[-1]=str(d/'guest.elf');before=run('parent-unknown-'+debug,argv,P/'spike',P/'libsifive_uart.so',False);after=run('new-unknown-'+debug,argv,a.binary,a.uart,False);assert(before/'stderr').read_bytes()==(after/'stderr').read_bytes();assert any(x in(after/'stderr').read_bytes()for x in[b'IRIS_UNDEFINED',b'IRIS_TIMING_NO_EVENT'])
 # Original six-ROI144word ELF remains byte-identical. Run with and without
 # its exact readback debugger commands; compare pre-host numeric/counter data.
 src=R/'build/full-graph-VME-buffered-bounded-v3/run.json';base=json.load(src.open())['argv']
 for debug in [False,True]:
  argv=base if debug else[x for x in base if x!='-d'and not x.startswith('--debug-cmd=')];label='fullgraph-'+('debug'if debug else'normal');before=run('parent-'+label,argv,P/'spike',P/'libsifive_uart.so',not debug);after=run('new-'+label,argv,a.binary,a.uart,True)
  for f in ['stdout','features.jsonl']:assert(before/f).read_bytes()==(after/f).read_bytes(),(label,f)
  if debug:
   old=(before/'stderr').read_bytes();new=(after/'stderr').read_bytes();assert old==new+b'IRIS_TIMING_NO_EVENT: all harts parked without a modeled wakeup\n';commands=next(x.split('=',1)[1]for x in argv if x.startswith('--debug-cmd='));assert new.count(b'0x')==sum(l.startswith('mem ')for l in Path(commands).read_text().splitlines())
  else:assert(before/'stderr').read_bytes()==(after/'stderr').read_bytes()==b''
 inputs=[Path(__file__).resolve(),a.binary,a.uart,P/'manifest.json',P/'verification.json',R/'build/htif-debugger-wfi-proof-v1/report.json',R/'build/full-graph-VME-guest-buffered-v3/profile-vme.elf',R/'build/htif-debugger-wfi-fix-proposal-v1/known-pending-host-yield-on-V8.patch']
 j={'schema':'iris.HTIF_known_pending_handoff_native_proof.v1','pass':True,'runs':rows,'minimal_known_pending_exit_debug_normal_pass':True,'no_host_and_unknown_payload_strict_refusals':True,'original_fullgraph_v3_debug_normal_exit':True,'normal_stdout_CSR_prefix_byte_parity':True,'original_debugger_readback_all_words_unchanged':True,'cost_ISA_memory_or_cache_policy_changed':False,'native_binary_sha256':sha(a.binary),'uart_sha256':sha(a.uart),'hardware_contacted':False,'global_heldout_timings_consumed':False,'input_sha256':{str(p):sha(p)for p in inputs}};(o/'report.json').write_text(json.dumps(j,indent=2)+'\n');print(sha(o/'report.json'))
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--uart',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
