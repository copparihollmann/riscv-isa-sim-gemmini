# Zephyr FP/RVV/VME contexts

The clean base is Zephyr `cd45a528d3bf81f9c7aa2a63f9fe512eee0881b0`.
`patches/0002-iris-vme-context.patch` is cumulative from that pin and includes
the cursor-only `0001` fix. Apply either patch to the base, not both in sequence.

```sh
python3 zephyr/prepare_context_tree.py
python3 zephyr/context_build.py --source third_party/zephyr-iris \
  --patch zephyr/patches/0002-iris-vme-context.patch \
  --extra-conf zephyr/configs/vme-context.conf \
  --output build/zephyr-context-example
python3 zephyr/context_run.py \
  --elf build/zephyr-context-example/zephyr/zephyr.elf \
  --output build/zephyr-context-example-run
python3 zephyr/context_build.py --source third_party/zephyr-iris \
  --patch zephyr/patches/0002-iris-vme-context.patch \
  --app zephyr/vme-context-stress --output build/zephyr-vme-example
python3 zephyr/vme_context_run.py \
  --elf build/zephyr-vme-example/zephyr/zephyr.elf \
  --output build/zephyr-vme-example-run
```

The derived worktree stays at the full base commit plus a byte-matched explicit
patch. The base clone remains clean. Builds archive source inputs and bind
their hashes, compiler, ELF and patch. Runs bind the physical ROM/DTB, stable
private Spike/UART snapshot, runner source, console and independent host goldens.
Both context runners accept explicit `--binary` and `--uart` paths for testing
another immutable simulator build; their default is the preserved snapshot.

The full reproducible context corpus builds three positive and two deliberate
failure ELFs, including an isolated kernel with tile restore removed:

```sh
python3 zephyr/check_contexts.py --binary spike/bin/spike-iris-functional \
  --uart spike/bin/libsifive_uart.so --output build/zephyr-context-suite-current
python3 zephyr/context_audit.py --verify
```

Use the explicit API before establishing live vector/matrix values:

```c
#include <zephyr/arch/riscv/iris_vme.h>
/* Create this thread blocked; restrict its CPU mask to harts 0/1 first. */
int err = iris_vme_enable();
```

Enable `CONFIG_RISCV_ISA_EXT_V`, `CONFIG_FPU_SHARING`,
`CONFIG_SCHED_CPU_MASK`, and `CONFIG_RISCV_IRIS_VME_CONTEXT`. Call from thread
context on hart 0/1 with nonempty affinity restricted to these harts. The API
returns zero once, `-EALREADY` if repeated and `-ENOTSUP` for incompatible
affinity, interrupt context or hart 2. Later CPU-mask changes cannot place an
initialized VME task on hart 2. First ownership explicitly zeroes all four
32×32 tiles and clobbers vector configuration. Hardware tiles are uninitialized
at reset; the model refuses undefined reads. This initialization belongs to
the software ABI, not Spike. Unregistered VME use and VME in interrupt handlers
are unsupported. Privileged code can bypass an API, so compiler/runtime setup
must invoke target-owned initialization.

The extension uses the existing lazy FP/RVV owner and SMP remote-flush IPI.
Before vector-copy configuration changes, it captures mtype (widen/TK/TM),
vtype (including format), VL/TN, vstart and vcsr. After saving the vector file,
it serializes all 16 KiB of tiles through supported e32w1 row moves. Restore
writes tiles, vector data, matrix configuration via msetmtype/TN/TM/TK, and
vstart/vcsr. Existing hooks preserve FP registers/fcsr. Registered VME owners
force a save even when OP-VE does not dirty FS/VS. Lazy recognition includes
opcode 0x77 and mtype reads. Ordinary RVV tasks, including hart 2, never access
matrix state. Tests disable C vector auto-generation, including kernel C;
applications must still obey the function-call ABI for caller-clobbered registers.

| Actual ELF test | Result |
| --- | --- |
| Clean-base six FP/RVV tasks, two per hart | 72 full-register checks, timer ticks and IEEE16/32/64 arithmetic pass |
| VME-aware kernel, six ordinary FP/RVV tasks | Same 72 independent goldens pass on all three harts |
| Four competing VME tasks, eight rounds each | All FP/RVV/mtype/16 KiB tile contents preserved; each task visits harts 0 and 1 |
| INT8 and exact E4M3/E5M2 MACs after handoff | Independent bitwise goldens pass; producer operands vary by round |
| Raw special tile values | Signed zeros, infinities, quiet/signaling NaN payloads and all-one cells preserved |
| Concurrent Rocket producer | Ordinary RVV, VME refusal and producer/completion synchronization pass |
| Mixed app, worker mask 7 | Nine scalar/VME/vector-copy regions pass independent checksums |
| Omitted ownership on a fresh compute hart | Nonzero undefined-tile-read failure; no simulator auto-initialization |

Receipts are under `build/zephyr-context-base-certified-run`,
`build/zephyr-context-vme-aware-certified-run`,
`build/zephyr-vme-context-certified-run`,
`build/zephyr-mixed-vme-mask7-final-run`, and
`build/zephyr-vme-ownership-negative-run`. The baseline disassembly keeps the
original CSR context pointer separately, and the baseline stress passes. The
invalid input-only cursor constraint is fixed without claiming an observed
GCC16 miscompile.

```sh
python3 zephyr/build.py --source third_party/zephyr-iris \
  --patch zephyr/patches/0002-iris-vme-context.patch \
  --saturn third_party/saturn --conf zephyr/configs/mixed-vme-mask7.conf \
  --output build/zephyr-mixed-example
python3 zephyr/run.py --build build/zephyr-mixed-example \
  --binary build/zephyr-binary-snapshot/spike \
  --uart build/zephyr-binary-snapshot/libsifive_uart.so \
  --output build/zephyr-mixed-example-run
```

The mixed app initializes ownership before its measured VME region, excluding
that one-time cost. Its one-worker-per-hart case is supplemented by the same-hart
stress. Historical scalar/placement/live outputs remain intact; matching build
inputs were archived before the optional app changed.

RTL/FPGA context validation, deployed image association, asynchronous OPU drain
behavior on hardware and calibrated performance remain pending. Exact FP8
examples here certify those context cases, not every FP8 arithmetic edge.
Functional-mode mcycle is instruction-based; these results make no +/-2%
timing claim. Saving 16 KiB per initialized task may be expensive and must be
measured on the real design before performance conclusions.
