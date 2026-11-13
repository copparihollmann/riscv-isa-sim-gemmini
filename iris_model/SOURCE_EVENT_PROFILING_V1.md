# Optional source-event profiling

Use the separate profiling frontend with a verified explicit descriptor and an
unstripped RISC-V ELF. Existing packages, the default selection, and
`iris_model.empirical_run` are unchanged.

```bash
python3 -m iris_model.source_profile_run_v1 \
  --model build/C12-source-composite-Merlin-adapter-package-v1/source_compute/manifest.json \
  --elf path/to/program.elf \
  --output build/my-source-profile \
  --source-events \
  --timeout 600
```

The output directory must be new. `--source-events` enables the native journal
and exports `source-profile/summary.json` and `source-profile/trace.json`. Open
`trace.json` with Perfetto. A relative filename may follow `--source-events`;
it must resolve inside the new output directory. Without this option, the
journal remains disabled. The command also preserves `stdout`, `stderr`,
`features.jsonl`, `native-summary.json` and `run.json`, including input and output
SHA256 digests, the exact three-hart launch configuration, and execution status.
Timeouts terminate and reap only the command's owned process group.

`run.json.pass` describes the guest's normal exit. `profile_pass` separately
reports whether the requested profile was produced. A profiling failure preserves
the original guest evidence and makes the CLI fail. Normal exit alone provides
no independent numerical or timing certification for an arbitrary program.

Choose `source_os/manifest.json` for the existing OS profile. Its OPU and special
OPU FENCE modes are disabled; it carries no compute-timing qualification from
`source_compute`. The frontend preserves every descriptor refusal and timing
scope. Unsupported finite FADD/OPU contexts still refuse in the native model.
Neither profile establishes full-model accuracy, source-to-loaded-image
attestation, physical traffic, or hart2 cycle accuracy.

## What the profile means

The whole-program profile includes boot, setup, unmarked code and UART work.
FADD source work requires an actual checked architectural COM event, an ELF
instruction/geometry match, and an owned source microissue and 16-byte VRF write.
Per-function attribution uses actual ELF symbol bounds; gaps remain unattributed.
Architecturally retired element counts, completed element counts and outstanding
work are distinct. Canceled reservations receive no work credit.

The FADD pipeline-valid interval for an EG accepted on source edge E and written
on E+4 is `[E+1, E+5)` for a one-base-cycle source clock. The implementation uses
`[issue+divider, write+divider)` for the actual hart divider. The union counts
source valid-entry occupancy of completed EGs. It is not physical switching or
FPGA utilization. The command-inflight trace is a separate span. Incomplete
publication/journal tails remain explicit and never become completed work.
VRF byte counts describe internal logical writes, not memory traffic.

The current 02b4 journal exposes OPU reservations and guarded K callbacks/final
entry publications. It lacks separate authoritative COM geometry and some
completion-owner fields. Consequently OPU logical MAC work and peaks are null;
ambiguous completions remain unattributed. A reserved microissue is never
presented as a completed MAC. Legacy modeled events and unknown journal kinds
remain counted/raw without being upgraded into source-qualified work.

## Explicit regions

Without supported markers, only whole-program and per-function attribution are
available. The frontend never guesses regions from successive counter reads.
By default it accepts `IRIS_REGION` JSON records with `case_id`, `hart`,
`start_cycle`, `end_cycle`, and boolean `pass: true`:

```text
IRIS_REGION {"case_id":"kernel","hart":0,"start_cycle":1234,"end_cycle":2345,"pass":true}
```

These values must match unique actual returning MCYCLE reads in the captured
prefix stream. Each boundary is checked against its ELF/ROM PC, raw instruction,
CSR number, destination, sequence and global model cycle. Program MCYCLE delta
and global observation span are reported separately; no linear projection
through WFI is assumed.

For the preserved compiler-image kernel marker format, use
`--region-format merlin-kernel-v1`. It accepts exactly
`REGION hart start_cycle end_cycle instret_delta` with a positive retired count.
Use `--region-format none` to request whole-program attribution explicitly.

Alternatively, provide `--region-map path/to/regions.json`:

```json
{
  "schema": "iris.source_event_region_map.v1",
  "regions": [
    {"case_id": "kernel", "hart": 0, "start_cycle": 1234, "end_cycle": 2345}
  ]
}
```

A map supplies names and observed endpoints, not fabricated timing. Missing,
duplicate or ambiguous CSR endpoints refuse attribution. Region completion
counts use actual writes inside the global interval and report carry-in work
separately. Hardware utilization, physical bandwidth/traffic, roofline data,
unobserved unit peaks and source CPU stall decomposition remain unavailable.

## Reproduce the small observer checks

```bash
python3 timing/build_source_profile_smoke_v1.py --output build/my-profile-guest
python3 spike/check_source_profile_run_v1.py \
  --model build/C12-source-composite-Merlin-adapter-package-v1/source_compute/manifest.json \
  --guest build/my-profile-guest/guest.elf \
  --output build/my-profile-checks
```

The control independently checks all 136 output words on three harts, matches
4,096 FADD element additions to 1,024 owned source writes, proves observer-only
numeric/CSR/native-summary byte parity, and exercises fatal, recoverable,
stripped-ELF, descriptor-digest, output-path, timeout and corrupt-join refusals.
It is a mechanism test and supplies no fitting data or accuracy certificate.
