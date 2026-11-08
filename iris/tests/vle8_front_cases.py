"""Authored functional cases; no model names, latency fits or hardware calls."""

patterns=[(0x59+13*i)&255 for i in range(64)]
cases=[]
for vl in [1,3,16,32]:cases.append(dict(name='defined_tail_vl'+str(vl),vl=vl,init=True,store_vl=32,expected=patterns[:vl]+[7]*(32-vl),admitted=1))
cases += [dict(name='unknown_tail_unobserved',vl=3,store_vl=3,expected=patterns[:3],admitted=1),dict(name='unknown_tail_required_refuses',vl=3,store_vl=32,refuses=True,admitted=1),dict(name='partial_RAM_unobserved',vl=8,partial=True,store_vl=3,expected=patterns[:3],admitted=1),dict(name='partial_RAM_required_refuses',vl=8,partial=True,store_vl=8,refuses=True,admitted=1),dict(name='masked_fallback',vl=3,init=True,masked=True,store_vl=32,expected=patterns[:3]+[7]*29,admitted=0),dict(name='e16_fallback',vl=3,sew=16,store_vl=3,expected=patterns[:6],admitted=0),dict(name='m2_vl64_fallback',vl=64,lmul=2,store_vl=64,expected=patterns,admitted=0),dict(name='vstart_fallback',vl=3,init=True,vstart=1,store_vl=32,expected=[7]+patterns[1:3]+[7]*29,admitted=0),dict(name='unmapped_load_precise_fault',vl=3,fault='hole',admitted=0),dict(name='PMP_CSR_unimplemented_precise_illegal',vl=3,fault='pmp',admitted=0)]
def setvl(vl,sew=8,lmul=1):return f'li t4,{vl}\nvsetvli zero,t4,e{sew},m{lmul},tu,mu'
def basic_assembly(c):
 seq=[]
 if c.get('init'):seq += [setvl(32),'vmv.v.i v8,7']
 if c.get('masked'):seq += [setvl(32),'vmv.v.i v0,-1']
 if c.get('partial'):seq += ['li a0,0x81000000']+[f'li t1,{patterns[i]}\nsb t1,{i}(a0)' for i in range(3)]
 else:seq += ['la a0,input']
 if c.get('fault'):
  seq+=['la t0,trap_handler','csrw mtvec,t0','li a0,'+('0x60000000' if c['fault']=='hole' else '0x81000000')]
  if c['fault']=='pmp':seq+=['li t0,0x20400003','csrw pmpaddr0,t0','li t0,0x98','csrw pmpcfg0,t0']
 seq += [setvl(c['vl'],c.get('sew',8),c.get('lmul',1))]
 if c.get('vstart'):seq += ['li t0,1','csrw vstart,t0']
 seq += [f"vle{c.get('sew',8)}.v v8,(a0)"+(',v0.t' if c.get('masked') else '')]
 # Overwrite the original address register while data is pending.
 seq += ['li a0,0x81234560','li a1,1']+['addi a1,a1,1']*12
 if c.get('fault'):seq += ['j failed']
 else:
  seq += ['li t0,13','bne a1,t0,failed','fence rw,rw',setvl(c['store_vl'],c.get('sew',8),c.get('lmul',1)),'la t0,output',f"vse{c.get('sew',8)}.v v8,(t0)",'fence rw,rw']
  if c.get('refuses'):seq += ['lbu t1,3(t0)','bne t1,zero,failed']
  for i,b in enumerate(c.get('expected',[])):seq += [f'lbu t1,{i}(t0)',f'li t2,{b}','bne t1,t2,failed']
  seq += ['j passed']
 return '#include "encoding.h"\n.option norelax\n.section .text.init\n.globl _start\n_start:\ncsrr a0,mhartid\nbnez a0,parked\nli t0,MSTATUS_VS|MSTATUS_FS\ncsrs mstatus,t0\n'+ '\n'.join(seq)+'''
trap_handler:
 csrr t0,mcause
 li t1,5
 bne t0,t1,failed
 j passed
passed:
 li t1,1
 j finish
failed:
 li t1,3
finish:
 la t0,tohost
 sd t1,0(t0)
1: j 1b
parked:
 wfi
 j parked
.section .htif,"aw",@progbits
.align 3
.globl tohost
tohost: .dword 0
.globl fromhost
fromhost: .dword 0
.section .data
.align 6
input:
.byte '''+','.join(map(str,patterns))+'''
.align 6
output: .zero 128
'''
cases.append(dict(name='pending_load_IPI_drains',vl=32,store_vl=32,expected=patterns[:32],admitted=1,irq=True))
cases.extend([dict(name='cross32B_safe_fallback',vl=3,offset=31,store_vl=3,expected=patterns[31:34],admitted=0),dict(name='segmented_safe_fallback',vl=3,segmented=True,store_vl=3,expected=patterns[:6:2]+patterns[1:6:2],admitted=0),dict(name='pending_fetch_access_fault_drains',vl=32,store_vl=32,expected=patterns[:32],fetch_fault=True,admitted=1)])
def assembly(c):
 s=basic_assembly(c)
 if c.get('offset'):s=s.replace('la a0,input','la a0,input\naddi a0,a0,'+str(c['offset']))
 if c.get('segmented'):s=s.replace('vle8.v v8,(a0)','vlseg2e8.v v8,(a0)').replace('vse8.v v8,(t0)','vse8.v v8,(t0)\naddi t0,t0,3\nvse8.v v9,(t0)\naddi t0,t0,-3')
 if c.get('fetch_fault'):
  s=s.replace('csrs mstatus,t0\n','csrs mstatus,t0\nla t0,trap_handler\ncsrw mtvec,t0\n',1).replace('li a0,0x81234560','li t0,0x60000000\njr t0\nli a0,0x81234560').replace(' li t1,5\n bne t0,t1,failed',' li t1,1\n bne t0,t1,failed')
  check='li t4,32\nvsetvli zero,t4,e8,m1,tu,mu\nla t0,output\nvse8.v v8,(t0)\nfence rw,rw\n'
  for i,b in enumerate(patterns[:32]):check+=f'lbu t1,{i}(t0)\nli t2,{b}\nbne t1,t2,failed\n'
  s=s.replace(' j passed\npassed:',check+' j passed\npassed:')
 if c.get('fault')=='pmp':s=s.replace(' li t1,5\n bne t0,t1,failed',' li t1,2\n bne t0,t1,failed')
 if c.get('irq'):
  s=s.replace('li a0,0x81234560\nli a1,1','li a0,0x81234560\nli a1,256\nh0_hold:\naddi a1,a1,-1\nbnez a1,h0_hold\nli a1,1')
  s=s.replace('bnez a0,parked','li t0,1\nbeq a0,t0,hart1_task\nbnez a0,parked',1)
  s=s.replace('csrs mstatus,t0\n','csrs mstatus,t0\nla t0,irq_handler\ncsrw mtvec,t0\nli t0,MIP_MSIP\ncsrs mie,t0\nli t0,MSTATUS_MIE\ncsrs mstatus,t0\nready_wait:\nla t0,irq_ready\nlw t1,0(t0)\nbeqz t1,ready_wait\nla t0,irq_go\nli t1,1\nsw t1,0(t0)\n',1)
  s=s.replace('li t0,13\nbne a1,t0,failed','irq_wait:\nla t0,irq_seen\nlw t1,0(t0)\nbeqz t1,irq_wait\nli t0,13\nbne a1,t0,failed')
  extra='hart1_task:\nla t0,irq_go\nlw t1,0(t0)\nla t0,irq_ready\nli t1,1\nsw t1,0(t0)\nhart1_go_wait:\nla t0,irq_go\nlw t1,0(t0)\nbeqz t1,hart1_go_wait\nli t2,32\nhart1_delay:\naddi t2,t2,-1\nbnez t2,hart1_delay\nli t0,0x2000000\nli t1,1\nsw t1,0(t0)\nj parked\nirq_handler:\ncsrr t3,mcause\nli t4,0x8000000000000003\nbne t3,t4,failed\nli t3,0x2000000\nsw zero,0(t3)\nla t3,irq_seen\nli t4,1\nsw t4,0(t3)\nmret\n'
  s=s.replace('trap_handler:',extra+'trap_handler:')
  s+='\n.align 6\nirq_go: .word 0\nirq_seen: .word 0\nirq_ready: .word 0\n'
 return s


CASES = tuple(cases)
