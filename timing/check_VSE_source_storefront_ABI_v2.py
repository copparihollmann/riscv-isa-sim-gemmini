#!/usr/bin/env python3
"""Prove the unchanged UART-consumed ABI4 domain and actual compatible crossmix."""
from pathlib import Path
import argparse,json,shlex,subprocess
from check_VSE_live_boundary_native_v1 import R,F,execute,sha
B=R/'build/spike-VSE-source-storefront-v2'
P=R/'build/VSE-live-boundary-frozen-e24c891b-v1'
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();o=a.output.resolve();o.mkdir(exist_ok=False);old=R/'pipeline/riscv-isa-sim-VSE-live-boundary-v1';new=R/'pipeline/riscv-isa-sim-VSE-source-storefront-v2';consumed={}
 for n in('riscv/sim.h','riscv/processor.h','riscv/devices.h','riscv/abstract_device.h','riscv/iris_clocked_device.h','riscv/simif.h','riscv/dts.h'):
  assert sha(old/n)==sha(new/n),n;consumed[n]=sha(new/n)
 assert sha(old/'riscv/sim.cc')==sha(new/'riscv/sim.cc')
 deps=shlex.split((B/'uart-plugin.d').read_text().replace('\\\n',' ').split(':',1)[1]);checked=[]
 for word in deps:
  q=Path(word).resolve()
  if q.is_file()and q.is_relative_to(new):
   rel=q.relative_to(new);assert sha(q)==sha(old/rel),str(rel);checked.append(str(rel))
 assert not any(n.endswith('mmu.h')or n.endswith('iris_timing_adapter.h')for n in checked)
 code=o/'consumed_ABI.cpp';code.write_text('''#include <riscv/sim.h>
#include <riscv/processor.h>
#include "clocked_uart.hpp"
extern "C" abstract_interrupt_controller_t* consumed_get_intctrl(const sim_t*s){return s->get_intctrl();}
extern "C" unsigned long consumed_sim_size(){return sizeof(sim_t);}
extern "C" unsigned long consumed_processor_size(){return sizeof(processor_t);}
extern "C" unsigned long consumed_state_size(){return sizeof(state_t);}
extern "C" unsigned long consumed_device_size(){return sizeof(abstract_device_t);}
extern "C" unsigned long consumed_clockdevice_size(){return sizeof(iris_clocked_device_t);}
''');commands=[]
 for name,s,b in[('parent',old,R/'build/spike-VSE-live-boundary-v1'),('child',new,B)]:
  obj=o/(name+'.o');cmd=['g++','-O2','-std=c++20','-I'+str(s),'-I'+str(b),'-I'+str(R/'board'),'-I'+str(R/'board/uart-device'),'-I'+str(s/'riscv'),'-c',str(code),'-o',str(obj)];subprocess.run(cmd,check=True,capture_output=True);commands.append(cmd);subprocess.run(['objcopy','-O','binary','--only-section=.text',str(obj),str(o/(name+'.text'))],check=True);(o/(name+'.disassembly')).write_bytes(subprocess.check_output(['objdump','-dr',str(obj)]))
 assert (o/'parent.text').read_bytes()==(o/'child.text').read_bytes()
 assert len((o/'child.text').read_bytes())>0
 elf=R/'build/VSE-live-boundary-guest-h0-v1/guest.elf';runs={}
 for name,n,u in[('parent-matched',P/'spike',P/'libsifive_uart.so'),('child-matched',B/'spike',B/'libsifive_uart.so'),('parent-childUART',P/'spike',B/'libsifive_uart.so'),('child-parentUART',B/'spike',P/'libsifive_uart.so')]:
  runs[name]=execute(o/name,n,u,F,elf);assert runs[name]['exit_status']==0 and not runs[name]['timed_out']
 for name in runs:
  for file in('stdout','stderr','features.jsonl','async.jsonl','summary.json'):assert(o/name/file).read_bytes()==(o/'parent-matched'/file).read_bytes(),(name,file)
 inputs=[Path(__file__),code,B/'pipeline-build.json',P/'manifest.json',R/'pipeline/uart-plugin-abi4.cc',R/'board/uart-device/clocked_uart.hpp']
 report=dict(schema='iris.VSE_live_boundary_UART_ABI4_audit.v1',**{'pass':True},unchanged_consumed_native_headers=consumed,all_plugin_native_header_dependencies_equal=checked,changed_mmu_and_adapter_not_plugin_dependencies=True,pointee_layout_changes_do_not_change_sim_unique_pointer_layout=True,compiled_get_intctrl_and_size_functions_text_equal=True,compiled_text_sha256=sha(o/'child.text'),native_export_iris_device_clock_abi_v4_unchanged=True,compatible_ABI4_crossmix_actual_normal_exit_and_all_prefix_bytes_equal=True,unqualified_universal_binary_ABI_claim=False,exact_capsule_must_still_pin_own_UART_digest=True,commands=commands,runs=runs,input_sha256={str(x):sha(x)for x in inputs},output_sha256={str(x):sha(x)for x in o.iterdir()if x.is_file()});(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'sha256':sha(o/'report.json')}))
if __name__=='__main__':main()
