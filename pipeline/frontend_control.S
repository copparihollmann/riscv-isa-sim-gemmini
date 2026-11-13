.text
.option push
.option rvc
.global frontend_sfb32
.type frontend_sfb32,@function
frontend_sfb32:
  mv t1,a0
  li t0,0
  .balign 8
  .option norvc
.global frontend_sfb32_branch
frontend_sfb32_branch:
  beq t1,zero,1f
  .option rvc
  c.addi t0,7
1:addi a0,t0,3
  nop
  nop
  nop
  ret
.size frontend_sfb32,.-frontend_sfb32
.global frontend_sfb16
.type frontend_sfb16,@function
frontend_sfb16:
  li t0,0
  .balign 8
.global frontend_sfb16_branch
frontend_sfb16_branch:
  c.beqz a0,1f
  c.addi t0,7
1:addi a0,t0,3
  nop
  nop
  nop
  nop
  ret
.size frontend_sfb16,.-frontend_sfb16
.option norvc
.balign 8
.global frontend_wrongpath
.type frontend_wrongpath,@function
frontend_wrongpath:
  addi t0,zero,1
  addi t1,zero,1
.global frontend_wrongpath_branch
frontend_wrongpath_branch:
  beq t0,t1,1f
  addi a0,a0,1024
.global frontend_wrongpath_counter
frontend_wrongpath_counter:
  csrr t2,mcycle
  .word 0x0000000b
  addi a0,a0,1024
  addi a0,a0,1024
1:addi a0,zero,37
  ret
.size frontend_wrongpath,.-frontend_wrongpath
.balign 8
.global frontend_jalr_link
.type frontend_jalr_link,@function
frontend_jalr_link:
  addi t6,ra,0
  lla t0,1f
  jalr ra,0(t0)
.global frontend_jalr_link_pc
frontend_jalr_link_pc:
  addi a0,zero,999
  jalr zero,0(t6)
1:addi a0,ra,0
  jalr zero,0(t6)
.size frontend_jalr_link,.-frontend_jalr_link
.balign 8
.global frontend_jalr_alias
.type frontend_jalr_alias,@function
frontend_jalr_alias:
  lla t0,1f
  jalr t0,0(t0)
.global frontend_jalr_alias_pc
frontend_jalr_alias_pc:
  addi a0,zero,999
  jalr zero,0(ra)
1:addi a0,t0,0
  jalr zero,0(ra)
.size frontend_jalr_alias,.-frontend_jalr_alias
.option pop
