.option push
.option norvc
.text
.global irq_stream
irq_stream:
  mv t6,a0
  li t3,0
  li t4,0
  csrr t0,mcycle
  csrr t1,minstret
  li a2,1
  sd a2,0(a1)
.global irq_stream_begin
irq_stream_begin:
.rept 2048
  addi t3,t3,1
  addi t4,t4,3
.endr
.global irq_stream_end
irq_stream_end:
  csrr t2,mcycle
  csrr t5,minstret
  sub t2,t2,t0
  sub t5,t5,t1
  sd t2,0(t6)
  sd t5,8(t6)
  sd t3,16(t6)
  sd t4,24(t6)
  ret
.global emit_pulse
emit_pulse:
  li t0,0x02000000
  li t1,1
.global pulse_set
pulse_set:
  sw t1,0(t0)
#ifndef IRIS_ROCKET_PULSE
  addi zero,zero,0
#endif
.global pulse_clear
pulse_clear:
  sw zero,0(t0)
  ret
.global edge_word
edge_word:
  addi t3,t3,1
.global edge_fetch
edge_fetch:
  mv t6,a0
  li t3,41
  li t0,0x7003fffc
  jalr zero,0(t0)
.global edge_resume
edge_resume:
  sd t3,0(t6)
  ret
 .global illegal_sequence
illegal_sequence:
  mv t6,a0
  li t3,13
  addi t3,t3,7
.global illegal_pc
illegal_pc:
  .word 0x0000000b
  addi t3,t3,1
  sd t3,0(t6)
  ret
.option pop
