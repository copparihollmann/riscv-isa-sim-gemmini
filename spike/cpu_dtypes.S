// Source-backed IEEE FP16/FP32/FP64 scalar and vector operations on every hart.
// Compute harts additionally check BF16 FMA and OFP8 widening.
#include "encoding.h"
#include "../benchmarks/uart_drain.S"
.section .text.init,"ax",@progbits
.globl _start
_start:
  csrr s0, mhartid
  bnez s0, .Luart_ready
  li t0, 0x10020008
  li t1, 1
  sw t1, 0(t0)
  fence iorw,iorw
.Luart_ready:
  .option push
  .option norelax
  la s2, results
  .option pop
  slli t0, s0, 6
  add s2, s2, t0
  li t0, 0x6600
  csrs mstatus, t0
  csrw fcsr, zero
  la a0, half_inputs
  flh f0, 0(a0)
  flh f1, 8(a0)
  flh f2, 16(a0)
  fmadd.h f3, f0, f1, f2
  fmv.x.h t0, f3
  li t1, 0x4300
  bne t0, t1, .Lfail
  la a0, single_inputs
  flw f0, 0(a0)
  flw f1, 16(a0)
  flw f2, 32(a0)
  fmadd.s f3, f0, f1, f2
  fmv.x.w t0, f3
  li t1, 0x40600000
  bne t0, t1, .Lfail
  la a0, double_inputs
  fld f0, 0(a0)
  fld f1, 32(a0)
  fld f2, 64(a0)
  fmadd.d f3, f0, f1, f2
  fmv.x.d t0, f3
  li t1, 0x400c000000000000
  bne t0, t1, .Lfail
.macro VECTOR ew, vload, vstore, base, wanted, sload, stride, alt=0
  li a0, 4
.if \alt
  .insn i 0x57,7,t0,a0,0x1c8
.else
  vsetvli t0,a0,\ew,m1,tu,mu
.endif
  la a0, \base
  addi a1,a0,(4*\stride)
  addi a2,a0,(8*\stride)
  \vload v8,(a0)
  \vload v16,(a1)
  \vload v24,(a2)
  vfmacc.vv v24,v8,v16
  \vstore v24,(s2)
  mv a0,s2
  li t0,4
  li t1,\wanted
1:
  \sload t2,0(a0)
  bne t2,t1,.Lfail
  addi a0,a0,\stride
  addi t0,t0,-1
  bnez t0,1b
.endm
  VECTOR e16,vle16.v,vse16.v,half_inputs,0x4300,lhu,2
  VECTOR e32,vle32.v,vse32.v,single_inputs,0x40600000,lwu,4
  VECTOR e64,vle64.v,vse64.v,double_inputs,0x400c000000000000,ld,8
  li t0,2
  beq s0,t0,.Ldone
  VECTOR e16,vle16.v,vse16.v,bfloat_inputs,0x4060,lhu,2,1
  // BF16 -> FP32 using the real BF16 conversion instruction encoding.
  .word (MATCH_VFWCVTBF16_F_F_V | (1<<25) | (8<<20) | (16<<7))
  li a0,4
  vsetvli t0,a0,e32,m1,tu,mu
  vse32.v v16,(s2)
  lwu t0,0(s2)
  li t1,0x3fc00000
  bne t0,t1,.Lfail
  // E4M3 -> BF16, including signed zero.
  li a0,4
  vsetvli t0,a0,e8,m1,tu,mu
  la a0,fp8_e4
  vle8.v v8,(a0)
  .word (MATCH_VFWCVTBF16_F_F_V | (1<<25) | (8<<20) | (16<<7))
  li a0,4
  vsetvli t0,a0,e16,m1,tu,mu
  vse16.v v16,(s2)
  la a1,fp8_want
  jal ra,.Lcompare4
  // E5M2 -> BF16.
  li a0,4
  .insn i 0x57,7,t0,a0,0x1c0
  la a0,fp8_e5
  vle8.v v8,(a0)
  .word (MATCH_VFWCVTBF16_F_F_V | (1<<25) | (8<<20) | (16<<7))
  li a0,4
  vsetvli t0,a0,e16,m1,tu,mu
  vse16.v v16,(s2)
  la a1,fp8_want
  jal ra,.Lcompare4
.Ldone:
  la t0,completed
  li t1,1
  amoadd.w.aqrl t2,t1,(t0)
  addi t2,t2,1
  li t1,3
  bne t2,t1,.Lpark
  la a0,success_message
  li a1,0x10020000
1:
  lbu a2,0(a0)
  beqz a2,3f
2:
  lw t0,0(a1)
  bltz t0,2b
  sw a2,0(a1)
  addi a0,a0,1
  j 1b
3:
  IRIS_UART_DRAIN
  la t0,tohost
  li t1,1
  sd t1,0(t0)
.Lpark:
  wfi
  j .Lpark
.Lcompare4:
  mv a0,s2
  li t0,4
1:
  lhu t1,0(a0)
  lhu t2,0(a1)
  bne t1,t2,.Lfail
  addi a0,a0,2
  addi a1,a1,2
  addi t0,t0,-1
  bnez t0,1b
  ret
.Lfail:
  la t0,tohost
  li t1,3
  sd t1,0(t0)
  j .Lpark
.section .data,"aw",@progbits
.balign 64
half_inputs: .half 0x3e00,0x3e00,0x3e00,0x3e00,0x4000,0x4000,0x4000,0x4000,0x3800,0x3800,0x3800,0x3800
.balign 64
single_inputs: .word 0x3fc00000,0x3fc00000,0x3fc00000,0x3fc00000,0x40000000,0x40000000,0x40000000,0x40000000,0x3f000000,0x3f000000,0x3f000000,0x3f000000
.balign 64
double_inputs: .dword 0x3ff8000000000000,0x3ff8000000000000,0x3ff8000000000000,0x3ff8000000000000,0x4000000000000000,0x4000000000000000,0x4000000000000000,0x4000000000000000,0x3fe0000000000000,0x3fe0000000000000,0x3fe0000000000000,0x3fe0000000000000
.balign 64
bfloat_inputs: .half 0x3fc0,0x3fc0,0x3fc0,0x3fc0,0x4000,0x4000,0x4000,0x4000,0x3f00,0x3f00,0x3f00,0x3f00
fp8_e4: .byte 0x38,0x40,0,0x80
fp8_e5: .byte 0x3c,0x40,0,0x80
fp8_want: .half 0x3f80,0x4000,0,0x8000
.balign 64
results: .zero 192
completed: .word 0
success_message: .asciz "PASSED CPU_DTYPES scalar/vector FP16/FP32/FP64 on 3 harts; compute BF16/OFP8 conversion\n"
.section .tohost,"aw",@progbits
.balign 64
.globl tohost
tohost: .dword 0
.balign 64
.globl fromhost
fromhost: .dword 0
