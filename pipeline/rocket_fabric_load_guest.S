.section .text.init,"ax",@progbits
.option norvc
.globl _start
_start:
  csrr a0,mhartid
  li t0,2
  bne a0,t0,.Lpark
  la t0,.Ltrap
  csrw mtvec,t0
  li s0,0
  la t0,input
.globl source_load
source_load:
  ld a1,0(t0)
.rept 12
  addi s0,s0,1
.endr
.globl dependent_add
dependent_add:
  addi a2,a1,1
  li t0,0x1234000200000011
  bne a2,t0,.Ltrap
  li t0,12
  bne s0,t0,.Ltrap
  la t1,output
  sd a2,0(t1)
  fence rw,rw
  ld a3,0(t1)
  bne a3,a2,.Ltrap
  li s0,0
  li t0,0x10000
  .balign 64
.globl source_load_rom
source_load_rom:
  ld a1,0(t0)
.rept 12
  addi s0,s0,1
.endr
  addi a2,a1,1
  li t0,IRIS_ROM_WORD+1
  bne a2,t0,.Ltrap
  li t0,12
  bne s0,t0,.Ltrap
  li t2,1
  la t1,tohost
  sd t2,0(t1)
.Lpark:
  wfi
  j .Lpark
.Ltrap:
  li t2,3
  la t1,tohost
  sd t2,0(t1)
  j .Lpark
.balign 64
  .space 64
.section .data,"aw",@progbits
.balign 64
input: .quad 0x1234000200000010
  .space 56
.balign 64
output: .quad 0
  .space 56
.section .tohost,"aw",@progbits
.balign 64
.globl tohost
tohost: .quad 0
  .space 56
.globl fromhost
fromhost: .quad 0
  .space 56
