#!/usr/bin/env python3
"""Minimal actual-ELF witness for HTIF service delayed by debugger batching."""
import hashlib,json,os,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'build/htif-debugger-wfi-minimal-v2';O.mkdir(exist_ok=False)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
source='''#include "runtime.h"\nstatic unsigned arrived;\nvoid benchmark_main(unsigned h){(void)h;\n __atomic_add_fetch(&arrived,1,__ATOMIC_ACQ_REL);\n while(__atomic_load_n(&arrived,__ATOMIC_ACQUIRE)!=3){}\n#ifdef HTIF_EXIT\n if(h==0){memory_fence();tohost=1;memory_fence();}\n#endif\n for(;;)__asm__ volatile("wfi":::"memory");\n}\n'''
(O/'guest.c').write_text(source);(O/'run.commands').write_text('rs\n')
b=json.load(open(R/'build/full-graph-VME-guest-buffered-v3/build.json'))['argv'];base=json.load(open(R/'build/full-graph-VME-buffered-bounded-v3/run.json'))['argv'];records=[]
for exitrequest in [True,False]:
 d=O/('pending-exit'if exitrequest else'no-host-request');d.mkdir();elf=d/'guest.elf';a=[str(O/'guest.c')if x.endswith('/full-graph-VME-guest-buffered-v3/guest.c')else x for x in b];a[-1]=str(elf)
 if exitrequest:a.insert(1,'-DHTIF_EXIT=1')
 p=subprocess.run(a,capture_output=True);(d/'build.stdout').write_bytes(p.stdout);(d/'build.stderr').write_bytes(p.stderr);assert p.returncode==0
 for debugger in [False,True]:
  e=d/('debug'if debugger else'normal');e.mkdir();argv=[x for x in base if x!='-d'and not x.startswith(('--debug-cmd=','--iris-timing-trace='))][:-1]
  if debugger:argv[1:1]=['-d','--debug-cmd='+str(O/'run.commands')]
  argv+=['--iris-timing-trace='+str(e/'summary.json'),str(elf)];t=time.monotonic();p=subprocess.run(argv,capture_output=True,timeout=30,env=dict(os.environ));dt=time.monotonic()-t
  (e/'stdout').write_bytes(p.stdout);(e/'stderr').write_bytes(p.stderr);good=(p.returncode==0 if exitrequest and not debugger else p.returncode==1 and b'IRIS_TIMING_NO_EVENT'in p.stderr);assert good,(exitrequest,debugger,p.returncode,p.stderr)
  row={'exit_requested':exitrequest,'debugger':debugger,'exit_status':p.returncode,'host_seconds':dt,'argv':argv,'ELF_sha256':sha(elf),'stdout_sha256':sha(e/'stdout'),'stderr_sha256':sha(e/'stderr'),'expected_current_behavior_observed':good};(e/'run.json').write_text(json.dumps(row,indent=2)+'\n');records.append(row)
inputs=[Path(__file__).resolve(),O/'guest.c',O/'run.commands',R/'benchmarks/runtime.c',R/'benchmarks/runtime.h',R/'benchmarks/start.S',R/'benchmarks/link.ld',Path(base[0]),R/'build/empirical-fast-frozen-28a0a52b/spike',R/'build/empirical-fast-frozen-28a0a52b/libsifive_uart.so',R/'build/full-graph-VME-buffered-bounded-v3/job.fixture',R/'pipeline/riscv-isa-sim-read-overlap-response-v2/riscv/interactive.cc',R/'pipeline/riscv-isa-sim-read-overlap-response-v2/riscv/iris_timing_adapter.cc',R/'pipeline/riscv-isa-sim-read-overlap-response-v2/fesvr/htif.cc']
r={'schema':'iris.HTIF_debugger_WFI_gap_reproduction.v1','pass':True,'runs':records,'scope':'actual three-hart ELF; no native edits; known tohost1 followed by all-hart WFI','finding':'debugger interactive_run repeats step(1) until INTERLEAVE before returning to host; accepted exit is pending but another step reaches no-event guard before FESVR polls','nondebug_exit_passes':True,'unknown_no_host_WFI_still_refuses':True,'fix_implemented':False,'full_numeric_workload_qualification':False,'hardware_contacted':False,'global_heldout_timings_consumed':False,'input_sha256':{str(p):sha(p)for p in inputs}}
(O/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(sha(O/'report.json'))
