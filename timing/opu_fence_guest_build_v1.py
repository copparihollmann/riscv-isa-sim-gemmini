#!/usr/bin/env python3
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);a=ap.parse_args();o=Path(a.output).resolve();o.mkdir(parents=True,exist_ok=False)
 asm=['.text','.option norvc'];names=[];sites=[]
 for fp in range(2):
  row=[]
  for f,word in enumerate((0x0330000f,0x0ff0000f,0x0000100f,0x0f30000f)):
   name=f'opufence_{fp}_{f}';row.append(name);site=f'{name}_barrier';sites.append((site,word))
   asm+=['.balign 64',f'.globl {name}',f'.type {name},@function',name+':']
   for i in range(64):asm.append('.4byte 0x%08x'%((0xf2881077 if fp else 0xf2880077)|((i%4)<<10)))
   asm +=[f'.globl {site}',site+':',f'.4byte 0x{word:08x}','csrr a0,mcycle','ret',f'.size {name},.-{name}']
  names.append(row)
 (o/'kernels.S').write_text('\n'.join(asm)+'\n');(o/'kernels.h').write_text('typedef unsigned long(*kernel_t)(void);\n'+''.join(f'extern unsigned long {n}(void);\n'for row in names for n in row)+'static kernel_t kernels[2][4]={{'+','.join(names[0])+'},{'+','.join(names[1])+'}};\n')
 base=json.load(open(ROOT/'build/warm-OPU-TK124-fullcell-guest-TK2-v1/build.json'));cmd=base['argv'][:];cmd=[x for x in cmd if not x.startswith('-DTEST_TK')];cmd=[str(ROOT/'timing/opu_fence_guest_v1.c')if x.endswith('/timing/overlap_completion_TK_guard_guest.c')else str(o/'kernels.S')if x.endswith('/kernels.S')else '-I'+str(o)if x.startswith('-I')and'warm-OPU-TK124-fullcell-guest-TK2-v1'in x else x for x in cmd];cmd[cmd.index('-o')+1]=str(o/'guest.elf')
 run=subprocess.run(cmd,capture_output=True);(o/'build.stdout').write_bytes(run.stdout);(o/'build.stderr').write_bytes(run.stderr)
 if run.returncode:raise RuntimeError(run.stderr.decode())
 from timing.memory_routes_current_audit_v2 import Elf
 e=Elf(o/'guest.elf');obj={n:dict(zip(('address','size'),e.symbol(n)))for n in('opu_fence_done','opu_fence_errors','opu_fence_cases','opu_fence_words','opu_fence_counters')};barriers={name:{'pc':e.symbol(name)[0],'raw':word}for name,word in sites}
 ins={str(Path(x).resolve()):sha(Path(x))for x in base['input_sha256']if Path(x).is_file()and'fullcell-guest'not in x and'overlap_completion_TK_guard'not in x};ins.update({str(p.resolve()):sha(p)for p in(Path(__file__),ROOT/'timing/opu_fence_guest_v1.c',o/'kernels.S',o/'kernels.h',o/'guest.elf')})
 j={'schema':'iris.opu_fence_finite_guest_build.v1','pass':True,'argv':cmd,'ELF_sha256':sha(o/'guest.elf'),'input_sha256':ins,'objects':obj,'barrier_sites':barriers,'cases':16,'numeric_words':65536,'scope':'two FM0 supported fences and two excluded barriers; INT8 and E4M3; both compute harts; all four tiles and all32x32 cells; scalar CSR follows each barrier; normal HTIF required'};(o/'build.json').write_text(json.dumps(j,indent=2)+'\n');print(json.dumps({'pass':True,'ELF_sha256':j['ELF_sha256']}))
if __name__=='__main__':main()
