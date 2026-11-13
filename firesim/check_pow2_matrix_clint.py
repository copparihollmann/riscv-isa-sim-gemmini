"""Static actual-ELF CLINT/CSR/call sequence; not a hardware cycle oracle."""
import struct
from pow2_matrix_review import Elf
def inspect_clint_window(raw):
 e=Elf(raw);expected={0x80000b52:0x0200c937,0x80000b56:0xff893783,0x80000b5e:0xb02027f3,0x80000b64:0xb00027f3,0x80000b6c:0x93fff0ef,0x80000b70:0xb0002f73,0x80000b74:0xb0202e73,0x80000b7c:0x00093e83}
 for pc,word in expected.items():
  if struct.unpack('<I',e.read(pc,4))[0]!=word:raise ValueError('Actual matrix CLINT/CSR word changed')
 if e.read(0x80000b5a,2)!=b'\x61\x19':raise ValueError('Actual CLINT base subtraction changed')
 word=expected[0x80000b6c];imm=((word>>31)<<20)|(((word>>12)&255)<<12)|(((word>>20)&1)<<11)|(((word>>21)&1023)<<1);imm=imm-(1<<21)if imm&(1<<20)else imm
 if 0x80000b6c+imm!=e.syms['kernel'][0]:raise ValueError('Actual matrix call target changed')
 return dict(schema='iris.pow2_matrix_compiled_CLINT_window.v1',mtime_MMIO_address=0x0200bff8,mtime_before_load_pc=0x80000b56,CSR_begin_pc=0x80000b64,call_pc=0x80000b6c,CSR_end_pc=0x80000b70,mtime_after_load_pc=0x80000b7c,kernel_target=e.syms['kernel'][0],source_core_cycles_per_mtime_tick=1000,mtime_hz=500000,CLINT_window_scope='encloses_CSR_ROI_with_sampling_overhead',quantization_error_bound_source_core_cycles=1000,overhead_subtracted=False,raw_instruction_words={hex(k):hex(v)for k,v in expected.items()})
