#!/usr/bin/env python3
"""Read actual ELF/DWARF buffer layout; never infer an executed restore/LSU fault."""
import argparse,hashlib,json,sys
from pathlib import Path
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def inspect(path):
 with path.open('rb')as f:
  e=ELFFile(f);sym=[s for s in e.get_section_by_name('.symtab').iter_symbols()if s.name=='workers'];assert len(sym)==1;sizes={};offsets={}
  for cu in e.get_dwarf_info().iter_CUs():
   for d in cu.iter_DIEs():
    a=d.attributes
    if d.tag!='DW_TAG_structure_type'or'DW_AT_name'not in a or'DW_AT_byte_size'not in a:continue
    name=a['DW_AT_name'].value.decode()
    if name not in ['k_thread','_thread_arch','z_riscv_v_context']or name in sizes:continue
    sizes[name]=a['DW_AT_byte_size'].value
    for c in d.iter_children():
     a=c.attributes
     if'DW_AT_name'in a and'DW_AT_data_member_location'in a:offsets[name+'.'+a['DW_AT_name'].value.decode()]=a['DW_AT_data_member_location'].value
  stride=sizes['k_thread'];assert sym[0]['st_size']==3*stride;ctx=offsets['k_thread.arch']+offsets['_thread_arch.saved_v_context'];vr=offsets['z_riscv_v_context.vreg'];assert vr==40
  rows=[]
  for h in range(3):
   base=sym[0]['st_value']+h*stride;cursor=base+ctx+vr;dlen=16 if h<2 else 32;groups=[]
   for g in range(4):
    a=cursor+g*256;b=a+256;fragments=[]
    while a<b:
     end=min(b,(a//4096+1)*4096);fragments.append(dict(address=a,bytes=end-a));a=end
    groups.append(dict(group=g,start=cursor+g*256,bytes=256,page_fragments=fragments))
   rows.append(dict(worker=h,pinned_physical_hart=h,thread_base=base,context_base=base+ctx,vreg_start=cursor,configured_DLEN_bytes=dlen,mod_DLEN=cursor%dlen,mod32=cursor%32,mod4096=cursor%4096,logical_context_copy_bytes=1024,allocated_vreg_bytes=offsets['z_riscv_v_context.iris_mtype']-vr,groups=groups,actual_restore_reached=False))
  return dict(ELF_sha256=sha(path),workers_address=sym[0]['st_value'],thread_stride=stride,context_offset=ctx,vreg_offset=vr,workers=rows)
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();assert not out.exists();out.mkdir(parents=True)
 paths=[ROOT/'build/zephyr-firesim-uart/5e6/mixed-build/zephyr/zephyr.elf',ROOT/'build/zephyr-mixed9-firstuse-normal-v1/zephyr/zephyr.elf',ROOT/'build/zephyr-mixed9-firstuse-normal-v2/zephyr/zephyr.elf'];r=dict(schema='iris.Zephyr_actual_context_buffer_layout.v1',**{'pass':True},variants=[dict(path=str(x),**inspect(x))for x in paths],scope='Compiled potential perworker context buffers only; actual restore reached/transaction/fault/stalledPC not established',alignment_requirement_or_hardware_bug_claimed=False,V1_to_V2_control_scope='V2 changes ready handshake and adds a semaphore object/layout; passing V2 does not isolate the busy-poll instruction as the V1 failure cause.',hardware_contacted=False,protected_timing_labels_consumed=False,input_sha256={str(x):sha(x)for x in [Path(__file__).resolve(),*paths]});(out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(report_sha256=sha(out/'report.json'),variants=[dict(ELF=x['ELF_sha256'][:8],mod_DLEN=[w['mod_DLEN']for w in x['workers']],mod4096=[w['mod4096']for w in x['workers']])for x in r['variants']])))
if __name__=='__main__':main()
