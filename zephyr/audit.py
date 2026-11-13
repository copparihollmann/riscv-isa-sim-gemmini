#!/usr/bin/env python3
"""Verify the out-of-tree board against the frozen source-backed Iris facts."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from uart_profiles import profile as uart_profile,inputs as uart_inputs

ROOT=Path(__file__).resolve().parents[1]
ZEPHYR=ROOT/"third_party/zephyr"
PIN="cd45a528d3bf81f9c7aa2a63f9fe512eee0881b0"
sys.path.insert(0,str(ZEPHYR/"scripts/dts/python-devicetree/src"))
from devicetree import dtlib


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cells(node,name):return node.props[name].to_nums()


def make_record():
    if subprocess.check_output(["git","-C",str(ZEPHYR),"rev-parse","HEAD"],text=True).strip()!=PIN:
        raise ValueError("Zephyr pin mismatch")
    if subprocess.check_output(["git","-C",str(ZEPHYR),"status","--porcelain"],text=True):
        raise ValueError("Zephyr base must remain clean")
    source=dtlib.DT(str(ROOT/"board/evidence/firesim-dts.dts"))
    board=dtlib.DT(str(ROOT/"zephyr/boards/chipyard/iris/iris.dts"))
    expected_cpu_names={"cpu@0","cpu@1","cpu@2"}
    if set(board.get_node("/cpus").nodes)!=expected_cpu_names:
        raise ValueError("Board must expose exactly the three actual harts")
    memory=json.loads((ROOT/"hardware/memory-paths.json").read_text())
    facts={fact["id"]:fact["value"] for fact in memory["facts"]}
    for hart in range(3):
        old=source.get_node("/cpus/cpu@"+str(hart));new=board.get_node("/cpus/cpu@"+str(hart))
        for prop in ("reg","compatible","riscv,isa","mmu-type"):
            if old.props[prop].value!=new.props[prop].value:
                raise ValueError("Board CPU fact differs: "+str(hart)+" "+prop)
        if cells(new,"clock-frequency")!=[facts["clock-domains-local-elaboration"]["harts_hz"][hart]]:
            raise ValueError("Board CPU clock differs from local elaboration")
    if cells(board.get_node("/cpus"),"timebase-frequency")!=[500000]:
        raise ValueError("Board timer is not 500kHz")
    for path in ("/memory@80000000","/memory@70000000","/memory@70020000","/memory@580000000"):
        if cells(board.get_node(path),"reg")!=cells(source.get_node(path),"reg"):
            raise ValueError("Board physical memory differs: "+path)
    plic=board.get_node("/soc/interrupt-controller@c000000")
    if cells(plic,"reg")!=[0,0xc000000,0,0x4000000] or cells(plic,"riscv,ndev")!=[1] or cells(plic,"riscv,max-priority")!=[1]:
        raise ValueError("Board PLIC dimensions differ")
    uart=board.get_node("/soc/serial@10020000")
    if cells(uart,"reg")!=[0,0x10020000,0,0x1000] or cells(uart,"interrupts")!=[1,1]:
        raise ValueError("Board UART address or source differs")
    if cells(uart,'current-speed')!=[115200]:raise ValueError('Physical board default UART changed')
    if 'uart->div = cfg->sys_clk_freq / cfg->baud_rate - 1;' not in (ZEPHYR/'drivers/serial/uart_sifive.c').read_text():raise ValueError('Review changed Zephyr UART divisor formula')
    profiles={name:uart_profile(name) for name in ['physical','ethan-firesim']}
    annotation=json.loads((ROOT/'zephyr/uart-profile-evidence/firesim-uart-annotation.json').read_text())
    if len(annotation['annotations'])!=1 or annotation['annotations'][0]['widgetConstructorKey']['div']!=135:raise ValueError('Review FireSim fixed UART bridge key')
    sources=["west.yml","arch/riscv/core/reset.S","arch/riscv/core/smp.c","arch/riscv/core/fpu.c",
             "arch/riscv/core/isr.S","include/zephyr/arch/riscv/thread.h","soc/rocketchip/virt_riscv/common/soc.c",
             "soc/rocketchip/virt_riscv/common/soc.h","drivers/timer/riscv_machine_timer.c",
             "drivers/interrupt_controller/intc_plic.c","drivers/serial/uart_sifive.c","drivers/serial/uart_htif.c"]
    inputs=[ROOT/"board/evidence/firesim-dts.dts",ROOT/"hardware/memory-paths.json",ROOT/"hardware/dtypes.json"]
    inputs += [path for base in (ROOT/"zephyr/boards",ROOT/"zephyr/dts") for path in base.rglob("*") if path.is_file()]
    inputs += uart_inputs('physical')+uart_inputs('ethan-firesim')
    inputs=sorted(set(inputs))
    def citation(name,locator):return {"path":name,"sha256":sha(ROOT/name),"locator":locator}
    return {"schema_version":1,"status":"verified_source_board_facts","zephyr_url":"https://github.com/ucb-bar/zephyr.git","zephyr_sha":PIN,
            "generator_sha256":sha(Path(__file__)),"input_sha256":{str(path.relative_to(ROOT)):sha(path) for path in sorted(inputs)},
            "zephyr_source_sha256":{name:sha(ZEPHYR/name) for name in sources},
            "hardware_repositories":memory["repositories"],"harts":[0,1,2],"pmp_regions":facts["per-hart-pmp"]["entries"],
            "fact_sources":{
                "harts":citation("board/evidence/firesim-dts.dts","/cpus/cpu@0,/cpus/cpu@1,/cpus/cpu@2 reg and compatible"),
                "memory_map":citation("board/evidence/firesim-dts.dts","/memory@80000000,/memory@70000000,/memory@70020000,/memory@580000000 reg"),
                "pmp_regions":citation("hardware/memory-paths.json","facts[id=per-hart-pmp] and its source/line evidence"),
                "mtime_hz":citation("board/evidence/firesim-dts.dts","/cpus timebase-frequency=500000"),
                "local_elaboration_hart_hz":citation("hardware/memory-paths.json","facts[id=clock-domains-local-elaboration] and its source/line evidence"),
                "kernel_policy":citation("zephyr/boards/chipyard/iris/iris_defconfig","SMP/MP_MAX_NUM_CPUS/RISCV_PMP/FPU/FPU_SHARING configuration"),
                "uart_plic":citation("board/evidence/firesim-dts.dts","/soc/serial@10020000 interrupts=1; /soc/interrupt-controller@c000000"),
                "completion":citation("third_party/zephyr/soc/rocketchip/virt_riscv/common/soc.c","sys_arch_reboot under CONFIG_UART_HTIF: tohost=((success<<1)|1), success=0"),
                "vector_context_gap":citation("third_party/zephyr/arch/riscv/core/fpu.c","z_riscv_vstate_restore modifies input pointer then calls CSR restore; no matrix tile/config state")},
            "mtime_hz":500000,"local_elaboration_hart_hz":facts["clock-domains-local-elaboration"]["harts_hz"],
            "uart_deployment_profiles":profiles,"ethan_firesim_uart_hardware_validated":False,
            "kernel_policy":{"machine_mode":True,"userspace":False,"pmp":False,"scalar_common_isa":"RV64IMAFDC_Zicsr_Zifencei",
                             "fpu_sharing":True,"vector_context_certified":False,"vme_context_certified":False},
            "binding_adaptations":["Zephyr PLIC second interrupt cell expresses software priority, physical source remains1",
                                   "Existing RISC-V CPU schemas are extended only for actual compatible names/PMP metadata",
                                   "Only DRAM is chosen as kernel SRAM; TCM/scratchpad remain explicitly mapped but are not autoallocated"],
            "completion_source":"soc/rocketchip/virt_riscv/common/soc.c sys_arch_reboot with CONFIG_UART_HTIF writes tohost=1",
            "modules_required_for_scalar_build":[],"rtl_certified":False,"timing_certified":False,
            "remaining":["Actual FPGA Zephyr validation and source/image association","VME tile/config save/restore or explicit exclusive ownership contract",
                         "RVV context restore input-pointer mutation needs disassembly/runtime proof before enabling vector sharing",
                         "UART driver uses3bit watermark configuration (current threshold1 is valid in256entry hardware)"]}


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument("--verify",action="store_true");args=p.parse_args()
    path=ROOT/"zephyr/source-audit.json";data=make_record()
    if args.verify:
        if json.loads(path.read_text())!=data:raise ValueError("Zephyr source board audit is stale")
    else:path.write_text(json.dumps(data,indent=2)+"\n")
    print(json.dumps({"status":data["status"],"harts":data["harts"],"zephyr_sha":PIN,"rtl_certified":False}))


if __name__=="__main__":main()
