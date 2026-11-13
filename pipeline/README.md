# Isolated live Shuttle pipeline

The fifth isolated candidate now models different live scalar pipelines on all
three harts. See [ROCKET_PIPELINE.md](ROCKET_PIPELINE.md) for source rules,
actual multicore Zephyr checks, review identities and remaining timing gaps.

The fourth isolated candidate now overlaps source-legal counter operations with
ALUs using actual EX stalls and COM bypass readiness. See
[COUNTER_PIPELINE.md](COUNTER_PIPELINE.md) for its evidence and unqualified scope.

The source counter-edge correction and actual read-capture profiler are now
implemented in a further isolated review epoch. See
[COUNTER_POLICY.md](COUNTER_POLICY.md); the primary simulator remains unchanged.

The current experimental epoch adds the independently checked compressed-ALU
path and rebases onto the frozen finite-UART/HPM32 base. See
[CURRENT.md](CURRENT.md) for its identities, current gates and remaining scope.
The b14 snapshot described below is preserved historical evidence.

The experimental native model overlaps up to four source pipeline packets on
each Shuttle hart. It creates separate result-ready, COM retirement and WB
events for every admitted instruction. Spike executes each real instruction at
COM in program/lane order; multiple packets remain in flight. Hart2 retains the
conservative Rocket path. This is implemented code, with guest-visible modeled
counters and actual three-hart Zephyr tests. It is not calibrated RTL timing.

The immutable initial model is `build/pipeline-frozen-b14e192f/spike`, SHA256
`b14e192f3931660ab0215ce5be6b7a4b8e18331370489d26bf32a6b644d426d7`.
Its matching immediate-output UART is `libsifive_uart.so` in the same directory,
SHA256 `1bb66f7d0cf9db8050be8f32748550cf86769a4409efa9bcaf7879cbc1ae4406`.
The new interrupt-completion virtual method changes `simif_t`; pair this model
with its matching plugin. This historical model predates the separate finite,
clocked UART epoch. No hardware runs are performed by these tools.

## Scope

An explicit `shuttle_pipeline pure-integer-sequential-frontend` fixture admits
verified, 32-bit base RV64I scalar ALUs on harts0/1. It preserves source RAW/WAW,
x0 and unused raw-field pairing/retiming behavior. RVC, CFI, CSR/system, memory,
FP/vector/VME, translated fetch, triggers and debug are boundaries or exclusions.
Counter reads and shared-memory operations drain the pure pipeline and use the
existing guarded live adapter. This intentionally over-serializes some legal RTL
overlap; it cannot yet meet the full +/-2% goal.

The fixture assumes sequential frontend tags and no unmodeled external pipeline
stall. EX-ready+1, MEM-ready+2, COM+3 and WB+4 count hart clock edges from the
chosen RRD acceptance boundary. Their precise phase relative to RTL counter
sampling is unvalidated. Branch/frontend/cache latencies and real memory costs
remain unknown; the fixture's numeric costs are synthetic. The design and source
line references are in [PIPELINED_SHUTTLE.md](../timing/PIPELINED_SHUTTLE.md) and
`evidence/source-design.json`. Full RTL, calibration and held-out2% flags are false.

## Reproduce directed checks

The current source worktree is `pipeline/riscv-isa-sim`; build products are in
`build/spike-shuttle-pipeline`. It starts from Spike
`72958551566a30f19444bd7e354552824e4d0a98`, frozen primary overlay
`450a9418864ab562255eb0635cdda15414a709d8d6241fcd038918da027223e2`, then the
pipeline extension. The source-backed issue classifier is compiled directly
from `timing/shuttle_issue.cpp`.

The independently reviewable extension is
`build/pipeline-frozen-b14e192f/pipeline-on-memory-epoch.patch` (SHA256
`ba0a36b397fd33e3c9538685728e8d9ade86b6d2f782e9564f8a8fd70e84d38a`).
It applies cleanly to the exact frozen primary overlay. The full base-to-model
patch is `iris-with-pipeline.patch` in that snapshot (SHA256
`ea47ff1049f9de3827d5f84903c0d13f2448b919220e264baccd5f13c33313bb`).
The snapshot retains both patches, binary/plugin, reports and a content-addressed
closure of their source inputs. Never apply the old extension on a newer native
epoch without reviewing its ABI and source conflicts.

