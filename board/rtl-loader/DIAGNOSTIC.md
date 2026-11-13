# Saved-RTL memory response observation

This is a local, separately identified saved-IrisConfig experiment. It is not
an observation of Ethan's loaded FPGA image. The model uses native FIRRTL
memories, explicit sideband ELF preload, a CRT relying on ELF-loader BSS zero
fill, and a two-state Verilator initialization seed. Original binaries, source
variants, timeouts and raw outputs remain preserved.

The scalar48-byte boot ELF completes through ordinary TSI. Selected three-hart
HPM and rdtime probes complete with coherent TSI mailbox reads; their closed
capsule is `build/rtl-reference-hpm-rdtime-final/reference.json`.

Longer vector probes expose a traffic-sensitive incomplete execution. The
reduction `vector-memory-counted.c` contains no floating-point arithmetic.
Only hart2 executes vector work, while all three harts boot and participate in
synchronization. Every iteration explicitly checks VL/VTYPE/VSTART for
`256/0xc3/0` and `1/0x1d8/0`. All matrix and reserved vtype fields are zero;
the latter is ordinary e64,m1 with the source altfmt bit and tail/mask policy.
Each iteration checks every byte of a256-byte load/store result using an OR
that is zero exactly when all bytes equal0xa5.

Eight iterations complete with64 hart2 checks. Nine differ in only one loaded
instruction byte, at0x80000422, and reach the RTL cycle limit. The same nine
iteration ELF completes with72 checks when a separate host adapter waits4096
TSI ticks between HTIF polls. Both positive results have all three done flags
and `failed=0` in the coherent TSI mailbox. That changes real coherent host
memory traffic and timing; it is not a general fix or a calibration default.
Sixteen memory iterations also complete under that host variant, while a
longer FPComp sequence still reaches another incomplete frontier.

`build/rtl-memory-frontier-v1/report.json` freezes the8/9/backoff controls and
1531 sampled fields. The observed frontier has17 outstanding TL reads, all four
load ROB slots occupied, no response for the load-order head, and an empty load
compactor. Ten-thousand-testbench-cycle sampling repeatedly sees the same
control phase. It does not prove an absence of intermediate transactions.

The per-target-clock observer in `packet_main.cc` resolves that ambiguity.
`build/rtl-memory-packets-v1/report.json` independently matches1973 accepted
load requests with1956 responses by testbench cycle130000. It finds no duplicate
active tag or unmatched response. The difference17 agrees with the RTL counter.
Later response/reissue traffic continues, while the oldest outstanding
tag12/address0x80003940 accepted at99057 remains missing. The last observed
response is at129989. This is a blocked-head/reissue pattern, not evidence that
the entire SoC has stopped clocking or that the FPComp unit failed.

Cold SEW64/altfmt1 masked-vfsgnj probes complete259 checks on each hart with
scalar initialization, vector initialization, and fenced vector initialization.
The long-sequence failure is therefore not sufficient evidence that this
instruction or vtype is unsupported. Accepting an altfmt configuration also
does not imply that hart2 implements FP8 matrix or arithmetic instructions.

Explicit guest fences between each of the three operand loads allow the
nine-iteration memory control to finish under the original host polling policy.
The full16-case FPComp probe also finishes on all three harts with those load
fences and explicit4096-tick host backoff:52 assertions per hart, including an
OR comparison of all1024 masked-output bytes per hart. These are different,
fully identified test ELFs and stronger ordering conditions. Their six-program
positive-reference capsule is
`build/rtl-selected-vector-references-v1/report.json`; verify it with
`python3 board/rtl-loader/vector_references.py --verify`. The unfenced behavior
and the hardware/fabric gate that causes it remain unresolved.

Recheck the frozen observations with:

```sh
python3 board/rtl-loader/certify.py --verify
python3 board/rtl-loader/memory_frontier.py --verify
python3 board/rtl-loader/packet_frontier.py --verify
```

The failing fabric/ordering gate has not been identified. Unknown reset state,
the native memory lowering, preload/cache state and host traffic remain relevant
assumptions. Full RTL qualification, deployed-image association and timing
calibration stay false. No FPGA operations were performed for this diagnosis.
