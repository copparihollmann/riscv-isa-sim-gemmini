// Causal shared-memory check: variable instruction latencies reverse completion.
.option norvc
#include "uart_drain.S"
.section .text.init,"ax",@progbits
.globl _start
_start:
  csrr a0,mhartid
  li t1,2
  beq a0,t1,.Lpark
  bnez a0,.Lwait_ready
  li t0,0x10020008
  li t1,1
  sw t1,0(t0)
  la t0,start_ready
  sw t1,0(t0)
  j .Lready
.Lwait_ready:
  la t0,start_ready
1: lw t1,0(t0)
  beqz t1,1b
.Lready:
  la t0,shared
  li t1,99
  bnez a0,.Lreader
.globl iris_order_store
iris_order_store:
  sw t1,0(t0)
  la t0,producer_done
  li t1,1
  sw t1,0(t0)
  j .Lpark
.Lreader:
.globl iris_order_load
iris_order_load:
  lw s0,0(t0)
  la t0,producer_done
1: lw t1,0(t0)
  beqz t1,1b
  beqz s0,.Lzero
  li t1,99
  bne s0,t1,.Lfail
  la a0,seen99
  j .Lprint
.Lzero:
  la a0,seen0
.Lprint:
  li a1,0x10020000
1: lbu a2,0(a0)
  beqz a2,.Lexit
2: lw t0,0(a1)
  bltz t0,2b
  sw a2,0(a1)
  addi a0,a0,1
  j 1b
.Lexit:
  IRIS_UART_DRAIN
  la t0,tohost
.globl iris_exit_store
iris_exit_store:
  li t1,1
  sd t1,0(t0)
  j .Lpark
.Lfail:
  la t0,tohost
  li t1,3
  sd t1,0(t0)
.Lpark:
  wfi
  j .Lpark
.section .data,"aw",@progbits
.balign 64
shared: .word 0
producer_done: .word 0
start_ready: .word 0
seen0: .asciz "IRIS_ORDER {\"observed\":0}\nPASSED completion order\n"
seen99: .asciz "IRIS_ORDER {\"observed\":99}\nPASSED completion order\n"
.section .tohost,"aw",@progbits
.balign 64
.globl tohost
tohost: .dword 0
.balign 64
.globl fromhost
fromhost: .dword 0
