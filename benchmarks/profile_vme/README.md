# Full event graphs from a real three-hart ELF

The demonstrated packet uses the immutable selected28 native and fatal-aware
provider. Both compute harts execute the existing `matrix_mac`, `matrix_setup`
and `matrix_drain` source helpers for UINT8→INT32 and E4M3→FP32. Hart2 executes
ordinary RVV additions and checks that VME is illegal there. The host independently
checks144 active result words,48 initialized padding words, six mcycle regions
and six actual minstret pairs.

The native, provider, calibrated parameters and original fixture are untouched.
The job fixture changes only the `empirical_profile` history token from
`bounded` to `full`. Both runs have identical stdout, debugger readback and all12
cycle-prefix records. The full graph also captures12 minstret reads.

From the repository root, use fresh directories:

```sh
PYTHONPATH=. python3 benchmarks/profile_vme/build_buffered_v4.py \
  --output build/my-vme-profile-guest

python3 -m iris_model.graph_run_buffered \
  --model build/empirical-28a0-guard-staging-v2/manifest.json \
  --elf build/my-vme-profile-guest/profile-vme.elf \
  --layout build/my-vme-profile-guest/readback-layout.json \
  --history bounded --output build/my-vme-bounded --timeout 120

python3 -m iris_model.graph_run_buffered \
  --model build/empirical-28a0-guard-staging-v2/manifest.json \
  --elf build/my-vme-profile-guest/profile-vme.elf \
  --layout build/my-vme-profile-guest/readback-layout.json \
  --history full --output build/my-vme-full --timeout 120

python3 timing/profile_vme_full_graph_v4.py \
  --build build/my-vme-profile-guest \
  --bounded build/my-vme-bounded --full build/my-vme-full \
  --output build/my-vme-profile
```

The runner keeps
all three provider-declared ISAs, the real memory regions, UART/ROM/DTB and fatal
launcher. A timeout terminates only its owned local process group and records
failure. No hardware is contacted.

The guest buffers results instead of generating a large post-measurement UART
polling trace. Standard Spike debugger commands inspect its completed memory,
then resume execution to normal HTIF exit; there is no `quit` command. The guest
prints `P` after the observations and drains the actual UART. Its final HTIF
publication uses a NOP loop while the host observes completion. The preserved
v3 guest instead used WFI and exposed the current model's all-harts-parked
guard; no native fix is implied by this completion-runtime choice.

The executed example is in `build/full-graph-VME-profile-v4/`: `summary.json`
contains per-hart, per-resource and ELF-bounded function attribution;
`trace.json` opens in Perfetto. `observed-regions.txt` contains actual stored
guest CSR values, joined to the graph's captured CSR instructions and results.
These host-produced lines are clearly distinguished from guest UART stdout.

MAC payloads represent requested algorithmic work credited on modeled
completion. All four matrix regions independently account for4096 MACs each.
The event resource busy fractions describe modeled in-flight spans. They are
not measured physical accelerator utilization. Function attribution describes
operation PCs, including speculative work; it does not count function calls.
Assembly symbols without nonzero ELF bounds and ROM instructions may remain unattributed.

Physical per-level bytes, DRAM bandwidth, physical MAC completions, roofline
ceilings and calibrated stall causes remain unavailable. The report leaves them
unavailable rather than treating requested bytes as physical traffic. Eight CPU
operations remain unfinished at HTIF exit, so the full trace honestly retains
its partial-frontier status despite normal guest completion. All measured regions
and matrix backend work completed before that frontier.

Earlier verbose and failed guest epochs remain under `build/full-graph-VME-*`.
The verbose successful run produced a3.05GB graph; the compact demonstrated graph
is about239MB and its Perfetto trace about339MB. Full history has host-memory and
disk costs. It does not change the calibrated model or certify its accuracy.
