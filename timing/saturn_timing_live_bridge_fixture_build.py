#!/usr/bin/env python3
"""Build explicit synthetic EX-boundary/no-memory ownership driver."""
import argparse,hashlib,json,shutil,struct,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
TC=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--bridge',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();bridge=a.bridge.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copy2(Path(__file__),out/'builder.py');source=R/'timing/saturn_timing_ownership_fixture.S';driver=R/'timing/saturn_timing_live_bridge_fixture.cpp';shutil.copy2(source,out/source.name);shutil.copy2(driver,out/driver.name)
 gcc=TC/'riscv64-unknown-elf-gcc';objcopy=TC/'riscv64-unknown-elf-objcopy';objdump=TC/'riscv64-unknown-elf-objdump';commands=[[str(gcc),'-march=rv64gcv','-mabi=lp64d','-c',str(out/source.name),'-o',str(out/'instructions.o')],[str(objcopy),'-O','binary','--only-section=.text',str(out/'instructions.o'),str(out/'instructions.bin')]]
 for cmd in commands:subprocess.run(cmd,check=True,capture_output=True)
 dis=subprocess.run([str(objdump),'-d',str(out/'instructions.o')],check=True,capture_output=True,text=True);(out/'instructions.disassembly').write_text(dis.stdout);data=(out/'instructions.bin').read_bytes()
 if len(data)!=12:raise ValueError('Expected exactly three whole 32-bit source instructions')
 raw=struct.unpack('<III',data);(out/'ownership_instruction_patterns.hpp').write_text('#pragma once\n#include <array>\n#include <cstdint>\n#define IRIS_FIXTURE_INSTRUCTION_SHA '+json.dumps(sha(out/'instructions.bin'))+'\ninline constexpr std::array<std::uint32_t,3> iris_fixture_instructions={'+','.join(str(x)+'u'for x in raw)+'};\n')
 cmd=['/usr/bin/g++','-O3','-std=c++20','-pthread','-I'+str(out),'-I'+str(bridge/'sdk'),str(out/driver.name),str(bridge/'sdk/libiris_saturn_live_bridge.a'),'-latomic','-lz','-o',str(out/'fixture')];commands.append(cmd)
 with(out/'build.log').open('w')as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
 inputs=[Path(__file__),out/source.name,out/driver.name,bridge/'build.json',bridge/'sdk/libiris_saturn_live_bridge.a',gcc,objcopy,objdump,Path('/usr/bin/g++'),out/'ownership_instruction_patterns.hpp'];result={'schema':'iris.saturn_live_bridge_explicit_EX_fixture_build.v1','argv':commands,'input_sha256':{str(x):sha(x)for x in inputs},'raw_instructions':list(raw),'binary_sha256':sha(out/'fixture'),'synthetic_external_EX_driver':True,'actual_CPU_pipeline':False,'actual_guest_ELF_execution':False,'external_memory_or_FPU_service':False,'RTL_state_driven':False,'hardware_contacted':False};(out/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'binary_sha256':result['binary_sha256']}))
if __name__=='__main__':main()
