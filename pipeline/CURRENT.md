# Current isolated pipeline epoch

The fifth isolated candidate adds a distinct single-issue Rocket EX/MEM/WB
pipeline alongside Shuttle's two-lane pipeline. Native
`91c404614db4c86247777d16cce4d8a18c68d27f38ba2b63b235aae2254684ee`,
UART`8b78272d399c5cddaacb5373201008926dcf1a07945a2792b0aacbc4c04b8e87`.
See [ROCKET_PIPELINE.md](ROCKET_PIPELINE.md) and the closed review epoch
`build/rocket-pipeline-frozen-91c40461`. Prior candidates remain immutable;
full RTL/timing/held-out2% certification remains false.

The fourth isolated candidate adds source-legal counter EX/COM overlap at
native`e0600503a0fdf0fe3391619273fe583715c64f79d08b099d6b8c35b24adf8c26`,
UART`a531fe309cf3d6b2577bc30a6b57baf40f6a192f26d5d79eaeada24f095b2c22`.
See [COUNTER_PIPELINE.md](COUNTER_PIPELINE.md) for the three-file source delta,
independent dependency/EX-hold corpus, exact256 debug observations and remaining
Rocket/SoC timing gaps. Its review closure is
`build/counter-pipeline-frozen-e0600503`; prior epochs stay immutable.

The next source-counter review epoch is implemented and tested separately at
native`8930257d62c58d53c3f1f9c9503b953806aaa69a04f0d72ed613385b2ec1e34c`,
matching UART`cde52d1646ba9493903dec78438513acba606ae19a4c525e739eaa4e746d667e`.
See [COUNTER_POLICY.md](COUNTER_POLICY.md) for its source/whole-CPU proof,
program-visible counter changes, captured-read profiler and remaining timing
errors. Its closed review snapshot is `build/counter-policy-frozen-8930257d`;
verify it with `python3 pipeline/freeze_epoch.py --snapshot build/counter-policy-frozen-8930257d --verify`.
No primary publication is implied. The646 epoch below remains immutable
historical evidence and lacks the newly proved counter-edge behavior.

Native SHA256 `646538e05746dac9cfa014ea8fe068964260cad870edfe65deea39549c2efb51`,
matching finite-UART plugin
`cc8f65c2e4423c2f9eab1b3f89b09a6e3e01dde650a809801c9c718114eaf4c3`.
The immutable closure is `build/pipeline-frozen-646538e0`; verify it with:

```sh
python3 pipeline/freeze_epoch.py --verify
```

The parent is the frozen HPM32/clocked-UART model at
`build/snapshot-5e6cc309`: native
`5e6cc309b8cd1085e30ee0c31b43c2bc27ef9c325136a94bfdd4d86700787f7e`,
overlay `7b92dcd4b68416f6445c908f82b4d4d34960471d207f23b045eaa78cd9750854`,
provenance `277cdec0c1cc0cd4182c75dfea9bcb69547a1d5b8beb44fbf1cada9cb2d5a8a1`.
Spike remains pinned to `72958551566a30f19444bd7e354552824e4d0a98`.
The primary package has not been modified by the isolated pipeline work.

## What changed

The twelve-file extension `pipeline-on-parent-epoch.patch` in the closure adds
the source classifier/ALU pipeline and compressed expander; adds safe direct
prefetch/context/interrupt probes to the processor; routes captured exceptions
through the ordinary trap path at COM; and connects these operations to the
existing live adapter/simulator. Its prerequisite is the exact parent overlay.
The full base-to-model patch is `iris-with-pipeline.patch`. The manifest binds
both patch hashes, the parent archive, native/plugin, actual compiler dependency
files, guest sources/ELFs and raw reports. Large JSON traces are stored as gzip
files with both compressed and uncompressed hashes.

An explicit fixture chooses either the original32-bit domain:

```
shuttle_pipeline pure-integer-sequential-frontend
```

or the expanded mixed16/32-bit domain:

```
shuttle_pipeline pure-integer-rvc-sequential-frontend
```

`pipeline/rvc.fixture` is a complete synthetic test fixture. These flags do not
claim calibrated Iris performance. All three physical harts remain present;
harts0/1 overlap up to four two-lane packets, and hart2 retains the conservative
path. Program-visible counters, interrupts, UART and scalar memory effects share
the same live event clock. The fixture's100MHz base/hart dividers are explicit
test inputs. The UART independently uses its sourced500MHz peripheral clock.

The compressed path uses the pinned default Rocket expansion called by Shuttle,
including C.MV as ADD rd,x0,rs2. Pairing and RAW/WAW/unused-field retiming use the
expanded register fields; functional execution uses Spike's original compressed
handler at the precise PC. Fetch/admission advances by each actual2/4-byte length.
Graphs record raw instruction, length, expanded instruction, RRD, result-ready,
COM and WB events separately. Neighboring halfword bits never supply compressed
instruction control.

