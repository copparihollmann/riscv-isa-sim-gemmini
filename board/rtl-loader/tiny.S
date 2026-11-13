.section .text.init,"ax",@progbits
.globl _start
_start:
  la t0, tohost
  li t1, 1
  sd t1, 0(t0)
  fence rw,rw
1: wfi
  j 1b
.section .tohost,"aw",@progbits
.balign 8
.globl tohost
tohost: .quad 0
.globl fromhost
fromhost: .quad 0
