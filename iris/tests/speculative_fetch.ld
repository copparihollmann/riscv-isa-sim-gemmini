OUTPUT_ARCH(riscv)
ENTRY(_start)
PHDRS {
  executable PT_LOAD FLAGS(5);
  writable PT_LOAD FLAGS(6);
}
SECTIONS {
  . = 0x80000000;
  .text : { *(.text.init) *(.text.last) } :executable
  . = 0x80002000;
  .htif : { *(.htif) } :writable
  /DISCARD/ : { *(.comment) }
}
