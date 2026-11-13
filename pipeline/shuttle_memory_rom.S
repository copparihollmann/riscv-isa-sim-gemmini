// Minimal explicitly substituted diagnostic ROM; not the shipped Iris BootROM.
.option norvc
.section .text,"ax",@progbits
.globl _start
_start:
  li t0,0x80000000
  jr t0
