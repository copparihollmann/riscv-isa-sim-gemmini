.option norvc
.section .text.init,"ax",@progbits
.globl _start
_start:
  csrr t0,mhartid
  bnez t0,.Lpark
  la t0,.Ltrap
  csrw mtvec,t0
  la t1,value
#if MEMORY_GUARD == 1
  li t0,0x6600
  csrs mstatus,t0
  vsetvli t0,zero,e8,m1,ta,ma
  vle8.v v0,(t1)
#elif MEMORY_GUARD == 2
  li t0,0x21800
  csrs mstatus,t0
  ld t2,0(t1)
#else
#error Unsupported memory guard
#endif
  la t0,tohost
  li t1,1
  sd t1,0(t0)
.Lpark:
  wfi
  j .Lpark
.balign 4
.Ltrap:
  la t0,tohost
  li t1,3
  sd t1,0(t0)
  j .Lpark
.section .data,"aw",@progbits
.balign 64
value: .zero 64
.section .tohost,"aw",@progbits
.balign 64
.globl tohost
tohost: .dword 0
.balign 64
.globl fromhost
fromhost: .dword 0
