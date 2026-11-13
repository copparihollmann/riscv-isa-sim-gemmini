.section .text.packet_measure,"ax",@progbits
.balign 4
.globl packet_measure
.type packet_measure,@function
packet_measure:
addi sp,sp,-80
sd ra,64(sp)
sd s0,0(sp)
sd s1,8(sp)
sd s2,16(sp)
sd s3,24(sp)
sd s4,32(sp)
sd s5,40(sp)
sd s6,48(sp)
sd s7,56(sp)
mv s0,a0
mv s1,a1
mv a0,a2
csrr s3,mcycle
csrr s4,minstret
#ifndef IRIS_POWER2_SKIP_MEASURED
jalr ra,s1,0
#endif
csrr s5,mcycle
fence rw,rw
csrr s6,mcycle
csrr s7,minstret
sd s3,40(s0)
sd s5,48(s0)
sd s6,56(s0)
sd s4,64(s0)
sd s7,72(s0)
ld ra,64(sp)
ld s0,0(sp)
ld s1,8(sp)
ld s2,16(sp)
ld s3,24(sp)
ld s4,32(sp)
ld s5,40(sp)
ld s6,48(sp)
ld s7,56(sp)
addi sp,sp,80
ret
.size packet_measure,.-packet_measure
.macro BODY name,op
.section .text.\name,"ax",@progbits
.balign 4
.globl \name
.type \name,@function
\name:
1:
.rept 16
\op
.endr
addi a0,a0,-1
bnez a0,1b
\op
ret
.size \name,.-\name
.endm
BODY packet_vadd,"vadd.vv v24,v24,v8"
BODY packet_mm_int,".word 0xf2880077"
BODY packet_mm_e4,".word 0xf2881077"
BODY packet_mm_e5,".word 0xf28810f7"
