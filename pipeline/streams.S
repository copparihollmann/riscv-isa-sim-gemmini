.option push
.option norvc
.text
.macro start name
.global \name
\name:
  mv t6,a0
  li t3,0
  li t4,0
  csrr t0,mcycle
  csrr t1,minstret
.global \name\()_begin
\name\()_begin:
.endm
.macro end name
.global \name\()_end
\name\()_end:
  csrr t2,mcycle
  csrr t5,minstret
  sub t2,t2,t0
  sub t5,t5,t1
  sd t2,0(t6)
  sd t5,8(t6)
  sd t3,16(t6)
  sd t4,24(t6)
  ret
.endm
start independent
.rept 256
  addi t3,t3,1
  addi t4,t4,3
.endr
end independent
start dependent
.rept 512
  addi t3,t3,1
.endr
end dependent
start unused_field
  addi sp,sp,-16
  sd s2,0(sp)
  sd s3,8(sp)
  li s2,0
  li s3,0
.rept 256
  addi s2,s2,1
  lui s3,0x90
.endr
  mv t3,s2
  mv t4,s3
  ld s2,0(sp)
  ld s3,8(sp)
  addi sp,sp,16
end unused_field
start waw_zero
.rept 128
  addi t3,zero,7
  addi t3,zero,11
  addi t4,t3,5
  addi zero,t4,9
.endr
end waw_zero
.option pop
