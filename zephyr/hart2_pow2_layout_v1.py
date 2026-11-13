#!/usr/bin/env python3
"""Derive final packet readback layout from actual ELF symbols and DWARF."""
import argparse,hashlib,json
from pathlib import Path
from elftools.elf.elffile import ELFFile
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def derive(a):
 elf=a.build.resolve()/'zephyr/zephyr.elf';out=a.output.resolve();out.mkdir(parents=True);app=ROOT/'benchmarks/zephyr_hart2_pow2_v4';corpus=json.loads((app/'corpus.json').read_text());proofpath=ROOT/'build/zephyr-hart2-pow2-source-proof-v4/report.json';proof=json.loads(proofpath.read_text());assert proof['ELF_sha256']==sha(elf)and proof['pass']is True
 with elf.open('rb')as f:
  e=ELFFile(f);assert e.elfclass==64 and e.little_endian
  syms={s.name:s for s in e.get_section_by_name('.symtab').iter_symbols()}
  def symbol(name):
   s=syms[name];return dict(address=s['st_value'],address_hex=hex(s['st_value']),size=s['st_size'])
  def raw(name):
   s=syms[name];sec=e.get_section(s['st_shndx']);i=s['st_value']-sec['sh_addr'];return sec.data()[i:i+s['st_size']]
  types={}
  dwarf=e.get_dwarf_info()
  for cu in dwarf.iter_CUs():
   for die in cu.iter_DIEs():
    attr=die.attributes.get('DW_AT_name')
    if die.tag!='DW_TAG_typedef'or not attr:continue
    name=attr.value.decode()
    if name not in ['record_t','descriptor_t','group_t']:continue
    structdie=die.get_DIE_from_attribute('DW_AT_type');fields=[]
    for member in structdie.iter_children():
     if member.tag!='DW_TAG_member':continue
     mt=member.get_DIE_from_attribute('DW_AT_type')
     while'DW_AT_byte_size'not in mt.attributes:mt=mt.get_DIE_from_attribute('DW_AT_type')
     fields.append(dict(name=member.attributes['DW_AT_name'].value.decode(),offset=member.attributes['DW_AT_data_member_location'].value,bytes=mt.attributes['DW_AT_byte_size'].value))
    value=dict(bytes=structdie.attributes['DW_AT_byte_size'].value,fields=fields)
    if name in types:assert types[name]==value
    types[name]=value
  assert types['record_t']['bytes']==144 and types['descriptor_t']['bytes']==24 and types['group_t']['bytes']==36
  assert [x['offset']for x in types['record_t']['fields']]==list(range(0,144,8))
  anchors={name:symbol(name)for name in ['emit','controller','records','output_data','packet_record_count','packet_measurements_done','descriptors','groups','case_ids','inputs_a','inputs_b']}
  assert anchors['records']['size']==648*types['record_t']['bytes']and anchors['descriptors']['size']==648*24 and anchors['groups']['size']==486*36 and anchors['output_data']['size']==corpus['storage_bytes']
  assert int.from_bytes(raw('packet_measurements_done'),'little')==(1<<64)-1
  anchors['emit']['raw_first_instruction_hex']=raw('emit')[:2].hex();assert raw('emit')[:2]==bytes.fromhex('0571')
  base=anchors['output_data']['address'];descs=[]
  for r in corpus['regions']:
   descs.append(dict(region_index=r['region_index'],group=r['group'],case_id=r['case_id'],hart=r['hart'],record_address=anchors['records']['address']+r['region_index']*144,active_data_address=base+r['data_offset'],active_bytes=r['bytes'],elements=r['elements'],element_bytes=r['element_bytes'],leading_guard_address=base+r['offset'],trailing_guard_address=base+r['data_offset']+r['bytes'],guard_value=0x5ac31e79a64db208,internal_split=r['split']))
  result=dict(schema='iris.zephyr_hart2_pow2_actual_ELF_layout.v1',**{'pass':True},ELF_sha256=sha(elf),byte_order='little',pointer_bytes=8,source_hart=2,postmeasurement_stop=dict(symbol='emit',pc=anchors['emit']['address'],raw_first_instruction_hex=anchors['emit']['raw_first_instruction_hex'],count_address=anchors['packet_record_count']['address'],required_count=648,done_address=anchors['packet_measurements_done']['address'],required_done=0,file_initial_done='UINT64_MAX',normal_UART_HTIF_completion_claimed=False),source_anchor=dict(path=str(app/'src/main.c'),line=next(i for i,s in enumerate((app/'src/main.c').read_text().splitlines(),1)if'packet_record_count=REGIONS;'in s),meaning='controller loop completed all486groups; every worker ack/numeric/guard check stored; count648 thenFENCE then done0 thenFENCE then noinline emit'),compiled_terminal_sequence=dict(count_store_pc=0x800014fe,first_fence_pc=0x80001502,done_store_pc=0x8000150a,final_fence_pc=0x8000150e,emit_call_pc=0x80001512),all_IRIS_REGION_and_DATA_after_all_measurements=True,premeasurement_console='UART_PROFILE plus controller/compute readiness only; no percase/interphase output',symbols=anchors,DWARF_types=types,regions=descs,active_elements=181440,training_eligible=456,protected_validation=192,hardware_contacted=False,calibration_authorized=False,input_sha256={str(p):sha(p)for p in [elf,a.build.resolve()/'build.json',app/'src/main.c',app/'src/packet.h',app/'corpus.json',app/'split.json',proofpath,Path(__file__).resolve()]})
 (out/'layout.json').write_text(json.dumps(result,indent=2)+'\n');return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=derive(a);print(json.dumps(dict(pass_status=r['pass'],stop=r['postmeasurement_stop'],ELF_sha256=r['ELF_sha256'])))
