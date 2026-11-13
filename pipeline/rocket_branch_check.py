#!/usr/bin/env python3
"""Differential-check Rocket MEM control against exact emitted source expressions."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(exist_ok=False,parents=True)
    source=ROOT/'build/rtl-verilator/gen-collateral/Rocket.sv';text=source.read_text();definitions={};widths={}
    for line in text.splitlines():
        line=line.split('//',1)[0].strip()
        declaration=re.match(r'(?:input|output|wire|reg)\s*(\[[0-9:]+\])?\s+(\w+)\b',line)
        if declaration:widths[declaration[2]]=declaration[1]or''
        d=re.match(r'(?:wire\s*(?:\[[0-9:]+\])?\s+|assign\s+)(\w+)\s*=\s*(.*);$',line)
        if d:definitions[d[1]]=d[2]
    # Preserve the exact integer/FPU WB-data expression; the test explicitly
    # supplies integer-only control. No RTL register state is reinjected.
    expressions=re.findall(r'wb_reg_wdata <= (.*?);',text)
    if len(expressions)!=1:raise ValueError('source Rocket WB-data cone changed')
    definitions['source_mem_int_wdata']=expressions[0];widths['source_mem_int_wdata']='[63:0]'
    leaves=['mem_reg_inst','mem_reg_pc','mem_reg_wdata','mem_reg_rvc','mem_ctrl_branch','mem_ctrl_jal','mem_ctrl_jalr','mem_ctrl_fp','mem_ctrl_wxd','mem_reg_sfence','mem_br_taken','mem_reg_valid','mem_reg_xcpt','ex_reg_valid','ex_reg_replay','ex_reg_xcpt_interrupt','ex_reg_pc','_ibuf_io_inst_0_valid','io_imem_resp_valid','_ibuf_io_pc','take_pc_wb','_csr_io_status_isa','io_fpu_toint_data']
    roots={'next_pc':'mem_npc','wrong_npc':'mem_wrong_npc','take_pc':'take_pc_mem','int_wdata':'source_mem_int_wdata','btb_update':'io_imem_btb_update_valid','btb_valid':'io_imem_btb_update_bits_isValid','cfi_type':'io_imem_btb_update_bits_cfiType','branch_pc':'io_imem_btb_update_bits_br_pc','fetch_pc':'io_imem_btb_update_bits_pc','bht_update':'io_imem_bht_update_valid'}
    selected={}
    def visit(name):
        if name in leaves or name in selected:return
        if name not in definitions:raise ValueError('unclassified source cone signal: '+name)
        selected[name]=definitions[name]
        for token in re.findall(r'\b[A-Za-z_]\w*\b',definitions[name]):
            if token in widths:visit(token)
            elif token not in ('h0','h1','h2','h3','h4','hFFFFFFFFFE'): # literal fragments are ignored below
                if token in definitions:visit(token)
    for name in roots.values():visit(name)
    top=out/'RocketMemControl.sv';ports=['input '+widths[name]+' '+name for name in leaves]+['output '+widths[source]+' out_'+name for name,source in roots.items()]
    top.write_text('module RocketMemControl('+','.join(ports)+');\n'+''.join('wire '+widths[n]+' '+n+';\nassign '+n+' = '+e+';\n'for n,e in selected.items())+''.join('assign out_'+n+' = '+v+';\n'for n,v in roots.items())+'endmodule\n')
    test=ROOT/'pipeline/test_rocket_branch.cpp';tool=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator');perl=tool.with_name('perl');compiler=Path(shutil.which('g++')).resolve();obj=out/'obj'
    commands=[[str(perl),str(tool),'--cc','--exe','-Wno-fatal','--top-module','RocketMemControl','--Mdir',str(obj),str(top),str(test),'-CFLAGS','-std=c++20 -O2 -I'+str(ROOT/'pipeline')],['make','-C',str(obj),'-f','VRocketMemControl.mk','-j8','CXX='+str(compiler),'LINK='+str(compiler),'AR=ar']]
    for i,argv in enumerate(commands):
        r=subprocess.run(argv,text=True,capture_output=True);(out/f'build-{i}.log').write_text(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError('source Rocket MEM cone build failed: '+r.stderr[-4000:])
    binary=obj/'VRocketMemControl';r=subprocess.run([str(binary)],text=True,capture_output=True);(out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode:raise RuntimeError('source Rocket MEM differential failed: '+r.stderr)
    findings=json.loads(r.stdout);inputs=[Path(__file__).resolve(),source,top,test,ROOT/'pipeline/rocket_branch.hpp',ROOT/'third_party/rocket-chip/src/main/scala/rocket/RocketCore.scala',tool,perl,compiler]
    archive=out/'inputs';archive.mkdir();hashes={str(p):sha(p)for p in inputs}
    for path in inputs:
        dest=archive/hashes[str(path)]
        if not dest.exists():shutil.copy2(path,dest)
    report=dict(schema='iris.rocket.source_MEM_control_differential.v1',status=findings['status'],findings=findings,source_pin='fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0',source_lines=[[645,659],[1041,1053],[1101,1105],[1124,1142]],input_sha256=hashes,source_cone_leaves=leaves,source_expressions=selected,commands=commands,binary_sha256=sha(binary),scope='Combinational source boundary, C-present integer instructions; random boundary stimuli, no whole-CPU state injection or timing fit.',calibrated=False,rtl_certified=False,held_out_2pct=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(findings))
if __name__=='__main__':main()
