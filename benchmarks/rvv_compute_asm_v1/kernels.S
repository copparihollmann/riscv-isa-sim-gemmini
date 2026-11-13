.section .text.asm_measure,"ax",@progbits
.balign 4
.globl asm_measure
.type asm_measure,@function
asm_measure:
addi sp,sp,-112
sd ra,96(sp)
sd s0,0(sp)
sd s1,8(sp)
sd s2,16(sp)
sd s3,24(sp)
sd s4,32(sp)
sd s5,40(sp)
sd s6,48(sp)
sd s7,56(sp)
sd s8,64(sp)
sd s9,72(sp)
sd s10,80(sp)
sd s11,88(sp)
mv s0,a0
mv s1,a1
mv s2,a2
mv a0,a2
mv a1,a3
mv a2,a4
csrr s3,mip
srli s3,s3,3
andi s3,s3,1
li t0,0x0200bff8
ld s4,0(t0)
csrr s5,mcycle
csrr s6,minstret
#ifndef IRIS_SKIP_RVV_KERNEL
jalr ra,s1,0
#endif
csrr s7,minstret
csrr s8,mcycle
fence rw,rw
csrr s9,minstret
csrr s10,mcycle
li t0,0x0200bff8
ld s11,0(t0)
csrr t1,mip
srli t1,t1,3
andi t1,t1,1
sd s5,16(s0)
sd s8,24(s0)
sd s10,32(s0)
sd s6,40(s0)
sd s7,48(s0)
sd s9,56(s0)
sd s4,104(s0)
sd s11,112(s0)
sd s3,120(s0)
sd t1,128(s0)
ld ra,96(sp)
ld s0,0(sp)
ld s1,8(sp)
ld s2,16(sp)
ld s3,24(sp)
ld s4,32(sp)
ld s5,40(sp)
ld s6,48(sp)
ld s7,56(sp)
ld s8,64(sp)
ld s9,72(sp)
ld s10,80(sp)
ld s11,88(sp)
addi sp,sp,112
ret
.size asm_measure,.-asm_measure
.section .text.asm_integer0,"ax",@progbits
.balign 4
.globl asm_integer0
.type asm_integer0,@function
asm_integer0:
1:
.rept 16
vadd.vv v8,v8,v16
.endr
addi a0,a0,-1
bnez a0,1b
ret
.size asm_integer0,.-asm_integer0
.section .text.asm_integer1,"ax",@progbits
.balign 4
.globl asm_integer1
.type asm_integer1,@function
asm_integer1:
1:
.rept 16
vadd.vv v8,v8,v16
vadd.vv v24,v24,v16
.endr
addi a0,a0,-1
bnez a0,1b
ret
.size asm_integer1,.-asm_integer1
.section .text.asm_integer2,"ax",@progbits
.balign 4
.globl asm_integer2
.type asm_integer2,@function
asm_integer2:
1:
.rept 16
vadd.vv v8,v8,v16
vadd.vv v24,v8,v16
.endr
addi a0,a0,-1
bnez a0,1b
ret
.size asm_integer2,.-asm_integer2
.section .text.asm_fp0,"ax",@progbits
.balign 4
.globl asm_fp0
.type asm_fp0,@function
asm_fp0:
1:
.rept 16
vfadd.vv v8,v8,v16
.endr
addi a0,a0,-1
bnez a0,1b
ret
.size asm_fp0,.-asm_fp0
.section .text.asm_fp1,"ax",@progbits
.balign 4
.globl asm_fp1
.type asm_fp1,@function
asm_fp1:
1:
.rept 16
vfadd.vv v8,v8,v16
vfadd.vv v24,v24,v16
.endr
addi a0,a0,-1
bnez a0,1b
ret
.size asm_fp1,.-asm_fp1
.section .text.asm_fp2,"ax",@progbits
.balign 4
.globl asm_fp2
.type asm_fp2,@function
asm_fp2:
1:
.rept 16
vfadd.vv v8,v8,v16
vfadd.vv v24,v8,v16
.endr
addi a0,a0,-1
bnez a0,1b
ret
.size asm_fp2,.-asm_fp2
.section .text.asm_load,"ax",@progbits
.balign 4
.globl asm_load
.type asm_load,@function
asm_load:
1:
.rept 16
vle32.v v8,(a1)
.endr
addi a0,a0,-1
bnez a0,1b
ret
.size asm_load,.-asm_load
.section .text.asm_store,"ax",@progbits
.balign 4
.globl asm_store
.type asm_store,@function
asm_store:
1:
.rept 16
vse32.v v8,(a2)
.endr
addi a0,a0,-1
bnez a0,1b
ret
.size asm_store,.-asm_store
.section .text.asm_load_use,"ax",@progbits
.balign 4
.globl asm_load_use
.type asm_load_use,@function
asm_load_use:
1:
.rept 16
vle32.v v8,(a1)
vadd.vv v24,v8,v16
.endr
addi a0,a0,-1
bnez a0,1b
ret
.size asm_load_use,.-asm_load_use
.section .text.asm_load_independent,"ax",@progbits
.balign 4
.globl asm_load_independent
.type asm_load_independent,@function
asm_load_independent:
1:
.rept 16
vle32.v v8,(a1)
vadd.vi v24,v24,1
.endr
addi a0,a0,-1
bnez a0,1b
ret
.size asm_load_independent,.-asm_load_independent
.section .text.asm_store_compute,"ax",@progbits
.balign 4
.globl asm_store_compute
.type asm_store_compute,@function
asm_store_compute:
1:
.rept 16
vse32.v v8,(a2)
vadd.vi v24,v24,1
.endr
addi a0,a0,-1
bnez a0,1b
ret
.size asm_store_compute,.-asm_store_compute
.section .text.asm_matrix_int,"ax",@progbits
.balign 4
.globl asm_matrix_int
.type asm_matrix_int,@function
asm_matrix_int:
1:
.rept 16
.word 0xf2880077
.endr
addi a0,a0,-1
bnez a0,1b
ret
.size asm_matrix_int,.-asm_matrix_int
.section .text.asm_matrix_fp8,"ax",@progbits
.balign 4
.globl asm_matrix_fp8
.type asm_matrix_fp8,@function
asm_matrix_fp8:
1:
.rept 16
.word 0xf2881077
.endr
addi a0,a0,-1
bnez a0,1b
ret
.size asm_matrix_fp8,.-asm_matrix_fp8
.section .text.asm_row1,"ax",@progbits
.balign 4
.globl asm_row1
.type asm_row1,@function
asm_row1:
li t3,0
.insn r 0x57, 6, 0x21, x24, t3, x31
ret
.size asm_row1,.-asm_row1
.section .text.asm_row4,"ax",@progbits
.balign 4
.globl asm_row4
.type asm_row4,@function
asm_row4:
li t3,0
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,1
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,2
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,3
.insn r 0x57, 6, 0x21, x24, t3, x31
ret
.size asm_row4,.-asm_row4
.section .text.asm_row16,"ax",@progbits
.balign 4
.globl asm_row16
.type asm_row16,@function
asm_row16:
li t3,0
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,1
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,2
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,3
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,4
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,5
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,6
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,7
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,8
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,9
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,10
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,11
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,12
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,13
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,14
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,15
.insn r 0x57, 6, 0x21, x24, t3, x31
ret
.size asm_row16,.-asm_row16
.section .text.asm_row64,"ax",@progbits
.balign 4
.globl asm_row64
.type asm_row64,@function
asm_row64:
li t3,0
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,1
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,2
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,3
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,4
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,5
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,6
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,7
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,8
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,9
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,10
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,11
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,12
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,13
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,14
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,15
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,16
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,17
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,18
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,19
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,20
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,21
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,22
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,23
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,24
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,25
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,26
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,27
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,28
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,29
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,30
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,31
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,0
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,1
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,2
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,3
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,4
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,5
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,6
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,7
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,8
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,9
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,10
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,11
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,12
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,13
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,14
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,15
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,16
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,17
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,18
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,19
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,20
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,21
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,22
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,23
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,24
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,25
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,26
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,27
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,28
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,29
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,30
.insn r 0x57, 6, 0x21, x24, t3, x31
li t3,31
.insn r 0x57, 6, 0x21, x24, t3, x31
ret
.size asm_row64,.-asm_row64
