#!/usr/bin/env python3
import argparse,hashlib,json,os,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R));sys.path.insert(0,str(R/'firesim'));sys.path.insert(0,str(R/'zephyr'))
from spike.run_functional import command,symbols
from flush_frontier_validate import normal as validate,timeout as timeout_evidence


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--variant',choices=['enabled','disabled'],required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,default=0);p.add_argument('--timeout',type=int,default=300);a=p.parse_args();b=a.build.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);m=json.loads((b/'manifest.json').read_text());elf=Path(m['variants'][a.variant]['path']);assert sha(elf)==m['variants'][a.variant]['sha256'];native=R/'build/combined-frozen-35901887/spike';uart=native.with_name('libsifive_uart.so');rom=R/'board/evidence/bootrom.rv64.img';dtb=R/'board/build/iris.dtb';paths=[Path(__file__),Path(__file__).with_name('flush_frontier_validate.py'),Path(__file__).with_name('heldout_phase_diagnostic_validate.py'),b/'manifest.json',b/'pair-proof.json',elf,native,uart,rom,dtb,b/'cases.json',b/'golden.json'];inputs=dict(m['input_sha256']);inputs.update({str(p):sha(p)for p in paths});assert all(sha(p)==d for p,d in inputs.items());argv=command(native,elf);argv=['--extlib='+str(uart)if x.startswith('--extlib=')else x for x in argv];argv[-1:-1]=['--iris-bootrom='+str(rom),'--dtb='+str(dtb),'--iris-schedule-seed='+str(a.seed)];env=dict(os.environ,IRIS_FATAL_PCS=','.join(hex(v)for k,v in symbols(elf).items()if k in ['z_fatal_error','z_riscv_fatal_error','k_sys_fatal_error_handler','arch_system_halt','abort']));code=None;timed=False;start=time.monotonic()
 with(out/'stdout').open('wb')as stdout,(out/'stderr').open('wb')as stderr:
  try:code=subprocess.run(argv,env=env,stdout=stdout,stderr=stderr,timeout=a.timeout).returncode
  except subprocess.TimeoutExpired:timed=True
 r=dict(schema='iris.flush_frontier_functional_run.v1',**{'pass':False},variant=a.variant,seed=a.seed,argv=argv,ELF_sha256=sha(elf),native_sha256=sha(native),UART_sha256=sha(uart),exit_status=code,timed_out=timed,host_seconds=time.monotonic()-start,force_stall_negative=m['force_stall_negative'],input_sha256=inputs,stdout_sha256=sha(out/'stdout'),stderr_sha256=sha(out/'stderr'),hardware_contacted=False,fitting_allowed=False,global_v6_reference_timing_labels_consumed=False)
 try:
  text=(out/'stdout').read_text()
  if m['force_stall_negative']:
   if a.variant=='enabled':
    assert not timed and code==1;r['proof']=timeout_evidence(text,forced=True)
   else:
    assert timed and code is None and 'IRIS_FLUSH_ONESHOT 'not in text and 'IRIS_DIAG_DONE 'not in text and '"phase":0' in text;r['proof']=dict(disabled_watchdog_does_not_emit_target_timeout_in_bounded_forced_stall=True,host_bound_seconds=a.timeout,normal_completion=False,no_infinite_stall_claim=True)
  else:
   assert not timed and code==0;meta=dict(m,ELF_sha256=sha(elf));r['proof']=validate(text,meta,json.loads((b/'cases.json').read_text()),json.loads((b/'golden.json').read_text()),a.variant=='enabled')
  assert all(sha(p)==d for p,d in inputs.items());r['pass']=True
 except(ValueError,TypeError,KeyError,AssertionError)as e:r['error']=str(e)or'Counterfactual/normal outcome differs'
 (out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r.get(k)for k in['pass','variant','host_seconds','proof','error']}));return 0 if r['pass']else 1
if __name__=='__main__':raise SystemExit(main())
