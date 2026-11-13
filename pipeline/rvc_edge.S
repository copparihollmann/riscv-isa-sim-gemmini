.option push
.option norvc
.text
.global rvc_edge
rvc_edge:
  mv t6,a0
  li t3,41
  li t0,0x7003fffe
  jalr zero,0(t0)
.global rvc_edge_resume
rvc_edge_resume:
  sd t3,0(t6)
.global rvc_reserved_pc
rvc_reserved_pc:
  .hword 0x2001 # Reserved RV64 C.ADDIW rd=x0: leave to the ordinary decoder.
  addi t3,t3,1
  sd t3,8(t6)
  ret
.option pop
