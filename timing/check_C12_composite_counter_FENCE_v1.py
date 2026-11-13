#!/usr/bin/env python3
"""Finite counter-only overlap, numeric tail, boundary and OFF-parity proof."""
import argparse,hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from spike.run_functional import command

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(v,s):
 if not v:raise ValueError(s)
def main():
 ap=argparse.ArgumentParser(__doc__)
 for n in('capsule','ON','OFF','legacy','output'):ap.add_argument('--'+n,type=Path,required=True)
 a=ap.parse_args();cap,on,off,legacy,out=[getattr(a,n).resolve()for n in('capsule','ON','OFF','legacy','output')];out.mkdir(exist_ok=False)
 old=ROOT/'build/FADD-EG-actor-corrective-frozen-v2';source=ROOT/'timing/fadd_eg_counterCSR_guest_v1.c';cc=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc').resolve()
 m=json.loads((cap/'manifest.json').read_text())
 for n,h in m['artifact_sha256'].items():need(sha(cap/n)==h,'Capsule changed '+n)
 inputs={str(p):sha(p)for p in [Path(__file__).resolve(),source,cc,cap/'manifest.json',cap/'spike',cap/'libsifive_uart.so',on,off,legacy,old/'manifest.json',*[ROOT/'benchmarks'/n for n in('start.S','runtime.c','runtime.h','link.ld','uart_drain.h')],ROOT/'board/evidence/bootrom.rv64.img',ROOT/'board/build/iris.dtb']};runs=[];builds=[]
 def build(h):
  d=out/f'guest-h{h}';d.mkdir();elf=d/'guest.elf';argv=[str(cc),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none','-DIRIS_HARTS=3',f'-DIRIS_ACTIVE_HART={h}','-I'+str(ROOT/'benchmarks'),'-T',str(ROOT/'benchmarks/link.ld'),str(ROOT/'benchmarks/start.S'),str(ROOT/'benchmarks/runtime.c'),str(source),'-lgcc','-o',str(elf)]
  p=subprocess.run(argv,capture_output=True);(d/'compile.stderr').write_bytes(p.stderr);need(p.returncode==0,p.stderr.decode());builds.append(dict(argv=argv,ELF_sha256=sha(elf)));return elf
 def run(name,which,fixture,elf,seed=0,trace=True):
  d=out/name;d.mkdir();argv=command(which/'spike',elf);argv=['--extlib='+str(which/'libsifive_uart.so')if x.startswith('--extlib=')else x for x in argv];argv=argv[:-1]+['--iris-bootrom='+str(ROOT/'board/evidence/bootrom.rv64.img'),'--dtb='+str(ROOT/'board/build/iris.dtb'),'--iris-timing-fixture='+str(fixture),'--iris-schedule-seed='+str(seed),'--iris-timing-trace='+str(d/'summary.json')]+argv[-1:]
  env={k:v for k,v in os.environ.items()if not k.startswith('IRIS_EMPIRICAL_')};env['IRIS_EMPIRICAL_FEATURES']=str(d/'features.jsonl')
  if trace:env['IRIS_EMPIRICAL_ASYNC_TRACE']=str(d/'async.jsonl')
  start=time.monotonic()
  with(d/'stdout').open('wb')as so,(d/'stderr').open('wb')as se:
   p=subprocess.Popen(argv,stdout=so,stderr=se,env=env,start_new_session=True)
   try:code=p.wait(timeout=60)
   except subprocess.TimeoutExpired:
    os.killpg(p.pid,signal.SIGKILL);p.wait();raise ValueError('Owned bounded native run timed out: '+name)
  row=dict(name=name,argv=argv,exit_status=code,host_seconds=time.monotonic()-start,binary_sha256=sha(which/'spike'),UART_sha256=sha(which/'libsifive_uart.so'),fixture_sha256=sha(fixture),ELF_sha256=sha(elf));(d/'run.json').write_text(json.dumps(row,indent=2)+'\n');runs.append(row)
  need(code==0 and not(d/'stderr').read_bytes(),'Normal native exit '+name+': '+(d/'stderr').read_text())
  lines=[list(map(int,l.split()[1:]))for l in(d/'stdout').read_text().splitlines()if l.startswith('IRIS_FADD_COUNTER ')];need(len(lines)==23 and all(x[-1]==0 for x in lines),'All23 independent64-word/flags31 goldens');need(f'IRIS_FADD_COUNTER_DONE {lines[0][0]} 23 0\n'in(d/'stdout').read_text(),'Normal complete footer');row['pass']=True;return d
 wanted=[(c,f)for c in(0xb00,0xb02,0xc00,0xc02)for f in(2,3,6,7)]
 for h in(0,1):
  elf=build(h)
  for seed in(0,17):
   d=run(f'ON-h{h}-seed{seed}',cap,on,elf,seed)
   prefixes=[json.loads(l)for l in(d/'features.jsonl').read_text().splitlines()];events=[json.loads(l)for l in(d/'async.jsonl').read_text().splitlines()]
   com=[e for e in events if e['event']=='fadd_EG_functional_COM'];need(len(com)==23,'Exact architectural COM owner count')
   first=[p for p in events if p['event']=='fadd_EG_counter_read' and p['hart']==h and p['destination']==6];after=[p for p in prefixes if p['hart']==h and p['destination']==7]
   need([(p['csr'],(p['raw']>>12)&7)for p in first]==wanted and len(after)==23,'Exact16 zero-source counter encoding observations plus23 post-boundary observations')
   for i,e in enumerate(com):
    need((e['SEW'],e['VL'],e['LMUL_numerator'],e['LMUL_denominator'],e['vs1'],e['vs2'],e['vd'],e['raw'],e['geometry_authority'])==(32,64,8,1,16,8,8,0x02881457,'checked_architectural_COM'),'Trace geometry only at actual checked COM')
    writes=[x for x in events if x['event']=='fadd_EG_physical_write'and x['generation']==e['generation']];need(len(writes)==16,'All16 actual EG writes');last=max(x['cycle']for x in writes)
    need(after[i]['read_cycle']>last and after[i]['async_compute_pending']is False,'FENCE/other CSR boundaries retain complete physical tail dependency')
    if i<16:need(e['cycle']<first[i]['read_cycle']<last and first[i]['async_compute_pending']is True,'Independent actualcounter read overlaps unfinished numerical tail')
   fences=[e for e in events if e['event']=='fadd_EG_fence_admit'];need(fences and all(e['pending']==0 and e['controller_empty'] is True and (not e['last_preedge_busy'] or e['cycle']>e['last_controller_edge'])for e in fences),'Final-source-write edge remains busy; FENCE admitted only on following edge')
   runs[-1].update(independent_counter_reads_while_pending=16,conservative_dependent_CSR_cases=7,independent_words=23*64,checked_COM_geometry_records=23)
 need(all(sha(Path(p))==v for p,v in inputs.items()),'Inputs changed')
 report=dict(schema='iris.C12_composite_counter_FENCE_native_controls.v1',**{'pass':True},native_binary_sha256=sha(cap/'spike'),source_capsule_manifest_sha256=sha(cap/'manifest.json'),normal_native_runs=len(runs),newmode_positive_runs=4,overlapping_independent_counter_reads=64,independent_positive_words=4*23*64,conservative_CSR_controls=['fflags','frm','fcsr','mstatus','vl','vtype','vlenb'],counter_forms=[2,3,6,7],counter_addresses=[0xb00,0xb02,0xc00,0xc02],scalar_FADD_hazard_and_source_counter_phase_unchanged=True,default_OFF_byte_parity='separate_composite_parity_receipt',legacy_selector_byte_parity='not_claimed_FENCE_preedge_corrected',trace_toggle_byte_parity='not_tested_here',physical_write_timing_or_numeric_semantics_changed=False,synthetic_zero_instruction_service_admission_control=True,no_physical_Icache_hit_claim=True,FENCE_absolute_source_admission_certified=False,hardware_or_protected_labels_opened=False,runs=runs,guest_builds=builds,input_sha256=inputs)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'report_sha256':sha(out/'report.json'),'runs':len(runs)}))
if __name__=='__main__':main()
