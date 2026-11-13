# Whole-CPU counter read phase

`build.py` links a read-only C++ observer with the existing compiled standalone
Iris RTL objects. It does not alter SV, target memory, inputs, host polling or
counter policy. `run.py` executes the identical scalar probe ELF and retains
pre/post-eval CSR, retirement, WB and Shuttle RF observations. Unavailable Rocket
RF fields are JSON null. Counter-update ordinals are not claimed as absolute
target clocks.

```sh
python3 hardware/csr_phase/build.py --output build/csr-phase-observer-v2
python3 hardware/csr_phase/run.py --observer build/csr-phase-observer-v2/build.json \
  --output build/csr-phase-scalar-v1
python3 hardware/csr_phase/analyze.py --run build/csr-phase-scalar-v1 \
  --output build/csr-phase-proof-v2 --verify
```

The shown directories are existing immutable evidence. Use new directories for
new builds/runs; omit `--verify` to create a new analysis capsule. No hardware is
contacted. The full compiled RTL/source closure is referenced by its frozen
capsule SHA; observer sources, binary, libraries, ELF, raw observations and
coherent signature are retained separately.

The completed run has exactly the same448-byte coherent signature as the
unobserved run. Independent analysis checks152 sampled counter-update edges and
48 real CSR reads across all three harts. Every read matches the actual ELF and
the CSR pre-edge register value. On Shuttle, command6 writes that old value over
the addressed counter's ordinary increment. Rocket command2 leaves counting
enabled. The addressed CSR is decoded from the real instruction, rather than
inferred from a retained PC alone.

For all32 Shuttle reads, COM's result enters WB on that edge, and the actual
destination RF receives the same bits one500MHz edge later. Each straight-line
body is independently decoded as256 ADDIs, with one or eight register chains.
The observed read values match every field of the six coherent measured records.
Shuttle's mcycle read timestamps are264/137 core edges apart while its visible
values differ by263/136. Rocket's physical and visible intervals are259/259.

This confirms the source counter behavior in the whole saved CPU. It does not
select the simulator's COM tick convention, correct the model, certify all
functional behavior, or attest equivalence with Ethan's FireSim image. The
original collector's257-on-all-harts expectation still fails and remains
untouched. See [the source unit proof](../../pipeline/CSR_READS.md) and
[captured-read profiling](../../timing/COUNTER_READS.md).
