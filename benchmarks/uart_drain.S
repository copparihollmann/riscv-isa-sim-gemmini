/* Same source-clock/maximum-frame contract as uart_drain.h.
 * Clobbers t0..t6; producers must be quiescent and controls held during drain.
 */
.macro IRIS_UART_DRAIN
  li t0,0x10020000
  lw t1,8(t0)
  li t2,0x1ff0000
  not t2,t2
  and t1,t1,t2
  li t2,0x10000
  or t1,t1,t2
  sw t1,8(t0)
  fence rw,rw
.Luart_empty\@:
  lw t1,20(t0)
  andi t1,t1,1
  beqz t1,.Luart_empty\@
  lw t1,24(t0)
  li t2,0xffff
  and t1,t1,t2
  addi t1,t1,1
  li t2,11
  mul t1,t1,t2
  li t2,66535
  add t1,t1,t2
  li t2,1000
  divu t1,t1,t2
  addi t1,t1,1
  li t3,0x200bff8
  ld t4,0(t3)
.Luart_guard\@:
  ld t5,0(t3)
  sub t5,t5,t4
  bltu t5,t1,.Luart_guard\@
  fence rw,rw
.endm
