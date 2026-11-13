This independent batch runs eight real Zephyr SMP phases in one ELF: GEMM
and a convolution contraction, each with one or two compute workers, using
both the emitted VME kernel and its scalar twin. Hart 2 prepares alternate
buffers, runs an ordinary RVV producer and verifies that VME ownership is
refused. All three CPUs remain online. Each phase runs three datasets five
times, giving 188 measured regions in total.

The compiler path uses the actual Merlin rewrite, LLVM 23 lowering and
descriptor bridge. Each worker calls the compiled 32×64 contraction; a single
worker calls it twice to cover 64 rows. The convolution's im2col indexing is
performed by the producer, outside the compiled contraction. This does not
claim that Merlin compiled a complete convolution frontend or language model.

The frozen compact workload is
`build/fast-heldout-zephyr-compact-v6/manifest.json`, SHA256
`987e0b3c4e8c3f45c1549501edee6a7f1e6ba1b73f7289cb4fc877a1460e3ed2`.
Its deployable `compact.elf` has SHA256
`da2de5ef01d7030741058859162fb6286fa73baf8816ab1365bdfe3ea6785cd4`.
Every source, compiler object, original full-output ELF and emitted kernel is
retained by digest under the build directory's `objects/`.

The compact ELF differs from that build's original full-output ELF by exactly
one initialized data byte, `iris_heldout_full_output`. All instruction bytes,
including kernel and ROI code, are identical. Every INT32 and W8A8 output word
is compared to independently generated embedded goldens after each phase's
ROIs. Compact output carries both independently expected whole-output hashes,
word counts and zero mismatch counts. Volatile stores poison every output
with its golden XOR 0xffffffff before the phase. Full output remains available
in the original ELF. The output switch changes work and cache/timer history
between phases; timings from the two modes are not interchangeable.

The compute regions exclude setup and result checking. Each phase also has a
pinned-hart-2 interval from producer entry through consumption of all outputs;
it excludes boot, thread creation and final printing. Because hart mcycle can
stop during WFI, v6 separately reads the actual CLINT mtime MMIO register at
0x0200bff8 around that interval. Its 500 kHz timebase gives 1,000 core cycles
per tick; each elapsed interval has less than one tick of quantization error.
These timer data-sample boundaries enclose the hart-counter interval; MMIO
reads are outside the kernel ROIs. No whole-batch end-to-end accuracy is
claimed. Threads join before their objects or buffers are reused.
The VME kernel requires the explicit `iris_vme_enable` OS ownership ABI and
the recorded Zephyr context patch. There is no automatic Spike tile save.

Run the frozen batch locally, using a chosen matched native/UART pair:

```sh
python3 zephyr/heldout_batch_run.py \
  --batch build/fast-heldout-zephyr-compact-v6 \
  --expected-manifest-sha256 987e0b3c4e8c3f45c1549501edee6a7f1e6ba1b73f7289cb4fc877a1460e3ed2 \
  --binary PATH_TO_SPIKE --uart PATH_TO_MATCHED_UART \
  --output NEW_DIRECTORY
```

For experimental timing, add `--timing-kind experimental-empirical` and the
actual engine options as repeated `--engine-arg=OPTION`. Freeze the parameter
package and predictions before examining reference timing. Keep results out
of fitting inputs. Archive validation uses the same command with
`--console PATH_TO_ARCHIVED_UART` in place of the binary/UART options. Only the
coordinator may launch FPGA jobs, through the managed four-phase lifecycle.
The board selects Ethan's fixed FireSim UART profile, divisor 135.

`zephyr/heldout_batch_predict.py` additionally verifies the actual
`iris.empirical_runtime_binding.v1` envelope, snapshots the selected native,
UART, fixture, parameters, fit report and runtime libraries before execution,
and freezes a `prediction.json` after the actual run. It exports the native
bounded summary and `IRIS_EMPIRICAL_FEATURES` prefix stream. Use that receipt
for hardware admission, rather than a functional-only report.

`firesim/prepare_heldout_batch.py` requires both seeded functional gates,
the acceptance controls, frozen prediction hash, runtime envelope and actual
standing-user authorization receipt. It prepares a fresh private job and
never launches hardware. Its default foreground watchdog is 1,200 seconds;
there is no overflowing target-cycle plusarg. After the coordinator completes
and archives the managed lifecycle, run `firesim/analyze_heldout_batch.py` on
the job. It independently verifies the archive inventory, UART, actual ELF,
goldens and lifecycle, then emits `reference-validation.json`.

Finally `zephyr/heldout_batch_compare.py` compares that reference to the
exact frozen prediction. It reports signed error for every region and the
separate CLINT elapsed windows, including timer quantization bounds. It has
no fitting path. Its `--archive-evidence` is the independent analyzer's
`report.json`; arbitrary console text is insufficient reference evidence.

Functional seeds 0 and 17 pass all 188 regions and 491,520 independently
checked INT32 outputs plus W8A8 words. A real omitted-kernel ELF fails the
per-word golden check; 16 corruptions are rejected. These are experimental
functional checks. The exact original Zephyr/hart-2 context hang after 25
regions and the separate page-cross store failure after 1,174 regions remain
known hardware/model divergences, with exact ELF and archive identities in
[`HART2_VECTOR_INVESTIGATION.md`](../../firesim/HART2_VECTOR_INVESTIGATION.md).
This batch does not certify those paths,
all dtypes, full-model workloads, physical utilization or ±2% timing.
