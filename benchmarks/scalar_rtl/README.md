# Identical-ELF scalar RTL probe

The results below describe the original256-operation experiment. Later
source-derived counter/pipeline corrections and genuinely fresh component
validation are documented in [COMPONENT_VALIDATION.md](COMPONENT_VALIDATION.md).
The original collector, ELF and failed receipt remain unchanged.

This no-UART fitting probe runs a warmed, straight-line256-ADD dependency chain
and256ADDs across eight independent chains on every physical hart. The identical
ELF is used by the standalone RTL and Spike. Counter brackets include the
counter-read instructions; they exclude setup, output stores and checksum folding.
The compact CRT explicitly relies on FESVR PT_LOAD zero fill. It is not a claim
of the same startup/cache state as an arbitrary production ELF.

```sh
python3 benchmarks/scalar_rtl/build.py --output build/scalar-rtl-probe-v1
python3 benchmarks/scalar_rtl/collect.py --build build/scalar-rtl-probe-v1 \
  --output build/scalar-rtl-reference-v1 --kind rtl --timeout 240
```

Every output directory must be new. `--kind spike` requires an explicit matched
`--binary` / `--uart` pair and accepts `--fixture` for the uncalibrated online
model. The source-bound native-RAM RTL loader is required; stock loadmem hooks
are no-ops. No hardware is contacted. Raw logs,448-byte coherent TSI signature,
input/ELF/binary/library hashes and exact input bytes are retained.

The first saved-Iris run exited0 with all guest checksums/done flags correct,
but the strict collector failed: Shuttle reports256 retired instructions between
the two reads, versus257 in Spike and Rocket. The failure remains in its original
receipt; no expected value was relaxed. `report.py` separately freezes the raw
observations and labels this counter-phase discrepancy explicitly.

For native646538e0 with source500MHz clocks and synthetic serialized boundaries,
Shuttle dependent work measured263RTL cycles versus267model cycles (+1.52%);
independent work measured136 versus140 (+2.94%). Rocket measured259 versus777
(+200%) because it still uses the conservative fixture. All data and identities
are in `build/scalar-rtl-observation-v1/report.json`. The model was not fitted.
This single fitting shape, source/read-phase discrepancy and unattested standalone
FIR do not qualify held-out ±2% accuracy for Ethan's image.
