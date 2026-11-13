#!/usr/bin/env python3
"""Freeze normal/forced native proof and scalar-only observer machine-code guards."""
import argparse,hashlib,json,re,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'timing'))
from fp8_format_functional_audit_v1 import Elf
from firstuse_diag_validate_v1 import validate,cases,need
PATCH='558cefc2f57225774cc891e1df0d2f7149f6e834a7012b4c0735f0fba0d1aa1b'
TOOL=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-objdump')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def decoded(elf,symbol):
 e=Elf(elf);need(len(e.symbols[symbol])==1,'Unique actual symbol '+symbol);a,n=e.symbols[symbol][0];offset=0;out=[]
 while offset<n:
  w=int.from_bytes(e.read(a+offset,2),'little');size=4 if w&3==3 else 2;need(offset+size<=n,'Complete instruction');out.append((a+offset,size,int.from_bytes(e.read(a+offset,size),'little')));offset+=size
 return out
def codeproof(elf):
 functions={}
 for symbol in ['iris_probe_stamp','scalar_control_context','iris_probe_observe']:
  rows=decoded(elf,symbol)
  for pc,size,w in rows:
   need(not(size==4 and w&127 in [0x07,0x27,0x53,0x57,0x77])and not(size==2 and w&3 in[0,2]and w>>13 in[1,5]),'No application FP/vector operation in scalar observer/progress '+symbol)
   if symbol=='iris_probe_stamp':need(not(size==4 and w&127 in [0x0f,0x2f]),'No hot architectural FENCE/AMO')
  functions[symbol]=dict(instructions=len(rows),FP_or_vector_instructions=0,hot_fence_or_atomic_instructions=0 if symbol=='iris_probe_stamp'else None)
 restore=decoded(elf,'z_riscv_vstate_restore');save=decoded(elf,'z_riscv_vstate_save')
 need(sum(size==4 and w&127==7 for pc,size,w in restore)==4 and sum(size==4 and w&127==0x27 for pc,size,w in save)==4,'Unchanged four-group context mechanism present; not runtime proof')
 asm=subprocess.check_output([str(TOOL),'-d','--disassemble=iris_probe_observe',str(elf)],text=True)
 need('tohost'in asm and re.search(r'li\s+[a-z0-9]+,3\b',asm)is not None,'Compiled requested HTIFfailure3 path')
 return dict(scalar_observer_and_progress=functions,kernel_context_source_changed=False,compiled_4xm8_restore_and_save_present=True,context_execution_in_FPGA_proven=False,timeout_transport='Production ELF contains tohost3 path; forced actual native exit1 tested separately',scope='Last source-point/CSR records, no current PC/state or physical completion inference')
