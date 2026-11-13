#!/usr/bin/env python3
"""Prove WFI/mcycle ungated-clock semantics on the two actual saved CSR units."""
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
    lines=['module WfiPair(input clock,ungated_clock,reset,input [11:0] address,input [31:0] instruction,input [2:0] cmd,input [63:0] write_data,input [1:0] retire,input msip,mtip,output [63:0] shuttle_data,rocket_data,output shuttle_stall,rocket_stall);'];sources=[]
    for module,prefix in [('CSRFile','shuttle'),('CSRFile_2','rocket')]:
        source=ROOT/'build/rtl-verilator/gen-collateral'/f'{module}.sv';target=out/source.name;shutil.copy2(source,target);sources.append(target)
        ports=re.findall(r'^\s*(input|output)\s*(?:\[[^]]+\]\s*)?(\w+)\s*[,)]',target.read_text(),re.M)
        selected={'clock':'clock','reset':'reset','io_ungated_clock':'ungated_clock','io_rw_addr':'address','io_rw_cmd':'cmd','io_rw_wdata':'write_data','io_retire':'retire' if prefix=='shuttle' else 'retire[0]','io_decode_0_inst':'instruction','io_rw_rdata':prefix+'_data','io_csr_stall':prefix+'_stall','io_interrupts_msip':'msip','io_interrupts_mtip':'mtip'}
        if not set(selected).issubset({n for _,n in ports}):raise ValueError('CSR source clock/wake boundary changed')
        mappings=[]
        for kind,name in ports:
            expression=selected.get(name,"'0" if kind=='input' else '')
            mappings.append(f'.{name}({expression})')
        lines.append(module+' '+prefix+'('+','.join(mappings)+');')
    lines.append('endmodule');top=out/'WfiPair.sv';top.write_text('\n'.join(lines)+'\n')
    perl=Path('/scratch/eygao/iris-cy/.conda-env/bin/perl');tool=perl.with_name('verilator');compiler=Path(shutil.which('g++')).resolve();test=ROOT/'pipeline/test_frontend_clock.cpp';obj=out/'obj'
    commands=[[str(perl),str(tool),'--cc','--exe','-Wno-fatal','--top-module','WfiPair','--Mdir',str(obj),str(top),*[str(s)for s in sources],str(test),'-CFLAGS','-std=c++20 -O2'],['make','-C',str(obj),'-f','VWfiPair.mk','-j8','CXX='+str(compiler),'LINK='+str(compiler),'AR=ar']]
    for i,cmd in enumerate(commands):
        r=subprocess.run(cmd,text=True,capture_output=True);(out/f'build-{i}.log').write_text(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError('WFI source component build failed: '+r.stderr[-1000:])
    binary=obj/'VWfiPair';r=subprocess.run([str(binary)],text=True,capture_output=True);(out/'transcript.jsonl').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
    if r.returncode:raise RuntimeError('WFI clock source rule failed: '+r.stderr)
    rows=[json.loads(line)for line in r.stdout.splitlines()]
    evidence=[]
    for repo,name,spans in [('rocket-chip','src/main/scala/rocket/CSR.scala',[[646,650],[1090,1095],[1231,1233]]),('rocket-chip','src/main/scala/rocket/RocketCore.scala',[[166,174],[1222,1233]]),('shuttle','src/main/scala/exu/Core.scala',[[58,62],[470,480]]),('shuttle','src/main/scala/common/Tile.scala',[[293,306]])]:
        source=ROOT/'third_party'/repo/name;target=out/'source'/repo/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        evidence.append(dict(path=str(source),snapshot=str(target),sha256=sha(source),lines=spans,repository_commit=subprocess.check_output(['git','-C',str(ROOT/'third_party'/repo),'rev-parse','HEAD'],text=True).strip()))
    report=dict(schema='iris.frontend.source_wfi_counter_clock.v1',status='passed_actual_CSR_WFI_ungated_clock_proof',transactions=len(rows),rows=rows,input_sha256={str(p):sha(p)for p in [Path(__file__).resolve(),test,top,*sources,perl,tool,compiler]},evidence=evidence,commands=commands,binary_sha256=sha(binary),
                findings=['mcycle increments on ungated edges only when pre-edge csr_stall isfalse and CY inhibit isclear','WFI entry edge counts; parked edges and wake edge hold; following ungated edge resumes','Locally enabled MSIP clears WFI even with global MIEzero and pipeline clockheldlow','mcycle can run with pipeline clockheldlow when CSRstall isfalse; Rocket pipeline clock gate alone isnot mcycle gate','CY inhibit uses its old value on the CSR write edge; clearing takes effect on subsequent ungated edge'],
                native_counter_policy_changed=False,clint_rtl_tested=False,ethan_image_association_verified=False,full_cpu_clocking_certified=False,calibrated=False,held_out_2pct=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],transactions=len(rows))))
if __name__=='__main__':main()
