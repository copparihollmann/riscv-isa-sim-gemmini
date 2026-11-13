OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {
  . = 0x80000000;
  .text : { *(.text.init) *(.text*) }
  . = ALIGN(0x1000);
  .data : { *(.data*) }
  .tohost : { *(.tohost) }
  .bss : { *(.bss*) }
}
