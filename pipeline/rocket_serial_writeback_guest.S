// Force actual inclusive-L2 dirty victims using nine source-congruent lines.
// Iris source4ways/512KiB/fourbanks/64B blocks: 128KiB stride keeps bank+set.
.section .text.init,"ax",@progbits
.option norvc
.globl _start
_start:
  csrr a0,mhartid
  li t0,2
  bne a0,t0,.Lpark
  la t0,.Lfail
  csrw mtvec,t0
  la s0,lines
  li s1,9
  li s2,0x1234567800000000
  li s3,0x20000
.Lwrite:
  sd s2,0(s0)
  addi s0,s0,0 // Independent initialized integer instructions exercise overlap.
  addi s2,s2,1
  add s0,s0,s3
  addi s1,s1,-1
  bnez s1,.Lwrite
  // Revisit in the opposite order; independent goldens include every line.
  li s1,9
.Lread:
  sub s0,s0,s3
  addi s2,s2,-1
  ld a1,0(s0)
  bne a1,s2,.Lfail
  addi s1,s1,-1
  bnez s1,.Lread
  li t2,1
  j .Lexit
.Lfail:
  li t2,3
.Lexit:
  la t1,tohost
  sd t2,0(t1)
.Lpark:
  wfi
  j .Lpark
.balign 64
.space 64
.section .bss,"aw",@nobits
.balign 0x20000
lines:
  .space 9*0x20000
.section .tohost,"aw",@progbits
.balign 64
.globl tohost
tohost:.quad 0
.space 56
.globl fromhost
fromhost:.quad 0
.space 56
