# Functional Spike baseline

This standalone package builds pristine public Spike and a selected Gemmini
functional extension. It carries no timing observer, timing provider, compiler
or kernel implementation. No compiler checkout or network access is needed to
build the exported package.

## Pinned sources and scope

| Component | Public revision |
| --- | --- |
| Spike | `9c190a07c6838f6392bafa4ad83acea462c7f759` |
| libgemmini for stock U250 `a9a190b9` | `ea8f7ed7afd68e001fb06ddccad9a023c990961d` |
| libgemmini for 30 MHz U250 `0af6f26e` | `5b1254a7dc72f757442280e7f28ef30542c78533` |

`sources.json` pins both original source archives and the selected Gemmini
receiver, parameter header and public RoCC header. `profile.json` records the
software ABI associated with `FireSimGemminiRocketConfig`: DIM 16, 16,384
scratchpad rows, 1,024 accumulator rows, int8 elements, int32 accumulators,
custom opcode `0x7b`, full accumulator readout and first-layer optimizations.
The builder checks these facts against the pinned header before compiling.
Every extracted source file and symlink is checked against a complete public
source roster before and after building; extra instrumentation is rejected.

The 30 MHz profile records exact Chipyard, Gemmini and receiver source revisions
from the U250 handoff; the complete historical dirty FireSim overlay and matched
FPGA execution remain unproven. The stock profile retains its original source
limitations.
These source pins establish a functional ABI baseline, not physical deployment
equivalence. Rocket caches, accelerator queues, memory bandwidth and cycle
counts are not modeled or inferred. The explicit launch ISA is an executable
compatibility selection, not proof of the exact bitstream's ISA. Spike's guest
counters remain its normal functional counters.

## Build

Requires Linux, Python 3.10+, GCC/G++, Make, the device-tree compiler and the
Boost development packages required by upstream Spike. Existing system
dependencies are used; the helper installs or downloads nothing.

```sh
python3 build.py --verify-only
python3 build.py --work-dir /your/task/.tmp/functional-build --jobs 2
mkdir -p /your/task/out
mv /your/task/.tmp/functional-build/runtime /your/task/out/runtime
```

The work directory must be new. Source extraction, temporary files, objects
and installation stay inside it. At most two compilation jobs are accepted.
The original functional source and Makefile are unmodified. The installation
contains `bin/spike`, `lib/libgemmini.so`, upstream headers and `deployment.json`
with source, binary, compiler and build-command receipts. Its initial status is
`built_not_executed`; building does not establish numerical or RTL correctness.
The separate `runtime/` deployment contains the executable, compiled
functional library, receipts and, when a staged Boost root was selected, the
exact Boost regex shared library. Move it by rename to the stable task `out/`
directory as shown above. The build's `sources/` and `install/include/` remain
trusted operator build material in `.tmp/`, outside candidate grants. Historical
execution receipts retain their original argv when a deployment moves; a current
deployment location record identifies the relocated endpoints.

When Boost is staged outside system paths, pass both `--boost-root` and
`--boost-libdir`. Those exact dependency paths and the version-header hash enter
the deployment receipt. Set `LD_LIBRARY_PATH` to `runtime/lib` when using a
staged Boost build; this selects the packaged regex library and Gemmini receiver.

## Functional launch

Choose memory capacity explicitly for the current ELF. This does not assert
that the physical board has that capacity. The default profile uses one
machine-mode RV64GC hart plus cycle/performance counters, without vectors.
Additional host extensions require independent deployment justification and an
explicit launch choice.

```sh
LD_LIBRARY_PATH=/your/task/out/runtime/lib /your/task/out/runtime/bin/spike \
  --isa=rv64imafdcb_zicsr_zifencei_zihpm_zfh_zba_zbb_zbs \
  --priv=m -p1 -m0x80000000:0x400000000 \
  --extlib=libgemmini.so \
  --extension=gemmini /path/to/program.elf
```

The 16 GiB launch span above is for the 30 MHz profile; select the declared
span of each other board explicitly. Only the selected baseline library should
be loaded. No annotated extension is needed.
The receiver implements its original public instruction set, including hardware
loop instructions. The experiment's no-FSM instruction constraint remains an
independent compiler/grader policy; this baseline does not silently change the
functional ISA to enforce it.

For an agent experiment, grant the executable/library endpoints through the
runner. The functional-model sources and vendor headers are operator build
inputs, not compiler-answer material to expose to the candidate.

## Export from local public object stores

Maintainers can regenerate this package using
`examples/gemmini/functional_baseline/export.py`
with `--spike-repo`, `--libgemmini-repo` and a new `--output` directory. Export
reads the pinned Git objects, ignoring checkout revisions and uncommitted
changes. Generated source archives and binaries should not be committed.

This packager and the optional observer live on the same simulator source branch.
It exports the pristine pinned Git objects rather than the instrumented checkout,
so no timing code reaches the functional runtime. It imports no OOT compiler.

```sh
python3 examples/gemmini/functional_baseline/export.py \
  --profile fire_aligned_30mhz \
  --spike-repo /path/to/riscv-isa-sim \
  --libgemmini-repo /path/to/public/libgemmini \
  --output /path/to/new/task-temporary-package
```