`pipeline/check_rvc.py` classifies all65,536 low16 inputs and verifies all15,899
admitted encodings across19 ALU groups against the standalone saved-Iris RTL
expander, with three additional upper-halfword settings per admitted encoding.
Its source snapshots, full repository SHAs, line citations and tool/module hashes
are retained. This proves the admitted expansion subset against that module;
the saved elaboration's association with Ethan's loaded image remains unverified.

## Verified gates

- `build/pipeline-rvc-directed-final/results.json`: eleven actual guest runs,
  three fixture refusals and native processor context guards. Independent
  oracles cover all30 base ALUs and all19 admitted compressed groups. The mixed
  corpus contains2048 compressed ops and292 interleaved32-bit ops; all102
  full-width register/SP observations match across three harts and both adapters.
  Precise IRQ capture, timer delivery, illegal decode,2/4-byte TCM boundaries,
  counter reads, source pairing, four live packets and seeded replay pass.
- `build/pipeline-rvc-functional32/results.json`: all32 frozen ordinary functional
  cases preserve exact stdout, stderr and status, including the unchanged
  upstream-reference cases. This preserves inherited scope; it is not a new
  whole-SoC functional certificate.
- `build/pipeline-rvc-live8/results.json`: all8 existing live semantics cases and
  three refusals pass with RV64IC enabled, including counter inhibit/write,
  source-absent rdtime, per-hart timers, idle clocks, ordering and exact exit.
  `pipeline/live_regress.py` preserves the exact native bytes and substitutes
  their matching finite UART; its wrapper receipt supersedes the original
  runner's conservative-only static scope label for this replay.
- `build/pipeline-rvc-memory/results.json`:6 address-routed memory cases and7
  refusals pass with the compressed pipeline enabled.
- `build/pipeline-rvc-uart/results.json`:12 ordinary/live UART process cases pass,
  including both clock fixtures, all256 byte values, interrupt/frame behavior,
  undefined-RX refusal and a rejected old-native/plugin pair. The native builder
  also runs the actual register/clock helper tests against the matched SDK.
- `build/pipeline-rvc-zephyr-{scalar,mixed}/results.json`: actual three-hart
  Zephyr passes6 physical-UART scalar regions and9 Ethan-profile mixed regions
  with the explicit VME ownership/context ABI. The mixed graph contains181,232
  pure instructions, including93,262 compressed instructions; both Shuttle
  harts reach four live packets. Root's strict guest-CSR profiler also joins all9
  mixed regions at `build/pipeline-rvc-mixed-profile`.

The byte-matched clocked build command is
`python3 pipeline/build_native.py --source pipeline/riscv-isa-sim-next --build build/spike-shuttle-pipeline-next`.
The directed checker accepts explicit `--source`, `--native-build`,
`--baseline-binary`, `--baseline-uart`, `--parent-source`, `--parent-overlay` and
`--guest-root` arguments, plus `--rvc`; each receipt preserves its actual commands.
Use a new output directory for changed code or parameters. The old immediate
UART and CRT from the b14 snapshot must remain paired with that historical model.

## Remaining scope

No RTL throughput/counter-phase calibration or held-out +/-2% claim exists.
Frontend fetch/cache state, prediction/misprediction, speculative branch/flush
behavior, broader scalar overlap, Rocket pipeline details, vector/VME asynchronous
sequencing/shared-FPU/VRF contention, cache/coherence and calibrated NoC/serial-TL
costs still require implementation and measurements. Pure ALU result/COM/WB
stage distances alone do not resolve those costs. Required unknown latencies
remain unknown; the explicit test rules are not fitted hardware parameters.

CFI, memory, FP/vector/VME and CSR/system instructions currently drain to the
conservative path. Unadmitted/reserved compressed encodings also drain; the
expander does not invent architectural traps. RV32, debug/single-step/triggers,
virtual/supervisor fetch and unsafe direct fetch prevent pure-path admission.
An unexpected context change or admitted-instruction trap during flight ends
the timing run with a named refusal. The existing memory adapter still refuses
unmodeled vector/translated memory cases under routed-memory timing.

The timeline retains modeled operations separately from architectural retirement.
Full tracing currently retains substantial history: the physical115200-baud
Zephyr scalar run's UART polling produces a939MB JSON graph, versus269MB for
the mixed Ethan-profile run. Both MIPS/wall time and trace costs are reported;
long-model scalability, bounded history and calibrated fast-forward remain open.
Functional model/reset/numeric limitations inherited from the parent provenance
also remain; passing these regressions does not qualify every source behavior.
