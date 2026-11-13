.option norvc
.section .text.init,"ax",@progbits
.globl _start
_start:
  csrr a0,mhartid
  bnez a0,.Lspin
  la t0,tohost
  li t1,1
.globl iris_exit_store
iris_exit_store:
  sd t1,0(t0)
.Lspin:
  addi s0,s0,1
  j .Lspin
.section .tohost,"aw",@progbits
.balign 64
.globl tohost
tohost: .dword 0
.balign 64
.globl fromhost
fromhost: .dword 0