def qualify(a):
 out=a.output.resolve();need(not out.exists(),'Fresh qualification');b=a.build.resolve();built=json.loads((b/'build.json').read_text());elf=b/'zephyr/zephyr.elf';z=Path(built['source'])
 need(built['status']=='built'and built['elf_sha256']==sha(elf)and built['source_patch_sha256']==PATCH,'Exact new built normal ELF/unchanged kernel')
 need(hashlib.sha256(subprocess.check_output(['git','-C',str(z),'diff','--binary','HEAD'])).hexdigest()==PATCH,'Current unchanged context overlay')
 config=(b/'zephyr/.config').read_text();need('IRIS_FIRSTUSE_FORCE_STALL'not in config and 'IRIS_FIRSTUSE_TIMEOUT_MS=10'not in config,'Forced negative is not hardware-admitted')
 ids={str(ROOT/p):h for p,h in built['input_sha256'].items()};proof=codeproof(elf)
 gates=[]
 for negative,paths in [(False,a.gate),(True,a.negative)]:
  need(len(paths)==2,'Both schedules for normal and negative')
  for p in paths:
   p=p.resolve();r=json.loads((p/'report.json').read_text());need(r['pass']is True and r['expect_failure']is negative and r['timed_out']is False and type(r['exit_status'])is int and r['exit_status']==(1 if negative else 0),'Actual normal/failure subprocess outcome')
   need(sha(p/'stdout')==r['stdout_sha256']and sha(p/'stderr')==r['stderr_sha256'],'Exact run output bytes')
   need(validate((p/'stdout').read_text(),negative)==r['proof'],'Independent strict actual protocol recheck')
   if not negative:need(r['ELF_sha256']==sha(elf),'Exact hardware candidate executed')
   gates.append(dict(report=str(p/'report.json'),report_sha256=sha(p/'report.json'),seed=r['seed'],negative=negative,actual_exit_status=r['exit_status'],ELF_sha256=r['ELF_sha256']))
   ids.update(r['input_sha256']);ids.update({str(p/n):sha(p/n)for n in ['report.json','stdout','stderr']})
  need({x['seed']for x in gates if x['negative']is negative}=={0,17},'Seeds0/17')
 ninja=Path('/scratch/eygao/iris-cy/.conda-env/bin/ninja');deps=subprocess.check_output([str(ninja),'-C',str(b),'-t','deps'],text=True)
 for line in deps.splitlines():
  if line.startswith('    '):
   p=Path(line.strip());p=p if p.is_absolute()else b/p;need(p.is_file(),'Actual compiled dependency');ids[str(p.resolve())]=sha(p)
 for p in [elf,b/'build.json',b/'zephyr/.config',b/'zephyr/zephyr.dts',b/'zephyr/linker.cmd',Path(__file__).resolve(),ROOT/'zephyr/firstuse_diag_validate_v1.py',ROOT/'zephyr/firstuse_diag_run_v1.py',ROOT/'timing/fp8_format_functional_audit_v1.py',TOOL,ninja]:ids[str(p)]=sha(p)
 need(all(sha(p)==h for p,h in ids.items()),'All current source/run/tool inputs')
 out.mkdir(parents=True);(out/'inputs').mkdir()
 for p,h in ids.items():
  target=out/'inputs'/h
  if not target.exists():shutil.copyfile(p,target)
 (out/'compiled-dependencies.txt').write_text(deps);(out/'cases.json').write_text(json.dumps(cases(),indent=2)+'\n')
 for symbol in ['main','worker','scalar_control_context','iris_probe_stamp','iris_probe_observe','z_riscv_vstate_restore','iris_vme_enable']:(out/(symbol+'-disassembly.txt')).write_text(subprocess.check_output([str(TOOL),'-d','--disassemble='+symbol,str(elf)],text=True))
 report=dict(schema='iris.Zephyr_firstuse_diagnostic_qualification.v1',**{'pass':True},ELF_sha256=sha(elf),build=str(b),kernel_source_pin=built['zephyr_sha'],kernel_overlay_sha256=PATCH,kernel_source_changed=False,normal_gates=[x for x in gates if not x['negative']],forced_actual_HTIF1_controls=[x for x in gates if x['negative']],code_proof=proof,normal_regions=9,independent_checksums_by_hart=[1536,1280,1280,108,108,108,1024,1024,1024],h2_application_vector=False,observation_perturbation=True,original_93a_fixed_or_cause_proven=False,normal_v1_busy_poll_failures_preserved=True,hardware_contacted=False,calibration_usable=False,timing_certified=False,input_sha256=ids)
 (out/'qualification.json').write_text(json.dumps(report,indent=2)+'\n');ready=dict(schema='iris.Zephyr_firstuse_diagnostic_ready.v1',status='native_qualified_pending_managed_preparation',ELF_sha256=sha(elf),build=str(b),normal_regions=9,qualification_sha256=sha(out/'qualification.json'),cases_sha256=sha(out/'cases.json'),diagnostic_only=True,hardware_tested=False);(out/'ready.json').write_text(json.dumps(ready,indent=2)+'\n');return ready
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--gate',type=Path,action='append',required=True);p.add_argument('--negative',type=Path,action='append',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=qualify(a);print(json.dumps(dict(status=r['status'],ELF_sha256=r['ELF_sha256'],ready_sha256=sha(a.output/'ready.json'))))
