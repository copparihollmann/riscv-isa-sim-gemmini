# Working compute-hart Zephyr example

The same diagnostic ELF passes on Ethan's FPGA image and in the packaged Spike
Zephyr profile. Harts 0/1 perform unsigned INT8 VME work; hart 2 runs the scalar
observer/control path. Boot/main remains on hart 0 in this example. All three
harts also complete the scalar GEMM/conv2d phases.

ELF SHA256:
`f5d722c41d53517416cb0314191851f30227fa63e25c93408d73361494bd33dd`.
The derived Zephyr kernel is unchanged from the recorded 558cefc overlay;
the application uses a normal ready semaphore and plain progress records.

## Run without an FPGA

From the repository root, select a fresh output directory:

```sh
python3 spike/run_source_VADD35a_v1.py \
  --package build/C12-source-VADD35a-optional-package-v1 \
  --profile source_os \
  --elf build/zephyr-mixed9-firstuse-normal-v2/zephyr/zephyr.elf \
  --output build/my-new-zephyr-model-run --timeout 300
```

The actual run exited zero in 22.45 host seconds and passed all nine independent
region checksums. It uses the three-hart 35a native with the separately tested
OS fixture; compute-profile timing results do not transfer to this profile.
[Same-ELF functional evidence](../build/zephyr-firstuse-f5d-model-FPGA-functional-parity-v1/report.json).

## Verified FPGA run

The actual managed job is `runs/fpga-zephyr-firstuse-h2scalar-v1-001`.
All four phases passed: initial kill 24.780 s, setup 116.196 s, workload 31.968 s,
final kill 24.892 s. Normal guest/driver exit zero, nine independent checksums,
owned cleanup and archive inventory validation all passed.

Archive SHA256:
`39f1f857f49312d48e93089d974834b8d769b7883f0358233b932e2c7b9a23c8`.
[Strict validation](../build/zephyr-firstuse-h2scalar-FPGA-validated-v1/report.json)
and [independent second-parser/math review](../build/zephyr-firstuse-h2scalar-FPGA-independent-review-v1/report.json).

This is finite unsigned INT8 TK1 coverage: one owner per compute hart, 32 matrix
commands/yields and a 32-word output-row checksum. It does not establish full-MRF
per-word correctness, actual context-save counts, competing owners, migration,
hart-2 vector behavior or multicore timing accuracy. The original 93a mixed
workload's timeout remains preserved; this perturbed diagnostic is not its fix
or a proof of its cause. See [diagnostic design](../zephyr/FIRSTUSE_DIAGNOSTIC_V1.md).

The exact existing image tar SHA256 is
`9bbe1f12a2b18091c28b05ea43c001e579f70c8cfef0f528fcb49003212fb776`;
the original driver ELF is
`8f78167b754097623b031f41d7e5f121f4ae368f716255fdcf574693a071c48a`.
TSI step size is 128. The runner retains the original driver, programs the FPGA
each run and uses a foreground 180-second host watchdog. Source/image build
attestation remains incomplete. These results carry no blanket ±2% certificate.

## Reproduce a fresh managed job

Follow AGENTS.md, OPERATING_RULES.md and CAMPAIGN_POLICY.md. Root remains the
sole launch coordinator. A current account/boot-bound user authorization,
complete all-user/process/device inspection and the shared group lock are
required before every phase. Busy or uncertain state stops the run.

Do not rerun or edit the consumed job. Prepare a fresh job with the current
valid authorization receipt, then complete its final input snapshots:

```sh
python3 firesim/prepare_zephyr_firstuse_diag_v1.py \
  --qualification build/zephyr-mixed9-firstuse-qualified-v2 \
  --expected-ready-sha256 6f2932aae9e96c33cd13c949ab3af3e01d8ad08e63479775f70fd68ae40dfecb \
  --authorization-receipt /absolute/current-valid-user-receipt.json \
  --memory-probe-build build/fased-readonly-managed-v2 \
  --postrun-probe-build build/fased-readonly-extended-v2 \
  --output runs/CHOOSE_NEW_JOB

python3 firesim/complete_input_snapshots_v1.py runs/CHOOSE_NEW_JOB \
  --expected-prepared-manifest-sha256 SHA_PRINTED_BY_PREPARATION

python3 firesim/run_prepared.py runs/CHOOSE_NEW_JOB
bash runs/CHOOSE_NEW_JOB/launch.sh
```

The launch script supplies the original manager environment and Conda PATH.
The unchanged runner performs kill → infrasetup → runworkload → kill, phase
ownership rechecks and quiescent capture outside the job on success or failure.
Copying an image never substitutes for programming. No direct-driver or retained
image path is permitted.

After owned cleanup and capture, use a fresh analysis output:

```sh
python3 firesim/analyze_zephyr_firstuse_diag_v1.py runs/CHOOSE_NEW_JOB \
  --output build/CHOOSE_NEW_ANALYSIS
```

The snapshot-completion helper is local only. It preserves the preceding
manifest and fills all final digest-bound byte copies after optional hook
installation. Its actual fresh preparation verified 683/683 standalone inputs;
13 refusal controls protect used jobs, repeated completion and active lifecycle
state. Runtime/hook projections remain unchanged.
[Local-only validation](../build/prepared-input-snapshot-completion-controls-v1/report.json).
Older FPGA archives honestly retain 75 observer dependencies through matching
current bytes/original digests rather than standalone copies; their receipts
are unchanged.
