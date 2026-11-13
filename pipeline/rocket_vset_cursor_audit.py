#!/usr/bin/env python3
"""Bind the diagnostic cursor instructions to source Rocket bypass control."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    folder=ROOT/'build/zephyr-hart2-vreg-shift64-v1';layout=folder/'layout-slack-proof.json';proof=json.loads(layout.read_text());elf=folder/'shift64/zephyr/zephyr.elf';disassembly=folder/'shift64/disassembly.txt'
    if sha(elf)!=proof['shift_elf_sha256']or not proof['only_two_ADDI_immediate_words_change_loaded_payload']:raise ValueError('diagnostic ELF/layout changed')
    instructions={int(m[1],16):int(m[2],16)for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',disassembly.read_text(),re.M)};rows=[]
    for name,vset,mem,add,vlreg in [('save',0x800029c6,0x800029ca,0x800029ce,14),('restore',0x80002a48,0x80002a4c,0x80002a50,13)]:
        v=instructions[vset];memory=instructions[mem];cursor=instructions[add]
        if v&0x707f!=0x7057 or (v>>15)&31 or (v>>7)&31!=vlreg or v>>20!=0xc3:raise ValueError('actual diagnostic vsetvli encoding differs')
        if memory&127!=(0x27 if name=='save'else 7)or(memory>>12)&7 or(memory>>15)&31!=15:raise ValueError('actual diagnostic vector memory operand differs')
        if cursor&0xf003!=0x9002 or(cursor>>7)&31!=15 or(cursor>>2)&31!=vlreg:raise ValueError('actual compressed cursor ADD differs')
        rows.append(dict(function=name,vset_pc=vset,vset_raw=v,nonzero_rd=vlreg,avl_rs1=0,vtype_imm=0xc3,vector_memory_pc=mem,vector_memory_raw=memory,cursor_add_pc=add,cursor_add_raw=cursor,cursor_rd_rs1=15,cursor_rs2=vlreg,configured_VLEN=256,source_VLMAX_e8_m8=256))
    evidence=[
      ('third_party/saturn/src/main/scala/rocket/Configs.scala',[[35,40]],'Saturn Rocket sets issueVConfig=false.'),
      ('third_party/saturn/src/main/scala/frontend/EarlyDecode.scala',[[13,20],[37,40],[58,69]],'funct3=7 VSET is excluded from vector arithmetic; vector loads/stores do not write a scalar rd.'),
      ('third_party/rocket-chip/src/main/scala/rocket/IDecode.scala',[[19,45],[437,443]],'VCFGDecode gives VSETVLI scalar WXD=true, CSR.N and no memory/FP/divider class.'),
      ('third_party/rocket-chip/src/main/scala/rocket/RocketCore.scala',[[356,365],[464,480],[498,531],[680,700],[787,794],[846,855],[920,924],[1030,1058],[1170,1177]],'EX newVL is muxed into MEM write-data; scalar bypass uses that value. Vconfig interlock stalls following vector ID until the config leaves EX/MEM/WB. Scalar scoreboard is not allocated for scalar VSET.'),
      ('build/rtl-verilator/gen-collateral/Rocket.sv',[[683,697],[736,738],[1180,1182],[1707,1714]],'Actual saved elaboration emits no VSET forwarding to Saturn EX when issueVConfig=false; source MEM write-data selects ex_new_vl.'),
    ]
    inputs=[Path(__file__).resolve(),layout,elf,disassembly]+[ROOT/name for name,_,_ in evidence];hashes={str(p):sha(p)for p in inputs};archive=out/'inputs';archive.mkdir()
    for path in inputs:
        dest=archive/hashes[str(path)]
        if not dest.exists():shutil.copy2(path,dest)
    report=dict(schema='iris.rocket.vset_cursor_source_audit.v1',status='source_scalar_VL_bypass_path_present',input_sha256=hashes,original_elf_sha256=proof['original_elf_sha256'],shift_elf_sha256=proof['shift_elf_sha256'],source_pins=dict(rocket_chip='fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0',saturn='536774bd4c5e3bcd7813a4a0dc72fc87e5818532'),instructions=rows,evidence=[dict(path=str(ROOT/name),sha256=hashes[str(ROOT/name)],lines=lines,fact=fact)for name,lines,fact in evidence],inferences=[
        'For an immediate scalar ADD dependent on VSETVLI rd, ID may select EX bypass, then consumer EX reads producer MEM write-data containing newVL. The source does not require an extra scalar RAW bubble.',
        'The actual diagnostic loop has a vector memory instruction between VSETVLI and cursor ADD. That vector ID is held by id_vconfig_hazard until the preceding VSET leaves WB; the VL scalar RF write therefore precedes the following cursor ADD.',
        'There is no source-evident scalar scoreboard allocation for ordinary VSETVLI or scalar rd write from these vector memory instructions. This is not a proof excluding every CPU/Saturn interaction.'
      ],open_interactions=[
        'Rocket replay_wb_vec is wb_reg_valid && vector.wb.replay without a wb_ctrl.vec guard; actual Saturn WB replay token validity/ownership must still be verified.',
        'Source-only forwarding analysis does not determine the actual FPGA stall cause, runtime VLEN, loaded image identity, cache behavior or VMU page fission.'
      ],hardware_contacted=False,physical_root_cause_confirmed=False,all_CPU_hazards_ruled_out=False,timing_certified=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],report_sha256=sha(out/'report.json'))))
if __name__=='__main__':main()
