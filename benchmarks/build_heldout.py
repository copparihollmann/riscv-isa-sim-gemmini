#!/usr/bin/env python3
"""Build reserved Miles workloads; this does not collect or fit timing data."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, default=Path("/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc"))
    parser.add_argument("--saturn", type=Path, default=here.parent / "third_party/saturn")
    parser.add_argument("--spike", type=Path, default=here.parent / "third_party/riscv-isa-sim")
    parser.add_argument("--output", type=Path, default=here / "build")
    args = parser.parse_args()
    compiler, saturn, spike, out = (p.resolve() for p in (args.compiler,args.saturn,args.spike,args.output))
    commit = subprocess.check_output(["git","-C",str(saturn),"rev-parse","HEAD"]).decode().strip()
    if commit != "536774bd4c5e3bcd7813a4a0dc72fc87e5818532":
        raise SystemExit("heldout Saturn source pin mismatch")
    common = saturn / "benchmarks/common"
    corpus = json.loads((here / "heldout-corpus.json").read_text())
    out.mkdir(parents=True,exist_ok=True)
    result = {"schema_version":1,"split_id":corpus["split_id"],"fitting_allowed":False,
              "compiler_sha256":sha(compiler),"saturn_commit":commit,"artifacts":[]}
    for name,case_id,source in [
        ("miles-vme-fused","miles.vme-fused-lm2-gemm-transpose",saturn/"benchmarks/vme-fused-lm2-gemm-transpose/main.c"),
        ("miles-vme-i8","miles.vme-i8-gemm",saturn/"benchmarks/vme-i8-gemm/main.c"),
    ]:
        reserved = next(case for case in corpus["cases"] if case["case_id"]==case_id)
        if sha(source)!=reserved["source_sha256"]:
            raise SystemExit("heldout source changed: "+case_id)
        elf=out/(name+".elf")
        command=[str(compiler),"-O2","-g","-mcmodel=medany","-static","-fno-common","-fno-builtin-printf",
                 "-fno-tree-loop-distribute-patterns","-march=rv64gcv_zfh_zvfh","-mabi=lp64d",
                 "-DPREALLOCATE=1","-DMAX_TE=32","-I"+str(common),"-I"+str(spike/"riscv"),
                 str(source),str(common/"syscalls.c"),str(common/"crt.S"),"-nostdlib","-nostartfiles",
                 "-T",str(common/"test.ld"),"-lm","-lgcc","-o",str(elf)]
        completed=subprocess.run(command,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (out/(name+".build.log")).write_text(completed.stdout)
        if completed.returncode: raise SystemExit(completed.stdout)
        inputs=[source,common/"syscalls.c",common/"crt.S",common/"test.ld",spike/"riscv/encoding.h",*common.glob("*.h")]
        for library in ("libgcc.a","libm.a"):
            path=Path(subprocess.check_output([str(compiler),"-print-file-name="+library]).decode().strip())
            if not path.is_file(): raise SystemExit("missing linked library "+library)
            inputs.append(path)
        result["artifacts"].append({"case_id":case_id,"path":str(elf),"sha256":sha(elf),"command":command,
                                    "input_sha256":{str(p):sha(p) for p in inputs},"executed":False})
        print(name+": "+str(elf)+" sha256="+sha(elf))
    (out/"heldout-build.json").write_text(json.dumps(result,indent=2)+"\n")


if __name__=="__main__":
    main()
