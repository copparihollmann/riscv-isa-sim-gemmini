# Saved Iris OPU sequencer component

This is a source-generated timing component for the saved IrisConfig compute
hart's `OuterProductSequencer` and its `PipeScheduler`. It preserves their
queues, counters, FP8 dependencies, readout pipeline and scoreboard internally.
No observed internal state or fitted delay is injected. It is separate from
Spike and the shared timing engine until a reviewed global composition connects
the real VRF, dispatcher, backend register and array boundaries.

The frozen capsule is `build/opu-sequencer-component-v2-final/report.json`.
Reproduce its independent verification with:

```
python3 timing/opu_sequencer_package.py --verify
```

The public C++20 SDK is `build/opu-sequencer-sdk-v1/sdk/`:
`opu_sequencer.hpp`, `opu_sequencer_schema.hpp`, and
`libiris_opu_sequencer.a`. Link with `-pthread -latomic`; public headers have no
Verilator or internal-state dependency. Use `input_fields()` and
`output_fields()` for the exact ordered field schema. The 128-bit write mask
occupies two named 64-bit words. There are 18 physical inputs and 98 physical
outputs, represented by 99 output words.

Construct `iris::opu::IrisOPUSequencer(seed)` with an explicit seed. Construction
does not reset it. Drive the physical reset input, with dispatch disabled, and
commit a real edge before dispatching work. For each core edge:

1. `evaluate(inputs)` settles source combinational logic with clock low.
2. `sample()` returns that edge's outputs and per-word `defined` flags.
3. `commit()` advances exactly one source core edge, then returns clock low.

A global event scheduler may repeatedly change ready/hazard inputs and evaluate
before committing. No issue/dispatch edge is added. `step()` is exactly the
composition above. A failed evaluation invalidates the pending phase;
subsequent sample/commit is refused. There is no public internal-state loader,
no snapshot API, no idle skipping, and no automatic architectural tile save.

Reset initializes valid/scoreboard/history-valid/readout-valid/tracker, but
leaves instruction/config/intents/readout payload registers uninitialized.
Undefined or inactive payload has `defined=false`; it must not be consumed as a
known value. The text driver emits `x`, not a fabricated known reset zero. This
is conservative payload qualification, not general four-state taint propagation
through the rest of the SoC. Once a legal dispatch initializes the payload, the
same outputs remain defined through stalls and idle cycles. Readout data fields
are qualified only on `write_valid`.

The accepted dispatch subset follows the saved Saturn decoder's OP-VE 0x77
INT8 / FP8 MM and OP-V 0x57 move/zero/discard entries. The SDK fails closed on an
unsupported key, wrong MM/move SEW, out-of-profile tile geometry, unresolved or
reserved FP8 rounding mode, overwide input or dispatch before reset. The input
is already **after** the real frontend's architectural acceptance: this cut
does not implement instruction fetch, vtype/mtype legality, privilege, traps or
hart capability checks. The full simulator must still provide those.

`build/opu-sequencer-audit-v2/source-contract.json` binds 12 groups of derived
facts to exact source bytes and line numbers. In particular:

- Compute VLEN 256 / DLEN 128 gives 64 EGs, four VRF banks, four 32×32 tiles, and
  16x16 subtiles mapped to 16 entries/cell. The source configuration and physical
  port geometry are both recorded.
- Two source FP8 history slots block a same-entry issue for two subsequent
  edges, permit consecutive distinct entries, and block non-FP8 work until
  pending FP8 history drains. This is not a fixed latency charged per opcode.
- Readout cluster 0/1/2/3 requests source pipe depth 5/4/3/2. Its register capture
  enable occurs 5/4/3/2 edges after issue and write-valid 6/5/4/3 edges after issue.
  The source scheduler prevents equal completion-edge collisions.
- VRF older-read/write masks, VAT head, two read-ready signals and write-port
  reservation availability remain external inputs. EG read addresses, hazards,
  intents, bank/depth requests, issue control, delayed write EG/mask and
  scoreboard are computed internally.
