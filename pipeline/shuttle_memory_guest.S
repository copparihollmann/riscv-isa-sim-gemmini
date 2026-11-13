// Explicit diagnostic program: no stack, no hidden cache initialization.
.section .text.init,"ax",@progbits
.option norvc
.globl _start
_start:
  csrr a0,mhartid
#ifndef WORKER
#define WORKER 0
#endif
  li t0,WORKER
  bne a0,t0,.Lpark
  la t0,.Lfail
  csrw mtvec,t0
  la s0,source_data
#ifdef CASE_COLD_STORE
  li t1,7
  sd t1,0(s0)
#elif defined(CASE_UNKNOWN_ADDRESS)
  ld t1,0(s5)
#elif defined(CASE_MISALIGNED)
  ld t1,1(s0)
#elif defined(CASE_NARROW)
  lw t1,0(s0)
#elif defined(CASE_ATOMIC)
  li t1,1
  amoadd.d t2,t1,0(s0)
#elif defined(CASE_COMPRESSED)
  .option rvc
  c.ld a1,0(s0)
  .option norvc
#elif defined(CASE_FENCE_FORM)
  fence iorw,iorw
#elif defined(CASE_UNKNOWN_BACKING)
  li s0,0x81000000
  ld t1,0(s0)
#endif
#ifdef CASE_SOURCE_DISCARD_WARMUP
.globl source_discard_warmup
source_discard_warmup:
.rept 4
.rept 16
  ld zero,0(s0)
.endr
  addi s0,s0,64
.endr
.globl source_discard_warmup_end
source_discard_warmup_end:
  fence rw,rw
  la s0,source_data
#endif
#ifdef CASE_SOURCE_NACK
.rept 20
  ld zero,0(s0)
.endr
  fence rw,rw
#endif
  li s1,64
  li s2,0
.globl real_warmup_load
real_warmup_load:
  ld t1,0(s0)
  add s2,s2,t1
  addi s0,s0,64
  addi s1,s1,-1
  bnez s1,real_warmup_load
  li s3,0x1234567800000000*64+2016
#ifdef CASE_WRONG_GOLDEN
  addi s3,s3,1
#endif
  bne s2,s3,.Lfail
#ifdef CASE_READ_ONLY
.globl read_only_success
read_only_success:
  addi s2,s2,0
  j read_only_success
#endif
  la s0,target_data
  li t1,0x55aa11ee22dd33cc
.globl owned_store
owned_store:
  sd t1,0(s0)
.globl dependent_load
 dependent_load:
  ld t2,0(s0)
  bne t2,t1,.Lfail
  addi t2,t2,1
  addi t1,t1,1
  bne t2,t1,.Lfail
  ld zero,0(s0)
  fence rw,rw
  li t2,1
  j .Lexit
.Lfail:
  li t2,3
.Lexit:
  la t1,tohost
.globl owned_exit_store
owned_exit_store:
  sd t2,0(t1)
.Lpark:
  wfi
  j .Lpark
.balign 64
.space 64
.section .data,"aw",@progbits
.balign 64
source_data:
.set i,0
.rept 64
  .quad 0x1234567800000000+i
  .space 56
  .set i,i+1
.endr
.balign 64
target_data:.quad 0
.space 56
.section .tohost,"aw",@progbits
.balign 64
.globl tohost
tohost:.quad 0
.space 56
.globl fromhost
fromhost:.quad 0
.space 56
