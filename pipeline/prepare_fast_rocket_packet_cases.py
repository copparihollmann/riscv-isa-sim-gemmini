#!/usr/bin/env python3
"""Extract actual instruction bytes for parcel-flow tests, never cycle labels."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from iris_model.guest_regions import Instructions
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);elf=ROOT/'build/cpu-layout-v2/batch.elf';proof=ROOT/'build/cpu-layout-v2/binary-proof.json';insns=Instructions(elf);facts=json.loads(proof.read_text());rows=[]
 def word(address):
  for base,data in insns.ranges:
   if base<=address and address+4<=base+len(data):return int.from_bytes(data[address-base:address-base+4],'little')
  raise ValueError('Unmapped real ELF word')
 for f in facts['functions']:
  start=f['loop_pc'];end=f['end_pc'];base=start&~3;words=[word(pc)for pc in range(base,(end+3)&~3,4)]
  assert len(words)<=4;pc=start
  for raw,width in zip(f['opcode_words'],f['instruction_widths']):assert insns.read(pc)==raw;pc+=width
  assert pc==end;rows.append({'pc':start,'base':base,'words':words,'raw':f['opcode_words'],'widths':f['instruction_widths']})
 header='#pragma once\n#include <cstdint>\nstruct PacketCase{uint64_t pc,base;unsigned count;uint32_t words[4],raw[3];unsigned widths[3];};\ninline const PacketCase packet_cases[]={\n'
 for r in rows:header+='{'+str(r['pc'])+'ull,'+str(r['base'])+'ull,'+str(len(r['words']))+',{'+','.join(hex(x)+'u'for x in r['words'])+'},{'+','.join(hex(x)+'u'for x in r['raw'])+'},{'+','.join(map(str,r['widths']))+'}},\n'
 header+='};\n';(out/'cases.hpp').write_text(header);inputs=[Path(__file__).resolve(),elf,proof,ROOT/'iris_model/guest_regions.py'];r={'schema':'iris.fast_rocket_packet_cases.v1','pass':True,'cases':len(rows),'contains_timing_labels':False,'source':'unchanged actualCPUlayoutELF instruction bytes','input_sha256':{str(x):hashlib.sha256(x.read_bytes()).hexdigest()for x in inputs},'header_sha256':hashlib.sha256(header.encode()).hexdigest()};(out/'report.json').write_text(json.dumps(r,indent=2)+'\n')
if __name__=='__main__':main()
