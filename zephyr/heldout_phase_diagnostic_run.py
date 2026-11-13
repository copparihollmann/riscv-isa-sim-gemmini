#!/usr/bin/env python3
import argparse,hashlib,json,os,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R));sys.path.insert(0,str(R/'firesim'));sys.path.insert(0,str(R/'zephyr'))
from spike.run_functional import command,symbols
from batch_runner import parse_regions
from freeze_heldouts import output_hash
from compiler_pipeline import producer_golden
from uart_profiles import check_report

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def validate(text,m,cases,goldens):
 lines=text.splitlines();get=lambda tag:[json.loads(x.split(' ',1)[1])for x in lines if x.startswith(tag+' ')]
 if get('IRIS_DIAG_TIMEOUT')or 'IRIS_HELDOUT_FATAL 'in text:raise ValueError('Diagnostic timeout/fatal is not normal completion')
 if get('IRIS_DIAG_WATCHDOG')!=[dict(hart=1,no_progress_ms=5000)]or get('IRIS_DIAG_DONE')!=[dict(phases=2,failed=0)]or get('IRIS_BATCH_DONE')!=[dict(failed=0,cases=32,regions=32,trials=5)]:raise ValueError('Actual watchdog/hart/terminal geometry')
 phases=[{k:v for k,v in p.items()if k in ['phase','op','workers','kind']}for p in m['phases']]
 if get('IRIS_HELDOUT_PHASE')!=phases:raise ValueError('Two real shipped/twin phases required')
 rows=parse_regions(text,cases,m['ELF_sha256'],None,True,True)
 if len(rows)!=32:raise ValueError('Complete32 regions')
 outputs=get('IRIS_HELDOUT_RESULT')
 if len(outputs)!=30:raise ValueError('All30 compact numerical results')
 for index,result in enumerate(outputs):
  phase,job=divmod(index,15);g=goldens[0][job%3];want=dict(phase=phase,job=job,encoding='checked-word-hashes-v1',word_count=4096,accumulator_checksum=output_hash(g['accumulator_u32']),w8a8_checksum=output_hash(g['w8a8_f32_words']),mismatching_int32_words=0,mismatching_w8a8_words=0)
  if result!=want:raise ValueError('Independent full-output hash mismatch')
 producers=get('IRIS_HELDOUT_PRODUCER')
 if len(producers)!=2:raise ValueError('Both real hart2 producers')
 for phase,p in enumerate(producers):
  if p['phase']!=phase or p['hart']!=2 or p['jobs']!=15 or p['vector_checksum']!=producer_golden(5)or p['vme_refused']is not True or len(p['overlap_masks'])!=15 or not any(p['overlap_masks'][:2]):raise ValueError('Producer RVV/refusal/overlap')
 for row in rows:
  if row['cycles']<=0 or row['instret_delta']<=0:raise ValueError('Counter progress')
 return dict(phases=2,regions=32,jobs=30,embedded_full_int32_words=122880,embedded_full_W8A8_words=122880,all_compact_word_hashes_independently_match=True,harts=[0,1,2],watchdog_hart=1,watchdog_no_progress_ms=5000,uart_readback=check_report(lines,'ethan-firesim'))
def main():
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,default=0);p.add_argument('--timeout',type=int,default=300);a=p.parse_args();b=a.build.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);mp=b/'manifest.json';m=json.loads(mp.read_text());elf=Path(m['ELF']);assert sha(elf)==m['ELF_sha256'];native=R/'build/combined-frozen-35901887/spike';uart=native.with_name('libsifive_uart.so');rom=R/'board/evidence/bootrom.rv64.img';dtb=R/'board/build/iris.dtb';paths=[Path(__file__),mp,elf,native,uart,rom,dtb,b/'cases.json',b/'golden.json'];ident=dict(m['input_sha256']);ident.update({str(p):sha(p)for p in paths});assert all(sha(p)==d for p,d in ident.items())
 argv=command(native,elf);argv=['--extlib='+str(uart)if x.startswith('--extlib=')else x for x in argv];argv[-1:-1]=['--iris-bootrom='+str(rom),'--dtb='+str(dtb),'--iris-schedule-seed='+str(a.seed)];env=dict(os.environ,IRIS_FATAL_PCS=','.join(hex(v)for k,v in symbols(elf).items()if k in ['z_fatal_error','z_riscv_fatal_error','k_sys_fatal_error_handler','arch_system_halt','abort']));start=time.monotonic();code=None;timed=False
 with(out/'stdout').open('wb')as stdout,(out/'stderr').open('wb')as stderr:
  try:code=subprocess.run(argv,env=env,stdout=stdout,stderr=stderr,timeout=a.timeout).returncode
  except subprocess.TimeoutExpired:timed=True
 record=dict(schema='iris.phase_handoff_diagnostic_functional_run.v1',**{'pass':False},seed=a.seed,argv=argv,exit_status=code,timed_out=timed,host_seconds=time.monotonic()-start,ELF_sha256=sha(elf),native_sha256=sha(native),UART_sha256=sha(uart),force_stall_negative=m['force_stall_negative'],input_sha256=ident,stdout_sha256=sha(out/'stdout'),stderr_sha256=sha(out/'stderr'),hardware_contacted=False,fitting_allowed=False,global_v6_reference_timing_labels_consumed=False)
 try:
  text=(out/'stdout').read_text();cases=json.loads((b/'cases.json').read_text());gold=json.loads((b/'golden.json').read_text())
  if m['force_stall_negative']:
   events=[json.loads(x.split(' ',1)[1])for x in text.splitlines()if x.startswith('IRIS_DIAG_TIMEOUT ')];assert not timed and code==1 and len(events)==1;event=events[0];assert event['watchdog_hart']==1 and event['diagnostic_not_normal_completion']is True and ((event['main']>>24)&15)==1 and(event['main']&65535)==1;assert 'IRIS_DIAG_DONE 'not in text;record['proof']=dict(forced_phase1_stall_detected=True,nonzero_HTIF_exit=True,mailboxes=event,normal_completion=False)
  else:
   if timed or code!=0:raise ValueError('No normal zero-status completion')
   record['proof']=validate(text,m,cases,gold)
  if any(sha(p)!=d for p,d in ident.items()):raise ValueError('Input changed')
  record['pass']=True
 except(ValueError,AssertionError,KeyError,TypeError)as error:record['error']=str(error)or'Negative watchdog control failed'
 (out/'report.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({k:record.get(k)for k in['pass','host_seconds','error','proof']}));return 0 if record['pass']else 1
if __name__=='__main__':raise SystemExit(main())