Configure/build commands used for this isolated tree:

```sh
mkdir -p build/spike-shuttle-pipeline
cd build/spike-shuttle-pipeline
PATH=/scratch/eygao/iris-cy/.conda-env/bin:$PATH ../../pipeline/riscv-isa-sim/configure --with-boost=no --with-boost-asio=no --with-boost-regex=no 'CXXFLAGS=-O2 -g0'
make -j32 spike
```

`pipeline/include/{riscv,fesvr,fdt}` point to the corresponding isolated source
directories. The matching plugin was compiled from the pre-UART-epoch source:

```sh
g++ -std=c++20 -O2 -fPIC -shared -Ipipeline/include -Ibuild/spike-shuttle-pipeline spike/devices/src/sifive_uart.cc -o build/spike-shuttle-pipeline/libsifive_uart.so
```

Use the frozen UART source from the parent archive for that historical build,
not a newer `spike/devices/src/sifive_uart.cc`. The archived guest SDK is similarly
frozen because the newer CRT explicitly drains the finite UART.

```sh
python3 pipeline/check.py --output build/pipeline-directed-new
```

The checker defaults to the frozen db964 baseline binary/plugin, the detached
`build/pipeline-parent-db964603` source and `build/pipeline-guest-db964603` CRT.
Those are prepared from `build/snapshot-db964603/iris.patch` and its source
archive. It checks the exact parent diff before writing an extension patch.
The source tree has intent-to-add entries for all new files so the full patch
contains them. Override the explicit baseline/source/overlay/guest-root options
only for a coordinated new model epoch; each run writes a new receipt.

The directed checker compiles actual guest assembly and tests independent and
dependent512-op streams, WAW/x0, raw-field LUI retiming, precise illegal decode,
last-TCM-word fetch faults, a latched IPI whose line clears before COM, a timer,
positive event durations, COM/WB separation, four live packets, per-instruction
graph attribution, identical seeded replay and fail-closed fixture parsing.
It also links a native test against the actual processor libraries to test
RV32/privilege/debug/single-step/halt/trigger exclusions, safe direct prefetch,
and non-mutating interrupt capture. Reports include host time and end-to-end
simulated MIPS, including startup and JSON serialization.

## Preserved results

`build/pipeline-directed-full-alu/results.json` passes eight guest runs, three
negative fixtures and the actual native processor guard test. A fixed2048-op
generated dependency corpus covers all30 admitted ALU mnemonics. An independent
integer oracle checks all14 output registers on each hart under both adapters
(84 full-width values); the graph retains all2048 exact encoded instructions
on both Shuttle harts. The independent
stream retires514 instructions in265 modeled hart cycles on each Shuttle,
versus1542 under the frozen conservative fixture. The dependency chain takes525
cycles. Rocket remains1028 in either mode. These are fixture observations, not
hardware reference measurements or accuracy claims.

`build/pipeline-memory-regression-final/{results,pipeline-regression}.json` passes
the existing six address-routed memory cases and seven refusals with the pipeline
enabled. `pipeline/regress.py` records its fixture transformation; its historical
runner and guest inputs are preserved in the snapshot. Re-run it against a
coordinated native/CRT epoch rather than mixing the newer finite UART's drain
protocol with this old immediate-output plugin.

`build/pipeline-zephyr-scalar-mask7/results.json` passes six actual Zephyr regions
on all three harts. `build/pipeline-zephyr-mixed-mask7/results.json` passes nine
scalar/RVV/VME regions with the explicit VME ownership/context ABI. The scalar
graph records27,172 pipelined instructions, with peak packets[4,3,0]. These are
physical three-hart software tests under a synthetic timing fixture. Their
binary/plugin/ELF/source hashes and old board inputs are retained; they do not
certify RTL context ordering or the next UART epoch.

The next integration step is to review/rebase the small pipeline extension onto
the frozen clocked-UART native epoch, rebuild its matching plugin, refresh the
directed/memory/Zephyr gates, then compare source pipeline phases and throughput
against the saved-Iris Verilator reference. Broader frontends, scalar execution
classes, asynchronous vector/VME execution and cache/coherence timing remain
required before calibration and held-out performance validation.
