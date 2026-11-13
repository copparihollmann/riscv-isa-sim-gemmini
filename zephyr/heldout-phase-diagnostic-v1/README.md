This is a disjoint, instrumented two-phase diagnostic derived from the frozen
v6 source. It executes shipped GEMM then its scalar twin,15jobs each, one compute
worker onhart0 and the original RVV producer onhart2. Hart1 runs a CPU-only
watchdog. The original worker k_thread/stack reuse, quantization, FP ownership
APIs, actual compiled MLIR/descriptor objects, generated kernels and goldens
remain unchanged. Integerstage stores, watchdog/timers and newlayout perturb
execution; no timing equivalence or calibration claim follows.

The final ready packet is build/heldout-phase-diagnostic-ready-v3/ready.json,
selecting build/heldout-phase-diagnostic-v2/diagnostic.elf (81fc50b9...). The v3
packet adds strict interpretation of CRT-zero mailboxes as "not recorded";
it reuses the identical tested v2 ELF. Earlier ready-v2/parser metadata is
historical. Positive359seed0/17 complete both phases and32regions; the forced
negative enters phase1stage1, makes no further progress, prints mailboxes and
exits HTIFstatus1. It must never count as normal completion.

Mailboxes are atomic64-bit release/acquire transports. Bits63:32 are a perwriter
sequence,31:28 physicalhart,27:24 phase,23:16 job,15:0 stage. Zero is known
CRT-initialized BSS with no stage store yet, not an invented hart/phase record.
The timeout prints three mailbox words (main, worker, producer). A stage denotes
the last store reached; it does not prove the next function's cause of blocking.

Main stages:
1 phase entered;2poison done;3worker create entry;4worker start returned;
5producer create entry;6producer start returned;7before each finished take;
8take returned;9before worker join;10join returned;11before producer join;
12join returned;13allword checks done/before printing;14printing returned.

Worker stages:
100entry;101target setup returned;110before work take;111take returned;
120/121before/after first compiled call;122/123second call;
130before completed give;131give returned;140before finished give;
141give returned, followed by unchanged normalreturn/abort cleanup.

Producer stages:
200entry;201target setup returned;210before prepare0;211prepare0done;
220before work give;221give returned;222before started take;223take returned;
230before RVV (next-buffer preparation precedes this marker);231RVV returned;
240before completed take;241take returned;250before finished give;251returned.

The normal watchdog waits5000ms of CLINT time without a change in any of these
three channels. It reads500kHz CLINT mtime, not guest writable/inhibitable mcycle.
It prints the frontier, drains sourceUART and issues HTIFstatus1. The forced
negative uses10ms and arms only after its explicit phase1 entry marker. A
scheduler/disabledIRQ/global lock or print stall can prevent this on-target
watchdog; the owned600-second host foreground watchdog remains authoritative.

The prepared job is runs/fpga-phase-handoff-diagnostic-v1-001, bound to actual
standing authorizationv4. Root is the only hardwarecoordinator, and must still
perform complete actual ownership/idle checks and hold the shared lock for
kill->infrasetup->runworkload->kill plus ownedcleanup/archive. Preparation has
not contacted hardware. The original8f driver and TSI128 are preserved; no
+max-cycles is used because startup can exceed5billion global drivercycles and
its option uses32-bit parsing. Available aggregate FASED capture is included.

After cleanup and capture:
python3 firesim/analyze_phase_handoff_diagnostic.py \
  runs/fpga-phase-handoff-diagnostic-v1-001 \
  --output build/fpga-phase-handoff-diagnostic-v1-001-analysis

The analyzer independently checks normal numerical completion, or separately
reports bounded target nonprogress with raw+decoded stagewords. It refuses a
host timeout as normal completion and does not identify a rootcause. No v6
reference timing labels were consumed, no originalv6 inputs changed, and no
FPGA operation was performed by this diagnostic's author.
