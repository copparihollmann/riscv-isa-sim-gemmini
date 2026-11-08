# Experimental single-row vector-load front

This opt-in component lets scalar arithmetic and branches continue after one
vector load retires its CPU front, while the existing memory response remains
pending. The response publishes only the owned destination bytes and their
knownness masks. Full VRF/MRF guards remain active.

It reduces one source of CPU blocking. Successive loads, load/VME overlap,
physical VRF bank arbitration and full LSU/coherence timing remain unqualified.
The shipped fixtures and provider defaults are unchanged. The simulator does
**not** meet a global ±2% timing target.

## Scope and boundaries

The fast path requires hart 0 or 1, M-mode, valid `e8,m1`, `vstart=0`, and an
unmasked unit-stride, single-field `vle8.v` with `VL=1..32`. The byte span must
fit one 32-byte block and one page in readable mapped DRAM. Address bits must
be defined. A side-effect-free PMA/PMP/mapping check rejects unsafe early
retirement; active load triggers also reject the fast path. Unsupported loads
retain their original execution/fault path.

One non-speculative architectural-head load is admitted per hart after prior
unit work drains. Only base scalar integer instructions and control flow may
progress while it is pending. Other memory operations, RVV/VME, configuration,
CSRs/counters, fences, interrupts and faulting or unknown instruction fetches
wait for the response. Scalar writes to the original address register cannot
change the captured request address.

Front retirement marks the existing VS/VSTART state without publishing numeric
VRF/MRF data. The original memory-service coefficients, fractional accounting,
cache dependencies and response owner remain unchanged. Typed byte transports
are sampled at that response and published only after both front retirement and
data return. Unknown input bits stay unknown; tails and unrelated registers
stay unchanged. Unexpected post-admission faults fail explicitly.

The real Compute128 source-cut test observes PFC front permission at EX+2 while
D responses are withheld. The native experiment uses the existing one-edge
RRD-to-EX bridge plus those two PFC edges. This does not qualify the complete
CPU/unit bridge or its physical memory service. Compute128 has a 32-byte ATL
port but issues **16-byte Gets** for this path. The legacy `atl_beats` feature
must not be interpreted as physical request counts.

## Enable and test

Use a fresh copy of `source_compute.fixture` or `source_os.fixture` and append:

```text
empirical_vle8_front single-row-e8m1-scalar-only-v1
```

Select that copy with the native launcher's `--iris-timing-fixture` argument and
include its digest in the execution receipt. Keep the original fixture intact.
The directed runner below performs that derivation and uses the build's verified
three-hart descriptor, per-hart ISAs, memory map, boot devices and fatal-aware
launcher. It requires no Merlin checkout and contacts no FPGA.

```sh
python3 iris/tests/compute128_vle8_withheld.py \
  --sdk "$SATURN_SDK" --sdk-report "$SATURN_SDK_REPORT" \
  --output "$OUT/compute128-proof"

python3 iris/tests/vle8_permission.py \
  --build "$BUILD" --output "$OUT/processor-permissions"

python3 iris/tests/vle8_front.py \
  --build "$BUILD" --riscv-gcc "$RISCV_GCC" --dtc "$DTC" \
  --output "$OUT/directed"
```

`SATURN_SDK` is the frozen directory containing `saturn_timing.hpp`,
`saturn_timing_ownership.hpp` and `libiris_saturn_live_bridge.a`. The source-cut
runner accepts `--cxx` for its C++20 compiler. The permission runner obtains the
exact compiler, source headers and SDK link recipe from `BUILD/build.json`.
Every output directory must be new. Drivers retain compiler diagnostics, failed
stdout/stderr, executable/input digests and bounded execution receipts.

The source-cut test covers VL 1, 3, 16 and 32 at two reset seeds and reconstructs
all 1,024 VRF bytes from observed physical scrub/write events. The native suite
covers 18 cases: full and partial byte knownness, unchanged tails, overwritten
address registers, masked/segmented/cross-block and wider-load fallback,
precise faults, and an IPI delivered with a load pending. The 11 processor
checks include real trap/debug/trigger paths and implemented-PMP read denial.
Current hart-0/1 DTB PMP CSR accesses instead produce their existing precise
illegal-instruction trap; the test keeps these cases distinct.

## Recorded experiment and limits

The [fresh committed-source validation](validation/committed-8923470-v1.json)
records the rebuilt native/UART/launcher and all rerun gates. Its same-ELF
240-region timing and numeric results reproduce the historical v2 experiment
below; the two build identities remain distinct.

[Validation references](validation/single-vle8-front-v1.json) pin the source
revisions and archived proof/report digests. The paired benchmark used the
identical FPGA ELF: ten frozen fitting shapes, two kernel variants, 240 regions.
All outputs, guards, checksums and instruction counts matched. All 119,040 loads
matched the intended `e8,m1` cohort; 131,548 scalar instructions retired while
loads were pending. That count is not physical unit utilization.

| Fitting-only diagnostic | Before this component | Experimental v2 |
| --- | ---: | ---: |
| Median absolute cycle error | 48.42% | 33.76% |
| p90 absolute cycle error | 71.82% | 50.28% |

No held-out timings or parameter fitting were used. The remaining errors are
substantial. `source_compute` retains its existing MM `TK=1,2,4` boundary and
refuses `TK=3`; the full four-format FP8 corpus was additionally checked with the
supported `source_os` profile. Hart 2 and multicore/Zephyr timing receive no new
accuracy certification. The final committed-source build has rerun its gates,
recorded separately in [committed-build validation](validation/committed-8923470-v1.json); archived
experimental validation does not transfer automatically.

New callbacks are nonvirtual. Processor/MMU layouts are unchanged. New owner
storage is appended to the timing adapter, and its profile flag uses prior
alignment padding. This preserves existing member offsets on the checked host
ABI; rebuild the native code rather than assuming arbitrary old object
allocations remain compatible.
