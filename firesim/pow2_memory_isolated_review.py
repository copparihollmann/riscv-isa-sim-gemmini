"""Strict admission of the new active-only pointer experiment."""
import importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];BENCH=ROOT/'benchmarks/pow2_memory_isolated_v3'
sys.path.insert(0,str(BENCH))
import qualify as proof
import validate as val
sys.path.pop(0)
ELF='b14aa74648af255d8a244572856c07c0a82322da72a296608bfa62ba9ed8705c'
ROLE='pow2_isolated_memory_train_reserved_v3'
inspect=proof.inspect;flatten=proof.flatten
def validator():return val
def inspect_clint_window(raw):
 import struct
 e=proof.elfmod.Elf(raw);words={0x80000512:0x0200cbb7,0x800006c2:0x000bba83,0x800006c6:0xb0002c73,0x800006ca:0xb0202cf3,0x800006d2:0xd47ff0ef,0x800006d6:0x0330000f,0x800006da:0xb0202673,0x800006de:0xb0002f73,0x800006e2:0x000bb583}
 for pc,word in words.items():
  if struct.unpack('<I',e.read(pc,4))[0]!=word:raise ValueError('Compiled isolated CLINT/CSR/call sequence changed')
 if struct.unpack('<H',e.read(0x80000522,2))[0]!=0x1be1:raise ValueError('mtime address addi changed')
 w=words[0x800006d2];imm=((w>>31)<<20)|(((w>>12)&255)<<12)|(((w>>20)&1)<<11)|(((w>>21)&1023)<<1);imm-=1<<21 if imm&(1<<20)else 0
 if 0x800006d2+imm!=e.syms['footprint_chase'][0]:raise ValueError('Actual kernel call target')
 return dict(mtime_MMIO_address=0x0200bff8,mtime_before_load_pc=0x800006c2,CSR_begin_pc=0x800006c6,call_pc=0x800006d2,CSR_end_pc=0x800006de,mtime_after_load_pc=0x800006e2,raw_instruction_words={hex(k):hex(v)for k,v in words.items()},compiled_bracket_order=True,overhead_subtracted=False,quantization_error_bound_source_core_cycles=1000)
