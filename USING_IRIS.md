# Using the current Iris development snapshot

Run these commands from `/scratch/copparihollmann/iris-model`. They select the
frozen, tested 35a simulator explicitly. All three heterogeneous harts remain
present: compute harts 0/1 have VLEN256/DLEN128 and VME; control hart 2 has
VLEN256/DLEN256 and ordinary RVV, with no VME or FP8/BF16 arithmetic.

## First check

```sh
./iris-run check
./iris-run compute benchmarks/build/smoke.elf --output build/my-first-smoke
```

Keep the frozen simulator dependency/adapter files unchanged. Develop the compiler
and kernels in a separate checkout, then pass their resulting ELF to this tool.
`check` intentionally fails if a bound input changes.

Choose a new output directory for every run. Keep the ELF unstripped so fatal
handlers and functions can be resolved. The check verifies both model profiles,
their exact binaries, timing parameters and bound source/evidence inputs.

## Compiler and baremetal kernel work

```sh
./iris-run compute /absolute/kernel.elf --output build/my-kernel-run
```

This uses `source_compute`: finite source VADD/FADD/VME timing on harts 0/1,
with inherited effective costs for the other components. Unsupported source
contexts, including active vector IRQ contexts, refuse explicitly. The strongest
timing results apply to the measured full-VL, unmasked arithmetic/matrix cases;
they do not cover arbitrary RVV, memory overlap or whole workloads.

On the latest isolated reference, all 432 FP-add and 48 E4M3×E4M3 matrix regions
were within 2%; integer-add passed 573/576 and INT8 matrix 47/48. Memory and short
drain phases still have large errors. [Exact scope and signed results](timing/SOURCE_COMPUTE_VADD35A.md).

## Multicore Zephyr work

```sh
./iris-run zephyr /absolute/zephyr.elf --output build/my-zephyr-run
```

This uses the separately tested `source_os` profile. It preserves all three
harts, modeled program-visible clocks, console/devices and fatal-aware execution.
Detailed timing work focuses on harts 0/1; hart 2 retains functional control and
shared-resource effects. The OS profile disables the new source VADD/OPU/FENCE
actors and uses its recorded effective timing costs instead.

A ready example has passed on both the FPGA and this model:

```sh
./iris-run zephyr \
  build/zephyr-mixed9-firstuse-normal-v2/zephyr/zephyr.elf \
  --output build/my-tested-zephyr-example
```

It performs INT8 VME work on harts 0/1 with scalar control/observation on hart 2.
All nine region checksums and normal exit passed on both paths.
[Working example, provenance and managed FPGA recipe](firesim/ZEPHYR_COMPUTE_HARTS.md).

The broader FPGA batch also passed all **648 regions and 181,440 values**:
RVV SEW8/16/32 with LMUL1/2/4/8, matrix shapes8/16/32, INT8 and all four
E4M3/E5M2 operand-format pairs, one/two compute harts, three trials. Hart 2
coordinates the work using scalar code. This establishes the tested active
elements/guards, rather than unrestricted context migration or every ISA case.

The frozen OS model's comparison retains all regions and phases. Median absolute
total-cycle error is **4.7% overall**, with P90 **27.8%**; 159/648 are within2%.
For the 192 reserved validation regions, median absolute error is **24.6%**;
32/192 are within2%. The ±2% target is therefore **not met**. The comparison uses
a controlled postmeasurement model stop; it is not an end-to-end speed result.
[Complete signed timing results](build/zephyr-hart2-pow2-35a-OS-root-validation-v2/report.json).

Use this profile for compiler correctness, multicore execution and experimental
profiling. Use the recorded FPGA reference for final concurrent/memory-sensitive
performance decisions. The older mixed workload that also uses hart-2 vectors
still has a preserved timeout; the working scalar-control example is a separate
program/history. Full competing-owner/migration and loaded-image/source
certification remain incomplete.

## Source utilization and timelines

```sh
./iris-run profile /absolute/kernel.elf --output build/my-kernel-profile
```

For a short tested example, use
`build/source-profile-smoke-guest-v1/guest.elf` as the ELF. This command selects
the compute profile. Inspect:

- `run.json`: execution and profile outcome, inputs and output digests;
- `execution-v1/stdout` and `stderr`: raw program output;
- `source-profile-v3/admission.json`: receipt/clock binding checks;
- `source-profile-v3/accounting-v2/summary.json`: region/function/work metrics;
- `source-profile-v3/accounting-v2/trace.json`: Perfetto/Chrome timeline.

Open the trace in Perfetto. Source pipe-valid occupancy, OPU controller busy,
command age and completed logical work are distinct metrics. Physical FPGA
utilization, DRAM/L2 traffic and physical rooflines remain unavailable. The
compute profile's utilization/accuracy qualification does not transfer to the
Zephyr profile. [Profiling semantics](iris_model/SOURCE_EVENT_PROFILING_V3.md).

Ordinary compute/Zephyr runs retain `stdout`, `stderr`, `native-summary.json`,
counter-prefix features and `run.json`. Their program `mcycle` reads use modeled
time. Process exit, numerical validation and timing accuracy are separate gates.

## Merlin integration and continuation

The tested OOT hook uses the exact descriptor selected through
`MERLIN_IRIS_MODEL_MANIFEST`. Choose the compute or OS manifest under
`build/C12-source-VADD35a-optional-package-v1`; select empirical mode and the
explicit experimental opt-in. [Exact environment/API recipe](timing/SOURCE_COMPUTE_VADD35A.md#merlin-integration).
Use three physical harts and matrix-worker IDs `(0,)` or `(0,1)`.

The convenience command changes no older default pointer or frozen package.
New source System/FASED/vector-memory experiments are preserved separately and
are not selected by `iris-run`; their production integration is unfinished.

The FPGA is cleaned up and no hardware job is left running. Every future FPGA
run must use fresh complete occupancy/authorization checks and the shared lock,
then kill → infrasetup → runworkload → owned kill. Never reuse a consumed job or
bypass the manager. Full raw results and byte inventories are retained.

[CURRENT_STATUS.md](CURRENT_STATUS.md) records exact releases, receipts, source
pins and next steps. The next modeling task is native memory/System integration
and overlap against a fresh reference, while preserving the reserved data split.
Whole GPT-OSS/Llama/Gemma/TinyLlama workloads have not been qualified.
