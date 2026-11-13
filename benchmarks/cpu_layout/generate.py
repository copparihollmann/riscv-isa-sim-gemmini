#!/usr/bin/env python3
import argparse,pathlib,json,hashlib,itertools
ROOT=pathlib.Path(__file__).resolve().parents[2]
def generate(out):
 out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True);asm=['.section .text.layout,"ax",@progbits','.option push','.option norvc'];decl=[];items=[]
 for mode,offset in itertools.product(('compact','wide'),range(0,64,2)):
  name=f'layout_{mode}_{offset:02d}';label=name+'_loop';begin=name+'_begin';end=name+'_end';asm += ['.balign 64',f'.global {name}',f'.type {name},@function',f'{name}:','mv a3,a0','mv a5,a1','li a4,0','.balign 64',f'.fill {(64+offset-8)//2},2,0x0001',f'{begin}:','csrr t4,minstret',f'{name}_cycle_begin:','csrr t3,mcycle',f'{label}:']
  if mode=='compact':asm += ['.option push','.option rvc','c.addi a4,1','c.addi a5,3','.option pop']
  else:asm += ['addi a4,a4,1','addi a5,a5,3']
  asm += [f'bne a4,a3,{label}',f'{end}:','csrr t5,mcycle','csrr t6,minstret','sd t3,0(a2)','sd t5,8(a2)','sub t6,t6,t4','sd t6,16(a2)','sd a5,24(a2)','sd a4,32(a2)',f'la t0,{label}','sd t0,40(a2)',f'la t0,{name}_cycle_begin','sd t0,48(a2)',f'la t0,{end}','sd t0,56(a2)','ret',f'.size {name},.-{name}']
  decl.append(f'extern void {name}(unsigned,uint64_t,volatile row_t*);');items.append({'mode':mode,'offset':offset,'name':name,'loop_symbol':label,'begin_symbol':name+'_cycle_begin','end_symbol':end,'instruction_widths':[2,2,4] if mode=='compact' else [4,4,4]})
 asm += ['.balign 64','.global layout_noop','.type layout_noop,@function','layout_noop:','csrr t4,minstret','.global layout_noop_begin','layout_noop_begin:','csrr t3,mcycle','.global layout_noop_loop','layout_noop_loop:','.global layout_noop_end','layout_noop_end:','csrr t5,mcycle','csrr t6,minstret','sd t3,0(a2)','sd t5,8(a2)','sub t6,t6,t4','sd t6,16(a2)','sd a1,24(a2)','sd zero,32(a2)','la t0,layout_noop_loop','sd t0,40(a2)','la t0,layout_noop_begin','sd t0,48(a2)','la t0,layout_noop_end','sd t0,56(a2)','ret','.size layout_noop,.-layout_noop','.option pop']
 (out/'layout.S').write_text('\n'.join(asm)+'\n');(out/'functions.inc').write_text('\n'.join(decl)+'\nstatic fn_t functions[64]={'+','.join(x['name'] for x in items)+'};\n');(out/'layout-meta.json').write_text(json.dumps({'schema':'iris.cpu_layout_source.v1','functions':items,'n_values':[16,64,256,1024],'repeats':3,'harts':3,'main_regions':2304,'noop_regions':9,'expected_regions':2313,'fitting_only':True,'global_heldout':False,'formula':'(hart+1)+3*N','counter_boundary':'minstret before mcycle; loop then mcycle before minstret; no host-derived cycles','cache_condition':'Fence.I before first call per mode/offset/N; three immediate calls; entry/padding may warm loop line, no assertion of physically cold tags','loop_offset_target':'loopPC modulo64, not function entry'},indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',default=str(ROOT/'build/cpu-layout-v1'));generate(p.parse_args().output)
