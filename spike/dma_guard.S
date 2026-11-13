// Hart-2 source-backed vector memcpy, arithmetic and register-move checks.
#include "../benchmarks/uart_drain.S"
.section .text.init,"ax",@progbits
.globl _start
_start:
  csrr a0, mhartid
  li t0, 2
  bne a0, t0, .Lpark
  li t0, 0x10020008
  li t1, 1
  sw t1, 0(t0)
  fence iorw,iorw
  li t0, 0x600
  csrs mstatus, t0
  li a0, 8
  vsetvli t0, a0, e8, m1, tu, mu
  la a0, source
  la a1, destination
  vle8.v v8, (a0)
  vse8.v v8, (a1)
  li t0, 8
.Lcompare:
  lbu t1, 0(a0)
  lbu t2, 0(a1)
  bne t1, t2, .Lfail
  addi a0, a0, 1
  addi a1, a1, 1
  addi t0, t0, -1
  bnez t0, .Lcompare
#ifdef DMA_TEST_MOVE
  vmv.v.i v8, 1
#else
  vadd.vv v8, v8, v8
#endif
  la a1,destination
  vse8.v v8,(a1)
  la a0,source
  li t0,8
1:
#ifdef DMA_TEST_MOVE
  li t1,1
#else
  lbu t1,0(a0)
  slli t1,t1,1
  andi t1,t1,255
#endif
  lbu t2,0(a1)
  bne t1,t2,.Lfail
  addi a0,a0,1
  addi a1,a1,1
  addi t0,t0,-1
  bnez t0,1b
  la a0,success_message
  li a1,0x10020000
1:
  lbu a2,0(a0)
  beqz a2,3f
2:
  lw t0,0(a1)
  bltz t0,2b
  sw a2,0(a1)
  addi a0,a0,1
  j 1b
3:
  IRIS_UART_DRAIN
  la t0,tohost
  li t1,1
  sd t1,0(t0)
  j .Lpark
.Lfail:
  la t0, tohost
  li t1, 3
  sd t1, 0(t0)
.Lpark:
  wfi
  j .Lpark
.section .data,"aw",@progbits
.balign 8
source: .byte 0,17,34,51,68,85,102,119
destination: .zero 8
success_message: .asciz "PASSED HART2_VECTOR\n"
.section .tohost,"aw",@progbits
.balign 64
.globl tohost
tohost: .dword 0
.balign 64
.globl fromhost
fromhost: .dword 0
