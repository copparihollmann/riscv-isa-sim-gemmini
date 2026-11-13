# Column-readout observation

The configured source accepts the tile-move opcode but disables the horizontal
column readout pipe. Decoder acceptance therefore does not establish a usable
column operation. This diagnostic observes the behavior without assuming a
correct transpose or inventing an illegal-instruction trap.

Both compute harts fill all 32×32 cells with distinct values, after explicitly
zeroing all four tiles. Every column attempt is surrounded by independent normal
row checks. One ELF bundles 768 known row regions and 384 raw column observations:
all 32 indices, two patterns and three trials on each compute hart. Hart2 boots,
joins barriers and then parks. Console output occurs after all data collection.
Raw column words, trap metadata, exact instruction PC, mcycle and minstret remain
available. Known row controls currently print FNV64 checksums, not individual
row words; this is not a complete bit-exact certification corpus.

```sh
python3 benchmarks/vme_column_probe/build.py --output build/NEW-column
```

The builder also makes `probe-silent.elf` by changing only the initialized
`emit_console` software input from one to zero. It proves the single file-byte
change and retains identical code, segments, symbols and probe addresses. That
flag is read after collection finishes. It does not edit RTL state or invent
hardware initialization. Silent runs expose the complete signature through the
qualified saved-FIR preload/signature harness:

```sh
python3 hardware/vme_column_probe/build_reference.py \
  --output build/NEW-column-reference
python3 hardware/vme_column_probe/run.py --build build/NEW-column \
  --reference build/NEW-column-reference --seed 1 \
  --max-cycles 20000000 --timeout 7200 --output build/NEW-column-rtl
```

The full saved-RTL run is slow through its actual CPU/memory path. Earlier runs
at a 600-second bound progressed but did not complete; they are failures, not
numeric oracle results. The original generated simulator also lacks the host
loadmem service requested by `+loadmem`; its failed runs are preserved separately.
Use the qualified preload host harness linked against unchanged frozen model
objects. This source reference remains unassociated with the full deployed
Combined image.

The primary functional model explicitly refuses column move-out with
`IRIS_UNSUPPORTED_COLUMN_MOVE`, rather than supplying fabricated data or an
architectural illegal trap. The actual refusal transcript is preserved at
`build/vme-column-probe-v1-native-refusal-seed0`. It is not a full positive
execution of this diagnostic. Parser admission fixtures exercise all three
possible classifications—illegal, accepted mathematical column, accepted other
data—and reject 16 corruptions. They are explicitly synthetic parser inputs,
not model predictions or hardware ground truth.

The sole hardware coordinator prepares/runs this as an observational experiment
using `firesim/prepare_column_probe.py` and the managed four-phase lifecycle.
The generated `launch.sh` sources the environment from its actual FireSim root;
environment source files are frozen before launch and their stdout/stderr are
captured inside the job. No direct-driver or retained-image path is supported.
The row controls have independent host goldens. Column outcomes are raw
observations, not required goldens. Validate the quiescent archive afterward:

```sh
python3 firesim/analyze_column_probe.py runs/NEW-column-job \
  --output build/NEW-column-archive-analysis
```

The analyzer keeps observed column words separate from reconstructed row goldens
and classifies them against a mathematical column only as a reference. Passing
row controls and complete observations do not certify useful column semantics,
source/image equivalence, full functional behavior or timing accuracy.

Actual managed job `runs/fpga-vme-column-probe-v1` passed all row controls and
completed all 384 column observations. None trapped and none matched the
mathematical column; each differed in 30–32 of its 32 words. Normalized output
patterns matched across all 12 hart/pattern/trial conditions for each index.
All four managed phases, owned cleanup, lock release and archive verification
passed. Bound evidence is in `hardware/actual-vme-column-observation.json` and
`build/fpga-vme-column-probe-v1-archive-analysis/report.json`. The raw fallback
data is retained rather than redefined as useful column semantics.
