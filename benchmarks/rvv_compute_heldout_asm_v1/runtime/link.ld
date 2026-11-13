OUTPUT_ARCH(riscv)
ENTRY(_start)
SECTIONS {
  . = 0x80000000;
  .text : { KEEP(*(.text.init)) *(.text .text.*) }
  . = ALIGN(64);
  .rodata : { *(.rodata .rodata.*) }
  . = ALIGN(64);
  .tohost : { *(.tohost) }
  . = ALIGN(64);
  .data : { *(.data .data.*) }
  . = ALIGN(64);
  PROVIDE(__global_pointer$ = . + 0x800);
  .sdata : { *(.sdata .sdata.*) }
  . = ALIGN(64);
  __bss_start = .;
  .bss : { *(.sbss .sbss.* .bss .bss.* COMMON) }
  . = ALIGN(64);
  __bss_end = .;
  _end = .;
}
