.section .text.init
.globl _start
_start:
  la sp, stack_top
  li t0, 0x6000
  csrs mstatus, t0
  rdcycle s0
  li t0, 7
  li t1, 9
  mul t2, t0, t1
  li t3, 63
  bne t2, t3, fail
  fcvt.s.w ft0, t0
  fcvt.s.w ft1, t1
  fadd.s ft2, ft0, ft1
  fcvt.w.s t4, ft2, rtz
  li t5, 16
  bne t4, t5, fail
  li t0, 3
loop:
  addi t0, t0, -1
  bnez t0, loop
  frflags t0
  fsflags zero
  rdcycle s1
  sub s1, s1, s0
  la t0, result
  sd s1, 0(t0)
  # Emit the architectural counter delta through HTIF's console device.
  # Baseline and annotated Spike must print exactly the same value.
  li t1, 60
  li t3, 0x0101000000000000
print_hex:
  srl t2, s1, t1
  andi t2, t2, 15
  li t4, 10
  bltu t2, t4, digit
  addi t2, t2, 39
digit:
  addi t2, t2, 48
  or t2, t2, t3
  la t0, tohost
  sd t2, 0(t0)
wait_console:
  ld t4, 0(t0)
  bnez t4, wait_console
  addi t1, t1, -4
  bgez t1, print_hex
  li a0, 1
  j exit
fail:
  li a0, 3
exit:
  la t0, tohost
  sd a0, 0(t0)
1: j 1b
.section .tohost,"aw",@progbits
.balign 64
.globl tohost
.globl fromhost
tohost: .dword 0
fromhost: .dword 0
.section .bss
.balign 64
result: .skip 8
.skip 4096
stack_top:
