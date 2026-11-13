#!/usr/bin/env python3
from pathlib import Path
import subprocess,hashlib,json,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
CC=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 entries=[]
 for kind,name in enumerate(['hpm','rdtime','fpcomp'],1):
  elf=HERE/(name+'.elf');inputs=[ROOT/'benchmarks/start.S',ROOT/'benchmarks/link.ld',ROOT/'benchmarks/runtime.h',HERE/'probe_runtime.h',HERE/'probe_runtime.c',HERE/(name+'.c')]
  if name=='hpm':inputs.append(HERE/'hpm_switch.h')
  command=[str(CC),'-O2','-g','-Wall','-Wextra','-Werror','-ffreestanding','-fno-builtin','-fno-tree-vectorize','-fno-tree-slp-vectorize','-mcmodel=medany','-mabi=lp64d','-march=rv64gcv_zfh_zvfh_zicsr_zifencei','-nostdlib','-static','-Wl,--build-id=none,--gc-sections','-DIRIS_HARTS=3','-DPROBE_KIND='+str(kind),'-T',str(ROOT/'benchmarks/link.ld'),str(ROOT/'benchmarks/start.S'),str(HERE/'probe_runtime.c'),str(HERE/(name+'.c')),'-lgcc','-o',str(elf)]
  subprocess.run(command,check=True);sys.path.insert(0,str(ROOT/'spike'));from run_functional import symbols
  sym=symbols(elf);entries.append({'name':name,'elf':str(elf),'elf_sha256':sha(elf),'expected_rtl_exit':0,'tohost_address':hex(sym['tohost']),'mailbox_address':hex(sym['iris_rtl_probe_mailbox']),'build_argv':command,'source_sha256':{str(p.relative_to(ROOT)):sha(p) for p in inputs}})
 manifest={'schema_version':1,'compiler_sha256':sha(CC),'expected_fir_sha256':json.loads((ROOT/'hardware/manifest.json').read_text())['sources']['firesim-fir']['sha256'],'rtl_executed':False,'deployed_image_association_verified':False,'stdout_used':False,'uart_drain_needed':False,'fcsr_explicitly_zeroed_after_fs_enable':True,'mailbox_layout':'64bit little endian: magic,version,kind,failed; hart[3] each stage,actual,expected,cause,pc,tval,checks,done','failure_status_encoding':'0x100 + hart*0x40 + stage; tohost=(status<<1)|1','hpm_expected':'mcounteren/scounteren after writing allones read7; mcountinhibit reads5; all29 mhpmcounter/hpmcounter/mhpmevent slots RAZ/WI in M mode','rdtime_expected':'CSR0xc01 read raises illegal cause2 with encoding0xc01022f3 tval; separate CLINT mtime MMIO remains monotonically readable','fpcomp_expected':'For both altfmt values on all3 harts: vs1 wins zero ties; masked physical tail poison sets NV; H/S chunk flags differ from IEEE chosen SEW; e16alt uses H; masked min-reduction qNaN seed folds to +inf','entries':entries}
 (HERE/'expected-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({'built':[e['elf'] for e in entries]}))
if __name__=='__main__':main()
