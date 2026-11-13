# Firstuse diagnostic, NEW application epoch

This is a functional-only instrumented fork of mixed9. The pinned cd45 Zephyr
kernel plus exact558cefc ownership overlay is unchanged. It keeps three workers
and scalar GEMM/conv first, replaces hart2 vector work with scalar32Bcopy×32 and
an active scalar CLINT observer, then runs the existing harts0/1 VME32/yield
kernel. The normal program emits nine independently checked regions plus actual
observer readiness/last-point snapshots/completion. Its third case is NEW:
`zephyr.vme.scalar-control`, with roles vme.compute0/1 and scalar.control2.

Observer readiness is a normal kernel semaphore, signaled before main releases
compute gates. The first app version's tight ready-poll normal runs timed out
after scalar6 on native359; controlled debugger stepping of that same ELF
completed. Those failures are preserved. The semaphore successor passes normal
seed0/17 without debugger intervention. This corrects the diagnostic handshake;
it identifies no cause or fix for the original93a hardware noncompletion.

Only the new application records progress. Constant stages surround ownership
API entry/return, configuration, tilezero, operandload, each MM/yield, rowmove
and outputstore/fence. There is no new kernel context instrumentation. An API
entry without return cannot distinguish globalIRQlock, firstVSET trap, lazy
restore or tile initialization. Compiled m8 restore presence is not evidence
that hardware executed it.

Slots use the existing source-uncacheable scratchpad range beginning58001e000,
with disjoint128B per physical hart. Hot recording uses plain volatile64 stores,
compiler barriers, actual mhartid and raw-mscratch logical CPU, worker/pin and
last recorded MSTATUS/MIE/MIP/mcycle. It has no FENCE/AMO/FP/RVV or OS call.
Initialization/arm/final transport fences are outside hot vector-state steps.
Stable sequence is an observed consistency check; metadata can race and no
current PC/state or physical completion is inferred.

Hart2 is started/acknowledged first and then polls actual CLINT500kHz directly,
without sleeps/new timer interrupts/kernel calls in its active observation loop.
The5000ms target deadline is not5000ms host wall time. On timeout it dumps the
three last records, drains SiFiveUART from actualDIV and requests HTIFfailure3.
Main cannot enter normal HTIFsuccess until this worker gives finished; timeout
never returns/gives it. Thus the diagnostic failure path is the sole terminal
writer at timeout. Chosen console is SiFive; workers do not use HTIF. If UART,
CLINT, scratchpad/NoC or transport cannot progress, the owned180s host watchdog
remains authoritative. No target-timeout capture is guaranteed in every stall.

A separately compiled forced-stall control stops hart0 before ownership enable,
uses a10ms target deadline and genuinely exits native status1 after timeout
and snapshot output, with no DONE. Both seed0/17 pass this negative control.
That ELF is NEVER hardware-admitted. Normal seed0/17 genuinely exit0 with all9
goldens. Machine-code guards prove the scalar observer/progress bodies have no
FP/vector instructions and hot stamping has no FENCE/AMO. The production normal
ELF includes the actual tohost3 path. This is native transport proof, not a claim
the FPGA diagnostic has already run.

The original93a failure remains a failed full workload: six scalar records,
no three vector records, no DONE, actual script exit124, full managed cleanup.
Its physical/logical fields are source- and machine-code-backed actual mhartid;
boot0 plus compiled DT order0,1,2 deterministically maps CPU indices, rather
than secondary arrival order. App and ownership API independently guard VME to
physical0/1. This does not identify the stalled hart/PC or exclude other faults.

Root alone may launch a fresh verified job with original8f/image, TSI128,
180s foreground watchdog/360s phases, fresh auth/boot/complete inspection/shared
lock, kill/setup/workload/kill, owned cleanup and capture. Strict normal archive
qualification still requires allnine goldens, observer envelope, actual dated
script exit0 and complete managed lifecycle. A nonzero target diagnostic is a
failed workload with a possible qualified diagnostic capture, never normal
completion. No old validator is relaxed and no timing/cause certification follows.
