.section .text.init
.globl _start
_start:
  la t0, handler
  csrw mtvec, t0
  rdcycle s0
  .4byte 0x00000000
  rdcycle s1
  li a0, 1
  la t0, tohost
  sd a0, 0(t0)
1: j 1b
.balign 4
handler:
  csrr t0, mepc
  addi t0, t0, 4
  csrw mepc, t0
  mret
.section .tohost,"aw",@progbits
.balign 64
.globl tohost
.globl fromhost
tohost: .dword 0
fromhost: .dword 0
