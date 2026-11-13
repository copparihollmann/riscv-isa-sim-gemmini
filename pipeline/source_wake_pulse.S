.text
.option push
.option norvc
.global source_wake_pulse
source_wake_pulse:
  li t0,0x02000008
  li t1,1
.global source_wake_pulse_set
source_wake_pulse_set:
  sw t1,0(t0)
.global source_wake_pulse_clear
source_wake_pulse_clear:
  sw zero,0(t0)
  ret
.option pop
