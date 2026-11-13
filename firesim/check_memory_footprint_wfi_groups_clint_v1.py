"""Exact static sampling-order witness for the new072aa footprint ELF."""
import struct
from memory_footprints_wfi_groups_review_v1 import Elf

def inspect_clint_window(raw):
 e=Elf(raw);expected={0x800006ba:0x0200c7b7,0x800006be:0xff87b683,0x800006c4:0xb0002873,0x800006ca:0xb02028f3,0x800006ec:0xdc9ff0ef,0x800006f4:0xb0202773,0x800006f8:0xb0002673,0x800006fc:0x0200c7b7,0x80000702:0xff87b583}
 for pc,word in expected.items():
  if struct.unpack('<I',e.read(pc,4))[0]!=word:raise ValueError('ActualCLINT/CSR/call sequence changed')
 word=expected[0x800006ec];imm=((word>>31)<<20)|(((word>>12)&255)<<12)|(((word>>20)&1)<<11)|(((word>>21)&1023)<<1);imm=imm-(1<<21)if imm&(1<<20)else imm
 if 0x800006ec+imm!=e.syms['footprint_chase'][0]:raise ValueError('ActualJALtarget changed')
 return dict(schema='iris.memory_footprint_compiled_CLINT_window.v1',mtime_MMIO_address=0x0200bff8,mtime_before_load_pc=0x800006be,CSR_begin_pc=0x800006c4,call_pc=0x800006ec,CSR_end_pc=0x800006f8,mtime_after_load_pc=0x80000702,call_target=e.syms['footprint_chase'][0],before_load_precedes_CSR_begin=True,after_load_follows_CSR_end=True,raw_instruction_words={hex(pc):hex(word)for pc,word in expected.items()},scope='Static actualcompiler instructionordering; noRTLcyclephase/globalaccuracy certification',source_clock_hz=500000000,mtime_hz=500000,source_core_cycles_per_mtime_tick=1000,CLINT_window_scope='encloses_CSR_ROI_with_sampling_overhead',quantization_error_bound_source_core_cycles=1000,overhead_subtracted=False)
