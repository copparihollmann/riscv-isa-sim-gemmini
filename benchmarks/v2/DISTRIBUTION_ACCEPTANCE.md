# Exact three-hart functional distribution acceptance

```sh
python3 benchmarks/v2/distribution_acceptance.py
python3 benchmarks/v2/distribution_acceptance.py --seed 17 --output benchmarks/v2/distribution-seed17
python3 -m unittest discover -s benchmarks/v2/tests -v
```

This adds distribution assertions to the existing v2 runner and validator. It
does not rebuild Spike or alter the frozen v1 suite. Each run executes the same
208-case v2 ELF, then compiles and executes only the missing synchronization
placement tests with the frozen common baremetal runtime.

The runner verifies all seven nonempty subsets of the exact physical harts:
`{0}`, `{1}`, `{2}`, `{0,1}`, `{0,2}`, `{1,2}`, `{0,1,2}`. It checks complete
case/hart results, exact job ledgers, core kinds, compiled case-table bindings,
pipeline roles, and producer→compute→consumer dependency declarations. Hart 2
must positively execute integer and FP16/FP32/FP64 scalar/vector work. It is not
classified as a DMA-only processor. VME compute is restricted to harts 0–1.

The hart-2 VME illegal-instruction probe is reported separately from positive
work counts. Five distributed pipelines cover vector compute on each hart and
VME compute on either legal matrix hart with a Rocket producer. Final checksums
and source-bound phase protocols verify functional dependencies; dynamic edge
timing is not instrumented or inferred from the static ledger.

The supplemental guest has **25 cases / 45 per-hart regions**:

- LR/SC shared increments for every subset, checked against independent global
  totals rather than each hart's completion count alone.
- CLINT IPI rings for every subset, including the singleton self-IPI controls.
- Explicit `fence w,w` / `fence r,r` messages for every subset. Channels use
  separate cache lines and monotonic flags; values must reach the next hart.
- Four multi-hart cases place an ordinary peer store between LR and SC and
  require SC failure with the peer's value retained. These do not identify the
  hardware reservation granule or uniquely attribute every possible SC failure.

The fenced-message checks exercise the simulator's functional ordering and do
not certify exhaustive RVWMO behavior. Inactive harts follow the existing WFI
and CLINT wakeup policy. The physical hart count stays three in every case.

`distribution-results/acceptance.json` binds executable, simulator, UART plugin,
compiler, linked library, source, corpus, generated table and console hashes.
Each attempt clears the previous pass before loading inputs; an interrupted or
failed rerun cannot retain a stale successful receipt. Simulator, UART plugin
and package provenance identities must stay unchanged through both guests.
The result is explicitly **baremetal functional acceptance**. Instruction-based
counter values and host runtime remain uncalibrated; it does not rank placements
or certify Iris cycle accuracy.

The same report snapshots the current Zephyr candidate's source identities and
records Zephyr acceptance as false. At initial review its worker range was 1–2
and it rejected hart 2 before distinguishing scalar from VME work. Subsequent
source changes are recorded afresh, but source inspection is never promoted to
a built or executed three-hart Zephyr result. The actual board port, CPU-index
mapping, interrupts, preemption, and vector/tile context handling still require
Zephyr execution evidence.
