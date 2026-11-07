# Build and run the Iris branch

This branch contains the modified Spike sources in `riscv/`, and the Iris board,
pipeline, timing, runtime and profiling sources under `iris/`. The external
includes from the historical snapshot now resolve inside this repository. The
upstream base, original source patch and include relocations are retained in
`iris/provenance/`. The original upstream README remains below the Iris summary.

The source model also links twelve generated component SDK archives. They are
external build dependencies with exact SHA256 identities in `iris/sdk-inputs.json`.
They are not an FPGA bitstream. Their generation pipeline is not yet packaged as
a clean build here; cloning this fork alone does not regenerate them.

On amd6, the existing cache root is `/scratch/copparihollmann/iris-model` and
the matching Verilator headers and `dtc` are in Ethan's existing toolchain:

```sh
python3 iris/build.py \
  --sdk-root /scratch/copparihollmann/iris-model \
  --verilator-include /scratch/eygao/iris-cy/.conda-env/share/verilator/include \
  --dtc /scratch/eygao/iris-cy/.conda-env/bin/dtc \
  --build /absolute/new-iris-build --jobs 12
```

The cache can live elsewhere with the same relative archive paths. The builder
verifies every SDK archive and the matching Verilator runtime headers, compiles
the native simulator and matched clocked UART library, creates the boot inputs
and fatal-aware launcher, and writes complete build-input/output hashes. Each
build needs a fresh output directory. Build failures retain their logs and
`build.json`. No command here contacts the FPGA.

Run a symbol-preserving RV64 ELF with all three physical harts:

```sh
python3 iris/run.py --build /absolute/new-iris-build --profile source_compute \
  --elf /absolute/kernel.elf --output /absolute/new-kernel-run
python3 iris/run.py --build /absolute/new-iris-build --profile source_os \
  --elf /absolute/zephyr.elf --output /absolute/new-zephyr-run
python3 iris/run.py --build /absolute/new-iris-build --profile source_compute \
  --elf /absolute/kernel.elf --output /absolute/new-profile-run --source-profile
```

`--timeout` defaults to 600 seconds; `--seed` defaults to zero. Matrix workers
belong on harts 0/1. Hart 2 remains present for control and ordinary RVV. Program
counter reads expose modeled time. Fatal-handler resolution rejects stripped
ELFs and terminates fatal execution instead of waiting indefinitely in a handler.

Each normal run preserves raw stdout/stderr, `run.json`, native summary and
counter-prefix records. Profiling additionally writes admitted source accounting
and Perfetto/Chrome trace files under `source-profile-v3/`. Process completion,
independent numerical validation and timing accuracy remain separate outcomes.

The two build descriptors are `source_compute/manifest.json` and
`source_os/manifest.json`. They implement the existing empirical simulator
descriptor API using this checkout's `iris/tools/native_model.py`. The
`ucb-bar/iris-mlir` adapter accepts these explicit development descriptors when
this branch is installed at its pinned `simulator/spike-model` submodule.
Merlin callers must honor all per-hart ISAs and launch arguments; the historical
generic runner delta is archived in iris-mlir and is not automatically applied.

New build digests are development builds. They do not inherit the frozen 35a
binary's timing validation. The README and `iris/results.json` identify that
historical binary and its measured limits. The overall ±2% target is unmet;
changing the model or fixture requires new numerical and timing validation.
