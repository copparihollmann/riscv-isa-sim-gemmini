OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {
  . = 0x80000000;
  .text : { KEEP(*(.text.init)) }
  . = ALIGN(8);
  .tohost : { *(.tohost) }
}
