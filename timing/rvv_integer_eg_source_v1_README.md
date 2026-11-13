# Finite Compute128 VADD controller

`rvv_integer_eg_source_v1.hpp` models the saved Saturn integer VADD.VV control path for harts 0 and 1. It accepts only unmasked, full-VLmax, vstart=0, aligned LMUL1/2/4/8 commands at SEW8/16/32/64. It contains no instruction-cost fit, CPU model, numerical register file or memory service.

The qualified source specialization has a four-entry VDQ with neither flow nor pipe, a three-entry IQ with pipe and no flow, one execute sequencer and a **one-edge VADD micro-issue-to-VRF-write** path. The physical integer execution unit has two slots because other integer instructions have different depths. VADD selects depth-minus-one zero and never occupies the second slot. The source of this distinction is IntegerPipeFactory's `baseInsns...pipelined(1)`, the saved integer decoder/ExecutionUnitint, and the full-unit differential; FADD's four-edge path is not reused.

Call `step(local_source_edge, optional_command, ports)` once per active source edge. The returned `input_fire` owns acceptance. `issue` identifies the actual 16-byte element group and operand-read event; `write` identifies its later physical write. The caller owns values, definedness and architectural visibility. VAT/command ownership must remain unique while live. Accepted backend commands have no cancellation API; speculative CPU reservations require a separate pre-acceptance owner.

The ports are external sequencer inputs: older read/write EG masks, source-read readiness, write-port availability and execution readiness. They must come from real modeled actors or an explicitly qualified fixture. They are not permission to replay observed readiness. The component computes its own queues, progress and dependencies. A full pre-edge VDQ refuses input even if it dequeues that edge; empty queues do not bypass. At empty ingress, an accepted command reaches first micro-issue three source edges later, followed by its first write one edge later. This is not a one-cycle CPU instruction claim.

`empty()` describes state **after** `step`. For a pre-edge busy/FENCE join, use the returned VDQ/IQ/sequencer prestate and `pipe` slots. The last writing edge is still busy before that edge. No CPU CSR, fence, interrupt, trap or context-switch policy is supplied by this component.

The clean qualification command is:

```bash
python3 timing/rvv_integer_eg_source_v3_build.py --output build/NEW-vadd-source-proof
```

It needs the pinned reference SDK at `build/saturn-timing-ownership-sdk-v7/sdk` and the saved compute RTL below `build/saturn-timing-component-v1-final`. SDK include order is intentional: use its `saturn_timing.hpp` before `timing/`. A header-only consumer needs C++20 and the frozen SDK header; it does not link the reference simulator.

The clean proof runs 128 complete-unit control streams and 128 nonzero numeric streams across all stated SEW/LMUL combinations, dependent/independent/chaining/WAW patterns and reset seeds 1/17. It compares 3,689,088 source fields and 153,600 VRF write events. Numeric initialization uses actual VMV.VX instructions after reset/scrub, with no internal RAM writes. Every one of 46,080 output bytes is checked independently on accepted VSE8 Put payloads and masks after full VADD drain. Three original integer-sequencer runs add 90,000 edges and 942,950 comparisons with external RAW/WAW/WAR and port backpressure. Both optimized and checked builds pass 31 API checks with 15 typed refusals. Five full-source/output-verifier mutants and three API guard mutants are rejected.

The VSE readback fixture supplies an explicit identity TLB, periodic A-channel readiness and synthetic acknowledgments after `2 + seed % 5` source edges. These are verification inputs, not DRAM/L2 timing parameters. Its physical port is 256 bits; each accepted Put transports 16 active bytes. Requested output bytes are not measured DRAM traffic.

Masked/partial-VL, fractional LMUL, other integer operations, widening/reduction, competing units/SMP, CPU publication, unknown-state policy and active interrupts remain outside this finite proof. The reference is the saved two-state source with real reset and explicit initialized operands; no loaded FPGA-image association or ±2% timing certificate is claimed. Existing native binaries, fixtures and defaults are unchanged. Initial observer/port/report-assembly failures remain preserved in their original build directories.
