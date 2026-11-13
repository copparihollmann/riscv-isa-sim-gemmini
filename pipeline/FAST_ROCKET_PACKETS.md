# Experimental Rocket packet timing

The optional fast packet path feeds actual initialized instruction words into
the source-derived Rocket IBuf. It supplies at most one four-byte fetch word
per core edge, retains a split 32-bit instruction across two accepted words,
and consumes instructions in order. It does not evaluate Verilator models.

Enable it in an explicitly experimental empirical fixture with:

```
empirical_rocket_packets source-IBuf-demand-4B-v1
```

The machine still has all three physical harts. Source-derived plain C++
Shuttle frontends may be enabled independently with `shuttle_frontend`; their
strict unknown-RAS refusals remain effective. Omitting that independent flag
selects the older empirical Shuttle frontend explicitly. There is no automatic
fallback after a source-model refusal.

`fast_rocket_ibuf.hpp/.cpp` implements the saved source IBuf/RVC transfer.
`fast_rocket_packets.hpp` and the checked implementation add a demand-driven
word producer. The producer reads side-effect-free instruction bytes and their
known masks, rather than issuing data-cache loads. Runtime opcode decoding
computes branch immediates. Predictions use the existing lightweight BHT/target
cache. The complete Rocket Frontend, BTB, RAS, TLB and physical Icache have not
been translated into this producer. The existing empirical Icache service
remains an approximation with separate calibration provenance.

Each accepted word has an ownership ID. Instructions retain their supplying
word IDs, including both words of a split instruction. Prediction metadata is
captured with the offered word and remains stable through backpressure. A
buffer wait schedules a real subsequent core edge; it must not create a fake
trap operation. Actual MEM misprediction, trap entry, control transfer,
FENCE.I and load-coherence replay redirect speculative packet state. This does
not set the architectural PC, cancel an accepted memory request, repeat a
load, or publish speculative register effects.

The model refuses an unknown required instruction word, inconsistent
architectural/buffer heads, missing ownership, clock reversal and illegal
phase calls. Failed API calls are terminal capability/protocol failures for
that instance; recovery after a refusal is not qualified. The packet path
requires the actual three-hart reset/boot configuration.

Evidence and frozen epochs:

- `build/fast-rocket-ibuf-component-v1` independently reconstructs the IBuf
  source proof: 300,000 continuous edges, 6.3 million physical-output checks,
  exhaustive RVC register-field checking, 16 guards and three corrupted-model
  controls. This reference is saved Iris RTL, not an Ethan-image attestation.
- `build/fast-rocket-packet-flow-proof-v1` checks 64 literal ELF instruction
  streams against the RTL IBuf on every edge: 229,376 checks, 65 guard checks
  in each of two host builds, 17 refusals and two corruption controls. Its
  explicitly warm branch fixture contains no measured cycle labels.
- First native epoch `build/empirical-rocket-packets-frozen-c67e8031` passes
  K1 and all 2,304 CPU-layout numeric/PC/retirement rows. All 128 long warm
  Rocket wide-instruction rows have under 0.52% absolute error in that
  development corpus. Cold/short failures remain. Four positive-cost OS
  groups exposed a missing Rocket load-replay redirect; this epoch is not
  qualified for those groups.
- Successor `build/empirical-rocket-packets-frozen-cdeeca09` adds only the
  source packet redirect on an actual conservative load-coherence replay,
  plus more informative guard diagnostics. The accepted cache response is
  retained. `build/rocket-packet-replay-repair-proof-v1` preserves the exact
  failing parcel sequence and a one-million-instruction progress control.
  Complete OS exit is a separate gate; the capped control is not an exit
  certificate.
- `build/empirical-rocket-packets-history-parity-v2` verifies byte-identical
  guest counters, output, complete CSR prefixes and packet streams with full
  versus bounded history. Its actual source-refill witness has four D beats
  sampled and the final D operation still unissued. Older completed D input
  held across an off-clock/CDC phase was not observed or qualified.

`IRIS_ROCKET_PACKET_TRACE=<new-file>` exports accepted words, instructions and
actual redirect reasons. Summary metrics count edges and transfers; the idle
hold metric counts host observations, not target cycles or utilization.
`IRIS_EMPIRICAL_FEATURES=<new-file>` preserves the normal source-counter and
region feature contract. Source frontend carry-in metadata identifies a line
owner, not the PC of an instruction allegedly waiting for that line.

`create_rocket_packet_companion.py` creates a source delta on frozen901 and
independently reconstructs every target native source file. The frozen native
builder/capsule records the matched UART library. Never pair arbitrary build
headers or mutable plugin files with a frozen binary.

These are component and development results. Full timing, image association,
held-out +/-2%, physical utilization, full ISA timing and speed acceptance
remain unqualified. No instruction PC, benchmark name or observed golden cycle
count is used as a prediction key.
