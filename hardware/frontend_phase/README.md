# Read-only whole-CPU frontend/cache diagnosis

The closed proof is `build/frontend-phase-proof-512-v3/report.json`, SHA256
`fb7329510dc4b43b7cd9f4b9d1d99eb17fb457dde3ea524733a902c4aa2ab14b`.
It uses the unchanged512-operation ELF and cached saved-Iris RTL objects.
Only a new C++main reads generated fields; no SV, TSI actor, clock driver,
memory loader or guest changes. All three observer variants produce the exact
same448-byte coherent signature as the original unobserved run.

The first observer sampled counter changes. Formal analysis caught missing boot
cache activity while counters were paused. The final observer samples the actual
`TestHarness.source.clk_i` rising edges, including those pauses, and records the
actual reset signal. Initial randomized pre-reset values are excluded until the
observed reset image establishes MC=IR=0, replacementLFSR=1 and an empty buffer.
Earlier observers and failed analysis attempts remain preserved.

The final audit verifies121,877 rows,121,819 unchanged prior qualified field
projections,196,756 source MC/IR transitions,171 complete64-byte/eight-beat
refills and all8 warm/measured512-instruction RRD/COM streams against the ELF.
Each of the7 measured warm-line misses has a directly observed eviction history.
Seven adversarial controls reject changed LFSR state, tags, validity, instruction
bits, queue pointers, counters and coherent signatures.

| Hart and measured body | Visible cycles | Frontend-empty edges | Refills |
| --- | ---: | ---: | --- |
|0 dependent|554|34|0x80000300,37edges|
|1 dependent|552|32|0x80000300,34edges|
|0 independent|431|167|0x80001100/1140/1200/1300,37/37/44/37edges|
|1 independent|299|35|0x80001300,33edges|

All four measured windows have5 EX-stall edges at their CSR boundaries and no
TLB miss, redirect or flush. The independent-body empty-edge counts exactly
equal their excess over the source pipeline's264 cycles. These are observed
overlapping signals, not additive stall categories or fitted timing parameters.

The saved Shuttle Icache has64 sets,2 ways and64-byte lines. Its16-bit Fibonacci
LFSR advances on accepted refill requests; its post-increment low bit selects
the way filled later. The tag/valid data directly show warm0x80001300 evicting
0x80000300 on both harts, followed by the measured dependent body doing the
reverse. On hart0, later main-code refills for lines0x80000100/140/200 evict
0x80001100/1140/1200. Hart1 retains those lines. The different histories explain
the different measured refill counts. Invalid tag bits are never interpreted.

Source: pinned Shuttle `ICache.scala:59-105,207-216`, saved
`ShuttleICache.sv`, `tag_array_64x46.sv` and `MaxPeriodFibonacciLFSR.sv`.
The capsule retains exact source/tool/library/ELF inputs, generated field mapping,
native observer, raw pre/post observations, signatures and independent analysis.
This is the saved standalone reference, without an attested Ethan-image link.
Full RTL/model/timing and held-out2% certification remain false.

```sh
python3 hardware/frontend_phase/build_clock.py --probe build/scalar-component-validation-plan-v2/alu512/build.json --output build/frontend-observer-new
python3 hardware/frontend_phase/run.py --observer build/frontend-observer-new/build.json --probe build/scalar-component-validation-plan-v2/alu512/build.json --unobserved build/scalar-component-validation-e060-v1/alu512 --output build/frontend-run-new
python3 hardware/frontend_phase/analyze.py --run build/frontend-run-new --output build/frontend-proof-new
python3 hardware/frontend_phase/analyze.py --output build/frontend-phase-proof-512-v3 --verify
python3 hardware/frontend_phase/check_rejections.py
```

Use new output directories for changed inputs. The next model needs causal
frontend request/replay/buffering, actual tags/replacement and refill routing
through shared memory resources. Hardcoding the observed33–44 or734–739-cycle
refills would hide the cache/history/contention mechanism and is not implemented.
