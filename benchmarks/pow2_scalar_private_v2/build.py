#!/usr/bin/env python3
"""Build a frozen, single-active-hart power-of-two scalar experiment."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LENGTHS = tuple(1 << n for n in range(4, 12))
RESERVED = (32, 256, 1024)
KINDS = ("integer_dependent", "integer_independent4",
         "fp16_dependent", "fp16_independent4",
         "fp32_dependent", "fp32_independent4",
         "fp64_dependent", "fp64_independent4")
COMPILER = Path("/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def golden(kind, n):
    independent = kind.endswith("independent4")
    if kind.startswith("integer"):
        return [n * (i + 1) for i in range(4)] if independent else [n, 0, 0, 0]
    fmt = {"16": "e", "32": "f", "64": "d"}[kind[2:4]]
    bits = int.from_bytes(struct.pack("<" + fmt, float(n)), "little")
    return [bits] * 4 if independent else [bits, 0, 0, 0]


def cases():
    result = []
    for trial in range(3):
        for n in LENGTHS:
            for kind_index, kind in enumerate(KINDS):
                for hart in range(3):
                    parent = f"scalar.pow2.private.v2.{kind}.n{n}.h{hart}"
                    result.append(dict(id=parent + f".trial{trial}", parent_case_id=parent,
                        semantic_parent_case_id=f"scalar.pow2.private.v2.{kind}.n{n}",
                        kind=kind, kind_index=kind_index, n=n, hart=hart, trial_id=trial,
                        active_harts=[hart], internal_split="reserved_validation" if n in RESERVED else "train",
                        expected_values=golden(kind, n)))
    return result


def assembly():
    lines = [".text", ".option push", ".option norvc"]
    for index, kind in enumerate(KINDS):
        name = "scalar_pow2_" + kind
        independent = kind.endswith("independent4")
        count = 4 if independent else 1
        lines += [".balign 64", ".globl " + name, ".type " + name + ",@function", name + ":"]
        lines += ["mv t2,a0"]
        if kind.startswith("integer"):
            lines += [f"li t{r + 3},0" for r in range(count)]
            body = [f"addi t{r + 3},t{r + 3},{r + 1}" for r in range(count)]
        else:
            suffix = {"16": "h", "32": "s", "64": "d"}[kind[2:4]]
            lines += [f"fcvt.{suffix}.w ft{r},zero" for r in range(count)]
            lines += ["li t0,1", f"fcvt.{suffix}.w ft4,t0"]
            body = [f"fadd.{suffix} ft{r},ft{r},ft4" for r in range(count)]
        lines += [f".Lbody_{index}:"] + body + ["addi t2,t2,-1", f"bnez t2,.Lbody_{index}"]
        if kind.startswith("integer"):
            lines += [f"sd t{r + 3},{r * 8}(a1)" for r in range(count)]
        else:
            move = {"16": "fmv.x.h", "32": "fmv.x.w", "64": "fmv.x.d"}[kind[2:4]]
            for r in range(count):
                lines += [f"{move} t0,ft{r}", f"sd t0,{r * 8}(a1)"]
        lines += ["ld a0,0(a1)", "ret", ".size " + name + ",.-" + name]
    lines += [".option pop", '.section .note.GNU-stack,"",@progbits']
    return "\n".join(lines) + "\n"


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--negative-skip-kernel", action="store_true")
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    runtime = HERE / "runtime"
    if not runtime.exists():
        raise ValueError("Private copied runtime must exist before freezing the build")
    cs = cases()
    corpus = dict(schema="iris.pow2_single_active_scalar_private.v2", cases=cs, required_regions=len(cs),
        physical_harts=3, single_active_hart=True,private_per_hart_results=True,done_poll_flag_separate_cache_line=True,all_measurements_before_UART=True,parent_shared_v1_preserved=True,new_exact_hardware_reference_required=True,lengths=list(LENGTHS), trials=3,
        kinds=list(KINDS), reserved_validation_lengths=list(RESERVED),
        split_grouping="N across every kind/hart/trial; reserved timing labels root-only",
        normal_ROI="Raw mcycle/minstret; call, initialization, loop, result stores, fence and counter overhead included",
        inactive_policy="Unchanged qualified DRAM-generation, masked-WFI/MSIP barrier and parked inactive peers",
        history="trial then N then kind then hart; ALL576measurement records buffered before any console; sentinel0 before UART. Perhart64Bresult slots; activehartzero beforeROI, pollflag separate64Bline; no flush/cold claim. Newlayout/reference mandatory; originalsharedlinev1 remains a validcoherence workload.",
        mtime_hz=500000, source_core_cycles_per_mtime_tick=1000,
        CLINT_scope="Encloses CSR ROI plus sampling overhead; no overhead subtraction; +/-1000 core-cycle quantization",
        hardware_contacted=False, timing_certified=False, source_image_association_verified=False,
        negative_skip_kernel=args.negative_skip_kernel)
    (out / "corpus.json").write_text(json.dumps(corpus, indent=2) + "\n")
    (out / "cases.inc").write_text("static const case_t experiments[]={\n" + ",\n".join(
        "{" + json.dumps(c["id"]) + "," + ",".join(str(c[k]) for k in
        ("kind_index", "n", "hart", "trial_id")) + ",{" +
        ",".join(str(v) + "ULL" for v in c["expected_values"]) + "}}" for c in cs) + "\n};\n")
    (out / "kernels.S").write_text(assembly())
    elf = out / "scalar.elf"
    argv = [str(COMPILER), "-O2", "-g", "-Wall", "-Wextra", "-Werror", "-ffreestanding",
        "-fno-builtin", "-fno-tree-vectorize", "-fno-tree-slp-vectorize", "-ffunction-sections",
        "-fdata-sections", "-fno-common", "-mcmodel=medany", "-mabi=lp64d",
        "-march=rv64gcv_zfh_zvfh_zicsr_zifencei", "-nostdlib", "-static",
        "-Wl,--build-id=none,--gc-sections", "-DIRIS_HARTS=3", "-I" + str(runtime),
        "-I" + str(out), "-T", str(runtime / "link.ld"), str(runtime / "start.S"),
        str(runtime / "runtime.c"), str(HERE / "guest.c"), str(out / "kernels.S"), "-lgcc", "-o", str(elf)]
    if args.negative_skip_kernel:
        argv.insert(1, "-DIRIS_SKIP_KERNEL")
    r = subprocess.run(argv, capture_output=True)
    (out / "build.stdout").write_bytes(r.stdout)
    (out / "build.stderr").write_bytes(r.stderr)
    if r.returncode:
        raise ValueError(r.stderr.decode())
    nm = COMPILER.with_name("riscv64-unknown-elf-nm")
    objdump = COMPILER.with_name("riscv64-unknown-elf-objdump")
    syms = subprocess.check_output([str(nm), "-S", "--defined-only", str(elf)], text=True)
    disasm = subprocess.check_output([str(objdump), "-d", str(elf)], text=True)
    (out / "symbols.txt").write_text(syms)
    (out / "disassembly.txt").write_text(disasm)
    def symbol(name):
        matches = [l.split() for l in syms.splitlines() if l.split()[-1] == name]
        if len(matches) != 1:
            raise ValueError("Unique symbol required: " + name)
        return dict(address=int(matches[0][0], 16), size=int(matches[0][1], 16))
    kernel_symbols = {} if args.negative_skip_kernel else {
        kind: symbol("scalar_pow2_" + kind) for kind in KINDS}
    if any(v["address"] % 64 for v in kernel_symbols.values()):
        raise ValueError("Actual kernel entry alignment differs")
    layout = dict(schema="iris.pow2_scalar_buffer_layout.v1", record_bytes=88,
        records=len(cs), objects={n: symbol(n) for n in
        ("scalar_records", "scalar_record_count", "scalar_measurements_done")},
        kernel_symbols=kernel_symbols, elf_sha256=sha(elf))
    (out / "layout.json").write_text(json.dumps(layout, indent=2) + "\n")
    libgcc = Path(subprocess.check_output([str(COMPILER), "-mabi=lp64d",
        "-march=rv64gcv_zfh_zvfh", "-print-libgcc-file-name"], text=True).strip()).resolve()
    inputs = [Path(__file__), HERE / "guest.c", HERE / "validate.py", COMPILER, nm, objdump, libgcc,
        *[runtime / n for n in ("start.S", "runtime.c", "runtime.h", "uart_drain.h", "link.ld")],
        *[out / n for n in ("corpus.json", "cases.inc", "kernels.S", "layout.json")]]
    ids = {str(p.resolve()): sha(p) for p in inputs}
    (out / "inputs").mkdir()
    for path, h in ids.items():
        (out / "inputs" / h).write_bytes(Path(path).read_bytes())
    report = dict(schema="iris.pow2_scalar_build.v1", **{"pass": True}, argv=argv,
        elf=str(elf), elf_sha256=sha(elf), input_sha256=ids, negative_skip_kernel=args.negative_skip_kernel,
        hardware_contacted=False, compiler_version=subprocess.check_output([str(COMPILER), "--version"], text=True).splitlines()[0])
    (out / "build.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(dict(elf=str(elf), elf_sha256=sha(elf), regions=len(cs))))


if __name__ == "__main__":
    main()
