#!/usr/bin/env python3
"""Required RVV operands refuse unknown state; unselected operands remain unobserved.

Fresh ELFs give every test a fresh unknown VRF. No test initializes the complete
VRF or disables strict checking. Positive generic-ISA replays also check ordinary
Spike behavior, independently of the Iris definedness machinery.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
IRIS = HERE.parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cases():
    rows = []
    for sew in (8, 16, 32):
        for operation in ("vwmulu.vx", "vwmulu.vv", "vwmul.vx", "vwmulsu.vx", "vwaddu.vx", "vwsubu.vx"):
            rows.append(dict(name=operation.replace(".", "_") + "_e" + str(sew), sew=sew, kind=operation))
        rows += [dict(name="wmac_defined_e" + str(sew), sew=sew, kind="vwmaccu.vx", initialize=True),
                 dict(name="wmac_unknown_e" + str(sew), sew=sew, kind="vwmaccu.vx", negative=True),
                 dict(name="wmul_unknown_source_e" + str(sew), sew=sew, kind="vwmulu.vx", negative=True, omit_source=True)]
    for sew in (8, 16, 32, 64):
        for kind in ("merge_partial", "merge_false", "merge_unknown", "merge_x", "merge_i", "move_x", "move_i"):
            rows.append(dict(name=kind + "_e" + str(sew), sew=sew, kind=kind, negative=kind == "merge_unknown"))
    for sew in (16, 32, 64):
        for kind in ("merge_float", "move_float"):
            rows.append(dict(name=kind + "_e" + str(sew), sew=sew, kind=kind))
    rows += [dict(name="copy_unknown_masked_store", sew=32, kind="copy_unknown"),
             dict(name="copy_unknown_required_store", sew=32, kind="copy_unknown", negative=True)]
    return rows


def assembly(row):
    sew, kind = row["sew"], row["kind"]
    n = min(8, 256 // sew)
    values = [i + 1 if i % 2 == 0 else (1 << sew) - i for i in range(n)]
    mask = (1 << (n // 2)) - 1
    instructions = [f"vsetivli zero,{n},e{sew},m1,tu,mu"]
    output_width = sew
    expected = [0] * n
    if kind.startswith("vw"):
        output_width = 2 * sew
        if row.get("initialize"):
            instructions += [f"vsetivli zero,{n},e{output_width},m2,tu,mu", "vmv.v.i v16,1",
                             f"vsetivli zero,{n},e{sew},m1,tu,mu"]
        if not row.get("omit_source"):
            instructions += ["la t0,input", f"vle{sew}.v v8,(t0)"]
        instructions += ["li t1,3"]
        if kind.endswith(".vv"):
            instructions += ["la t0,threes", f"vle{sew}.v v12,(t0)"]
        operands = "v16,t1,v8" if kind == "vwmaccu.vx" else "v16,v8," + ("v12" if kind.endswith(".vv") else "t1")
        instructions += [kind + " " + operands, "la t0,output",
                         f"vsetivli zero,{n},e{output_width},m2,tu,mu", f"vse{output_width}.v v16,(t0)"]
        for i, value in enumerate(values):
            signed = value - (1 << sew) if value & (1 << (sew - 1)) else value
            result = (signed if kind in ("vwmul.vx", "vwmulsu.vx") else value) * 3
            if kind == "vwaddu.vx": result = value + 3
            if kind == "vwsubu.vx": result = value - 3
            if kind == "vwmaccu.vx": result += 1
            expected[i] = result & ((1 << output_width) - 1)
    else:
        instructions += ["la t0,mask", "vlm.v v0,(t0)"]
        if kind in ("merge_partial", "merge_unknown", "copy_unknown"):
            instructions += ["vmv.v.i v10,0"]
            if kind != "merge_unknown":
                instructions += ["la t0,input", f"vle{sew}.v v12,(t0),v0.t"]
            if kind == "copy_unknown":
                instructions += ["vmv.v.v v10,v12"]
            else:
                instructions += ["vmerge.vvm v10,v10,v12,v0"]
            expected = [value if i < n // 2 else 0 for i, value in enumerate(values)]
        elif kind == "merge_false":
            mask = 0
            instructions += ["vmv.v.i v10,0", "vmerge.vvm v10,v10,v12,v0"]
        elif kind in ("merge_x", "merge_i", "merge_float"):
            instructions += ["vmnot.m v0,v0", "la t0,input", f"vle{sew}.v v12,(t0),v0.t",
                             "la t0,mask", "vlm.v v0,(t0)", "li t1,3"]
            if kind == "merge_x": instructions += ["vmerge.vxm v10,v12,t1,v0"]
            if kind == "merge_i": instructions += ["vmerge.vim v10,v12,3,v0"]
            if kind == "merge_float":
                instructions += [{16:"fmv.h.x",32:"fmv.w.x",64:"fmv.d.x"}[sew] + " ft0,zero",
                                 "vfmerge.vfm v10,v12,ft0,v0"]
            expected = [(0 if kind == "merge_float" else 3) if i < n // 2 else value for i, value in enumerate(values)]
        elif kind == "move_x":
            instructions += ["li t1,3", "vmv.v.x v10,t1"]
            expected = [3] * n
        elif kind == "move_i":
            instructions += ["vmv.v.i v10,3"]
            expected = [3] * n
        elif kind == "move_float":
            instructions += [{16:"fmv.h.x",32:"fmv.w.x",64:"fmv.d.x"}[sew] + " ft0,zero", "vfmv.v.f v10,ft0"]
        else:
            raise ValueError(kind)
        masked = ",v0.t" if kind == "copy_unknown" and not row.get("negative") else ""
        instructions += ["la t0,output", f"vse{sew}.v v10,(t0)" + masked]
    size = output_width // 8
    load = {1:"lbu",2:"lhu",4:"lwu",8:"ld"}[size]
    directive = {8:".byte",16:".half",32:".word",64:".dword"}
    check = []
    for i, value in enumerate(expected):
        check += [f"{load} t2,{i * size}(t0)", f"li t3,{value}", "bne t2,t3,failed"]
    return '''#include "encoding.h"
.option norelax
.section .text.init
.globl _start
_start:
 csrr a0,mhartid
 bnez a0,parked
 li t0,MSTATUS_VS | MSTATUS_FS
 csrs mstatus,t0
 csrw frm,zero
''' + "\n".join(instructions + ["fence rw,rw", "la t0,output"] + check) + '''
 li t1,1
 j finish
failed:
 li t1,3
finish:
 la t0,tohost
 sd t1,0(t0)
1: j 1b
parked:
 wfi
 j parked
.section .htif,"aw",@progbits
.align 3
.globl tohost
tohost: .dword 0
.globl fromhost
fromhost: .dword 0
.section .data
.align 6
input:
''' + directive[sew] + " " + ",".join(map(str, values)) + "\nthrees:\n" + directive[sew] + " " + ",".join(["3"] * n) + \
        "\nmask: .word " + str(mask) + "\n.align 6\noutput: .zero " + str(n * size) + "\n"


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--baseline-build", type=Path)
    parser.add_argument("--riscv-gcc", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve();out.mkdir(parents=True, exist_ok=False)
    records = []
    for row in cases():
        source = out / (row["name"] + ".S");source.write_text(assembly(row))
        elf = source.with_suffix(".elf")
        cmd = [str(args.riscv_gcc.resolve()), "-march=rv64gcv_zfh_zvfh", "-mabi=lp64d", "-mno-relax",
               "-nostdlib", "-nostartfiles", "-static", "-Wl,--no-relax", "-I" + str(IRIS.parent / "riscv"),
               "-Wl,-T," + str(HERE / "speculative_fetch.ld"), str(source), "-o", str(elf)]
        # Give ordinary data an explicit loaded section in an owned script.
        linker = out / "rvv_reads.ld"
        if not linker.exists():
            linker.write_text((HERE / "speculative_fetch.ld").read_text().replace(
                '  /DISCARD/', '  . = 0x80003000;\n  .data : { *(.data) } :writable\n  /DISCARD/'))
        cmd[cmd.index("-Wl,-T," + str(HERE / "speculative_fetch.ld"))] = "-Wl,-T," + str(linker)
        built = subprocess.run(cmd, capture_output=True)
        (out / (row["name"] + ".build.stderr")).write_bytes(built.stderr)
        if built.returncode:
            raise RuntimeError("directed assembly did not build: " + row["name"])
        for variant, build in (("fixed", args.build), ("baseline", args.baseline_build)):
            if build is None:
                continue
            run = out / (row["name"] + "-" + variant)
            proc = subprocess.run([sys.executable, str(IRIS / "run.py"), "--build", str(build.resolve()),
                "--profile", "source_os", "--elf", str(elf), "--output", str(run), "--timeout", "30"], capture_output=True)
            (out / (row["name"] + "." + variant + ".launcher.stderr")).write_bytes(proc.stderr)
            receipt = json.loads((run / "run.json").read_text())
            stderr = (run / "stderr").read_text()
            old_false_trap = row["kind"] in ("vwmulu.vx", "vwmulu.vv", "vwmul.vx", "vwmulsu.vx", "vwaddu.vx", "vwsubu.vx",
                                              "merge_partial", "merge_false", "merge_x", "merge_i", "merge_float")
            expected_refusal = bool(row.get("negative") or variant == "baseline" and old_false_trap)
            refused = receipt.get("exit_status") == 1 and not receipt.get("timed_out") and ("IRIS_UNDEFINED_STATE hart=0" in stderr or row["kind"] == "copy_unknown" and row.get("negative") and "IRIS_FRONTEND_UNDEFINED_BRANCH_OPERANDS_UNMODELED" in stderr)
            passed = refused if expected_refusal else receipt.get("pass") and receipt.get("exit_status") == 0
            records.append({**row, "variant": variant, "passed": bool(passed), "expected_refusal": expected_refusal,
                            "ELF_sha256": sha(elf), "receipt": str(run / "run.json"), "exit_status": receipt.get("exit_status")})
            print(row["name"], variant, bool(passed), flush=True)
        if not row.get("negative"):
            generic = out / (row["name"] + "-generic")
            generic.mkdir()
            argv = [str(args.build.resolve() / "spike"), "--isa=rv64gcv_zfh_zvfh_zvl256b", "-p3",
                    "-m0x80000000:0x40000", "--disable-dtb", "--pc=0x80000000", str(elf)]
            completed = subprocess.run(argv, capture_output=True, timeout=30)
            (generic / "stdout").write_bytes(completed.stdout)
            (generic / "stderr").write_bytes(completed.stderr)
            records.append({**row, "variant": "generic", "passed": completed.returncode == 0,
                            "expected_refusal": False, "ELF_sha256": sha(elf), "argv": argv,
                            "exit_status": completed.returncode})
    report = {"schema":"iris.rvv_operand_read_definedness.v1", "passed":all(r["passed"] for r in records),
              "cases":records, "physical_harts":3, "parked_harts":[1,2], "hardware_contacted":False,
              "timing_accuracy_certified":False, "source_sha256":sha(__file__), "toolchain_sha256":sha(args.riscv_gcc)}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
