# Gemmini simulator components

One source branch carries both execution routes:

| Route | Entry point | Contents |
| --- | --- | --- |
| Phase 1 functional execution | `functional_baseline/export.py` | Packages pinned pristine Spike and the unchanged public functional extension. No timing observer or provider is included in its runtime. |
| Optional annotated execution | `../../timing/build.py` and `timing/export_config.py` | Builds the generic observer-enabled Spike core and a separate primitive-command observer. Models, prices and per-execution counter bindings are selected explicitly. |

The build command from the repository root is `python3 timing/build.py`.
See [the baseline instructions](functional_baseline/README.md),
[the observer instructions](timing/README.md), and
[the generic timing API](../../timing/README.md).

The functional receiver follows the selected board: public `libgemmini`
`ea8f7ed7afd68e001fb06ddccad9a023c990961d` for the stock U250 archive, or
`5b1254a7dc72f757442280e7f28ef30542c78533` for the 30 MHz archive. Source
packaging verifies the selected revision and parameter/header bytes; it does
not maintain another receiver.
The Spike base `9c190a07c6838f6392bafa4ad83acea462c7f759` is Chipyard's pinned
Spike revision. The newer Chipyard checkout also selects this public extension;
the older 30 MHz checkout selects `5b1254a7dc72f757442280e7f28ef30542c78533`
instead. Their receiver sources differ, so the declared extension revision must
remain part of every deployment identity.
The observer adds accounting without changing the functional extension or guest
numerics. Generic bundle building and calibration live in Merlin's standalone
`merlin-timing` package.

These are trusted simulator components, independent of the compiler under test.
They do not import `gemmini-mlir`, Merlin's compiler, xDSL, a handwritten backend
or held-out workloads. Phase 1 produces the OOT compiler from scratch. Candidate
grants expose runtime endpoints through the broker; these sources, vendor
headers and selfcheck fixtures stay outside candidate inputs.

The functional baseline packages pristine pinned source objects from this
branch's history. Keeping its packaging next to the annotated route avoids a
second maintained simulator branch. Existing build/execute receipts retain their
original source and binary identities when this packaging moves.

`stock_u250.json` names the stock build whose bitstream archive starts with
`a9a190b9`. `fire_aligned_30mhz.json` separately pins the selected 30 MHz
archive starting with `0af6f26e` and its different `libgemmini` receiver at
`5b1254a7`. Profile names and compatible software headers do not establish
timing equivalence. Neither profile has qualified timing prices.
