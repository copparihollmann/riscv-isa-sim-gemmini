# Attention correctness and measurement preparation

These tools prepare separate candidates from the exact production ELF that
failed on the FPGA. They do not patch the running experiment, RTL, image, driver
or Zephyr context implementation. The original failure is still unresolved.

The retained production identity is
`08e652a4accc395c0799d9667dfffd2b6c2432dbdff678336a732de1a1ed69dd`.
Its FPGA failure was INT8 VME, causal prefill, B1/Lq64/Lkv64/Hq32/Hkv4/D64,
repetition3, first bad coordinate head19/query44/channel0. There were64 final
output mismatches, no reported input/guard/KV reconstruction errors, and a guest
failure rather than a timeout. The earlier intrusive row diagnostic passed, so
that diagnostic alone cannot certify the production sequence or identify a fix.

`build.py` creates a handoff diagnostic preserving all three cases, the original
global RVV-then-VME order, seven repetitions, quantizer/softmax/matrix objects and
IRQ policy. It records ordinary integer metadata: command sequence, mstatus,
and the owning thread's software matrix save/restore counts. It adds no FP,
RVV or VME CSR reads and no intermediate payload copies. It dumps its records
after the operations. It also preserves complete final outputs on failure.
Its code/data layout and execution timing still change, so it is performance
ineligible even if it passes.

The INT8 quantizer currently dispatches16 kernels per invocation. At the two
Hq32 cases, each query head has Q quantization16, softmax11, probability
quantization16, QK1 and PV1:45 team dispatches, plus128 cache-quantization
dispatches per complete operation. The Hq4 SpectFormer case uses softmax6.
The complete42-trial diagnostic therefore expects47,936 team commands plus
one matrix-registration command. This is a source-derived count, not a measured
latency or proof that each handoff spills matrix state. Its first Spike run
passed42 trials and47,937 metadata records with zero matrix saves/restores.
That observation cannot establish the hardware interrupt/context behavior.

`build_three_pass.py` creates an18-trial measurement candidate: three geometries
times INT8 RVV/VME times three sequential repetitions. It poisons final outputs
and fences before the clock starts, records shared-mtime dispatch boundaries
including initial/final wake and matrix registration, and retains H0 whole and
per-phase counters. H2 reads no performance CSRs. Each trial checks every final
word, guards, immutable inputs and reconstructed KV; the final output of every
route/case also receives an independent full host comparison. First/second/third
ordered passes are reported separately; the third is validation-conditioned
reuse, not a certified warm-cache or cold-start measurement. All18 trials,
six full host output certificates and1,242 phase windows passed the initial
functional Spike run. These are functional results, not FPGA cycle predictions.

Both routes include dynamic quantization and FP32 scale/mask/softmax/epilogue;
the contractions use the same encoded INT8 values. No native FP8 RVV execution
or FP8 hardware qualification is claimed by this sequence.

The private `attention-recovery-20261111-v1` campaign contains source-bound
ready packets, validators and a managed continuation:

1. Retest the unchanged production executable at42 trials. Its seven-pass
   sequence is retained specifically because the original fault happened on
   the fourth invocation.
2. Run the42-trial handoff diagnostic only if the first qualification passes.
3. Run the18-trial measurement candidate only if both preceding jobs pass.

Each ELF receives a separate managed kill/setup/run/owned-kill lifecycle,
complete fresh inspection/authorization and shared lock, then immutable capture
and independent archive/output checks. Separate ELFs are necessary here to
retain an unchanged binary control and isolate instrumentation changes.
Failures are archived and stop further automatic launches. The watchdog resets
on ordered checksum-matching successful UART regions, allowing100 minutes of
inactivity; the allocation/cleanup budget remains an independent upper bound.
The continuation has a finite06:00UTC November12 deadline inside the existing
user grant. A passing qualification sequence does not establish the cause or
reliability of the original intermittent failure, and does not automatically
release the broad sweep.

Original failed runs, superseded local preparation attempts, and their receipts
are preserved. No public figures or results are pushed by these tools.