- The saved backend always accepts issue, registers the control bundle before
  the array and registers array readout data with `write_reg_enable` before the
  VRF write. Those real backend flops are outside this cut and must be retained
  when composing it with the separately qualified array and VRF models.

Column **writes** are implemented and tested through row readback. This saved
configuration has `useOpuColReadout=false`, with no `shift_h`, `write_col` or
`out_col` ports. A controller column-read scheduling trace does not establish
functional horizontal readout. The component preserves the source controller
behavior; it does not invent an architectural illegal trap or a missing data
path. See `hardware/dtypes.md` for the existing discrepancy audit.

## Evidence

`build/opu-sequencer-semantic-v3/report.json` covers 14,226 dispatched operations
and 62,224 continuous edges. A separate Python oracle expands matrix work into
architectural coordinates and EG sets and schedules absolute-time FP8/readout
events. It imports neither Spike nor generated model state. It matches 6,003,273
defined words for each of seeds 0/17, and seven repeated evaluations per edge
produce byte-identical meaningful output. The corpus includes all four tiles,
four INT8 / FP8 operand type combinations, all 32 TSS indices, both move patterns,
empty/partial geometry, hazard/resource stalls and 10,009 delayed writes. Six
meaningful checker corruptions and 11 invalid input/lifecycle cases are rejected.

`build/opu-sequencer-rtl-v1/all-harts-vme.json` is an independent whole-SoC
reference run. Both compute harts execute actual INT8 / FP8 instructions, all four
FP8 format pairs, four tiles, partial 17×31 / tk 2, and row/column writes with row
readback. Each checks 1,472 actual int32/FP32 bit patterns. Hart 2 concurrently
produces scalar memory traffic and verifies its real OPU instruction refusal.
All three complete, exit 0, with the raw TSI signature preserved.

`build/opu-sequencer-replay-v1/report.json` continuously drives each controller
from the actual reset and physical ports captured in that whole-SoC run. Each
hart replays 110,232 edges, 93 dispatches, 641 micro-issues and 368 readout writes.
The generated SDK and independent semantic oracle both match 19,477,440 defined
physical words in total. Five meaningful physical-output corruptions are also
rejected. No waiting flag, history entry, FIFO or internal pipeline state is
used as a model input. The observer's scoreboard alias is the exact source
`assign io_wsboard = wsboard`, recorded separately because the initial read-only
visibility list omitted that final port; it reads the retained register.

`build/opu-sequencer-sdk-v1/benchmarks.json` reports about 5.2–5.4 million
controller edges/s in process (seven passes). Input parsing, output digest and
text I/O are outside the measured loop; evaluation, sample copies, definedness
and output stores are included. The SDK's ordered 64-bit field mix is checked
independently against the semantic proof. Ready/hazard inputs are revised and
restored on all 62,224 edges without adding time or changing the restored result.
Nine additional SDK lifecycle errors are refused. This is **component host
cost**, not simulated SoC MIPS or a claim about compiler iteration speed.

## Provenance and limits

Authoritative controller bytes are the saved standalone IrisConfig FIR
`f1b36c8565bd67825c636af40079ea048a9196bf1e36fcb719270411270201f4`, lowered by
CIRCT 1.75.0 with native FIRRTL memories and built by Verilator 5.052. This differs
from the saved FireSim FIR. Source context uses full 40-character repository
SHAs and the captured dirty patches in `hardware/manifest.json`; the saved
elaboration's association with those checkouts and Ethan's loaded image remains
unverified. All source/tool/ELF/raw-capture bytes are bound in the capsule.

The independent whole-SoC reference uses a read-only port observer, two-state
RTL, explicit native-RAM ELF preload with PT_LOAD BSS zero fill, and the recorded
compact CRT. It proves the selected functional observations under those stated
harness assumptions. It does not establish unknown reset irrelevance for the
entire SoC, deployed FPGA equivalence, complete ISA certification, or held-out
cycle accuracy. No hardware was contacted by this work; no timing parameters
were fitted and no ±2% or full-SoC timing certification is claimed.
