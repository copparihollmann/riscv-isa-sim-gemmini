.section .text,"ax",@progbits
.option push
.option norvc
.macro TIME_BEGIN
  csrr t4,mcycle
  csrr t5,minstret
.endm
.macro TIME_END
  csrr t6,minstret
  csrr a1,mcycle
  sd t4,0(a0)
  sd a1,8(a0)
  sd t5,16(a0)
  sd t6,24(a0)
.endm
.macro SAVE_RESULT
  sd t0,32(a0)
  li a1,256
  sd a1,40(a0)
  sd zero,48(a0)
  sd zero,56(a0)
  ret
.endm
.balign 64
.global scalar_dep256
scalar_dep256:
  li t0,1
  TIME_BEGIN
  .rept 256
    addi t0,t0,1
  .endr
  TIME_END
  SAVE_RESULT
.balign 64
.global scalar_ind256
scalar_ind256:
  li t0,1
  li t1,2
  li t2,3
  li t3,4
  li a2,5
  li a3,6
  li a4,7
  li a5,8
  TIME_BEGIN
  .rept 32
    addi t0,t0,1
    addi t1,t1,1
    addi t2,t2,1
    addi t3,t3,1
    addi a2,a2,1
    addi a3,a3,1
    addi a4,a4,1
    addi a5,a5,1
  .endr
  TIME_END
  add t0,t0,t1
  add t0,t0,t2
  add t0,t0,t3
  add t0,t0,a2
  add t0,t0,a3
  add t0,t0,a4
  add t0,t0,a5
  SAVE_RESULT
.option pop
.section .data.signature,"aw",@progbits
.balign 64
.global begin_signature,mailbox,end_signature
begin_signature:
mailbox:
  .quad 0x495249535343414c,1
  .zero 432
end_signature:
