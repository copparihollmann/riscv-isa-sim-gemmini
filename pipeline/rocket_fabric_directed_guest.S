.section .text.init,"ax",@progbits
.option norvc
.globl _start
_start:
  csrr a0,mhartid
  li t0,2
#ifdef CASE_SHUTTLE_RAM
  bnez a0,.Lpark
  la t0,data
  ld a1,0(t0)
  j .Lfail
#else
  bne a0,t0,.Lpark
#endif
  la t0,.Lfail
  csrw mtvec,t0
  la s1,data
#ifdef CASE_WIDTHS
  lb a1,0(s1)
  li t0,-128
  bne a1,t0,.Lfail
  lbu a1,0(s1)
  li t0,128
  bne a1,t0,.Lfail
  lh a1,2(s1)
  li t0,-32767
  bne a1,t0,.Lfail
  lhu a1,2(s1)
  li t0,32769
  bne a1,t0,.Lfail
  lw a1,4(s1)
  li t0,-2147483647
  bne a1,t0,.Lfail
  lwu a1,4(s1)
  li t0,2147483649
  bne a1,t0,.Lfail
  li a1,0x8877665544332211
  sb a1,32(s1)
  sh a1,34(s1)
  sw a1,36(s1)
  sd a1,40(s1)
  lb a2,32(s1)
  li t0,0x11
  bne a2,t0,.Lfail
  lhu a2,34(s1)
  li t0,0x2211
  bne a2,t0,.Lfail
  lwu a2,36(s1)
  li t0,0x44332211
  bne a2,t0,.Lfail
  ld a2,40(s1)
  bne a2,a1,.Lfail
#elif defined(CASE_FAST_DEPENDENCIES)
  ld a1,8(s1)
  fence rw,rw
  ld a1,8(s1)
  sd a1,16(s1)
  ld a2,16(s1)
  bne a2,a1,.Lfail
  ld a1,24(s1)
  fence rw,rw
  ld a1,24(s1)
  ld a2,0(a1)
  li t0,0x0123456789abcdef
  bne a2,t0,.Lfail
#elif defined(CASE_WAW_REPLAY)
  li s1,0x10000
  .balign 64
  ld a1,0(s1)
  nop
  li a1,7
  li a2,7
  bne a1,a2,.Lfail
#elif defined(CASE_RVC_MEMORY)
  .option rvc
  c.ld a1,8(s1)
  fence rw,rw
  c.ld a1,8(s1)
  c.sd a1,16(s1)
  c.ld a2,16(s1)
  bne a1,a2,.Lfail
  c.lw a1,4(s1)
  c.sw a1,32(s1)
  c.lw a2,32(s1)
  bne a1,a2,.Lfail
  .option norvc
#elif defined(CASE_RVC_COLD_GUARD)
  .option rvc
  c.ld a1,8(s1)
  c.sd a1,16(s1)
  .option norvc
#elif defined(CASE_ATOMIC_REFUSAL)
  amoadd.d a1,a0,(s1)
#elif defined(CASE_LOAD_ZERO_REFUSAL)
  ld zero,0(s1)
#elif defined(CASE_UNALIGNED_REFUSAL)
  ld a1,1(s1)
#elif defined(CASE_UNKNOWN_BACKING_REFUSAL)
  li s1,0x80010000
  ld a1,0(s1)
#elif defined(CASE_TCM_SERVICE_REFUSAL)
  li s1,0x70000000
  ld a1,0(s1)
#elif defined(CASE_MPRV_REFUSAL)
  li t0,0x20000
  csrs mstatus,t0
  ld a1,0(s1)
#elif defined(CASE_SHUTTLE_RAM)
  nop
#else
#error explicit directed case required
#endif
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
.section .data,"aw",@progbits
.balign 64
data:
  .byte 0x80,0
  .half 0x8001
  .word 0x80000001
  .quad 0x0123456789abcdef
  .quad 0
  .quad data+8
  .space 32
.section .tohost,"aw",@progbits
.balign 64
.globl tohost
tohost: .quad 0
  .space 56
.globl fromhost
fromhost: .quad 0
  .space 56
