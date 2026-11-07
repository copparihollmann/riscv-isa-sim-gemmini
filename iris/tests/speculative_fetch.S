/* The return's cold predicted fallthrough is not necessarily executable. */
.option norelax
.option norvc
.section .text.init
.globl _start
_start:
  csrr a0, mhartid
  bnez a0, parked
  la ra, finished
  la t0, tail_ret
#if NEGATIVE
  addi t0, t0, 2
#endif
  jr t0
finished:
  la t0, tohost
  li t1, 1
  sd t1, 0(t0)
1: j 1b
parked:
  wfi
  j parked

.section .text.last
.option rvc
.globl tail_ret
tail_ret:
  ret
#if PARTIAL
  /* The first parcel of a 32-bit ADDI exists, but its second parcel does not. */
  .2byte 0x0013
#endif

.section .htif,"aw",@progbits
.align 3
.globl tohost
tohost: .dword 0
.globl fromhost
fromhost: .dword 0
