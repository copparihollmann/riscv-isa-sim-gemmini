#!/usr/bin/env python3
"""Bind the first finite live-unit capability to actual ELF instruction bytes."""
import argparse,hashlib,json,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def generate(elf,admission):
 elf=Path(elf).resolve();admission=Path(admission).resolve();r=json.loads(admission.read_text());raw=elf.read_bytes()
 if r['schema']!='iris.saturn_initial_live_ELF_capability.v1'or sha(elf)!=r['ELF_sha256']or r['harts']!=3 or r['compute_owner_harts']!=[0]:raise ValueError('exact first-capability three-hart admission required')
 if raw[:6]!=b'\x7fELF\x02\x01'or len(raw)<64:raise ValueError('little-endian ELF64 required')
 hdr=struct.unpack_from('<16sHHIQQQIHHHHHH',raw);phoff,phsz,phnum=hdr[5],hdr[9],hdr[10]
 if hdr[2]!=243 or phsz!=56 or phoff>len(raw)or phnum>(len(raw)-phoff)//phsz:raise ValueError('RISC-V ELF program headers required')
 segments=[]
 for n in range(phnum):
  kind,flags,offset,vaddr,paddr,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',raw,phoff+n*phsz)
  if kind==1:
   if filesz and(offset>len(raw)or filesz>len(raw)-offset):raise ValueError('file-backed ELF segment out of bounds')
   segments.append((vaddr,filesz,offset,flags))
 def instruction(pc):
  candidates=[raw[off+pc-base:off+pc-base+4]for base,size,off,flags in segments if flags&1 and base<=pc and pc+4<=base+size]
  if len(candidates)!=1 or len(candidates[0])!=4:raise ValueError('unique executable file-backed instruction required')
  return int.from_bytes(candidates[0],'little')
 commands=r['actual_unit_EX_instructions'];patterns={(x['mask'],x['value'])for x in r['admitted_actual_unit_EX_patterns']}
 if len(commands)!=9 or len(patterns)!=9 or any(mask!=0xffffffff for mask,value in patterns):raise ValueError('exact finite nine-encoding envelope required')
 if {(0xffffffff,x['instruction'])for x in commands}!=patterns:raise ValueError('command PCs and encoding patterns disagree')
 if any(instruction(x['pc'])!=x['instruction']for x in commands):raise ValueError('actual ELF bytes disagree with admitted command')
 if any(instruction(x['pc'])!=x['instruction']or x['instruction']&0x707f!=0x7057 for x in r['CPU_configuration_instructions_not_dispatched_to_unit']):raise ValueError('configuration instructions must be actual CPU configuration bytes')
 lines=['schema iris.saturn.finite_integer_K1.v1','hart 0','elf_sha256 '+sha(elf),'admission_sha256 '+sha(admission)]
 for x in commands:lines.append(f"command {x['pc']:#x} {x['instruction']:#x}")
 return '\n'.join(lines)+'\n'
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--elf',type=Path,default=ROOT/'build/saturn-timing-live-guest-v1/guest.elf');p.add_argument('--admission',type=Path,default=ROOT/'build/saturn-timing-live-guest-v1/admission.json');p.add_argument('--output',required=True,type=Path);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True);manifest=out/'native.manifest';manifest.write_text(generate(a.elf,a.admission));report=dict(schema='iris.saturn.finite_native_admission_generation.v1',status='passed_actual_ELF_PC_raw_manifest_binding',native_manifest_sha256=sha(manifest),input_sha256={str(x.resolve()):sha(x)for x in [Path(__file__),a.elf,a.admission]},actual_native_execution=False,timing_certified=False);(out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
