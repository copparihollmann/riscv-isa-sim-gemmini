# Iris SoC functional and cycle-approximate Spike model

**Latest recorded capabilities and results — 2026-11-07.** This
[`iris-model` branch](https://github.com/copparihollmann/riscv-isa-sim-gemmini/tree/iris-model)
contains the Iris-specific Spike implementation, based on upstream
`72958551566a30f19444bd7e354552824e4d0a98`. The compiler-facing integration is
[`ucb-bar/iris-mlir`, `handwritten-implementation`](https://github.com/ucb-bar/iris-mlir/tree/handwritten-implementation),
which pins the model revision.

The model supports compiler/kernel functional iteration, three-hart Zephyr
execution and experimental timing/profiling. **The overall ±2% timing target is
not met.** The strongest accuracy is in isolated RVV arithmetic and VME compute;
concurrent OS work and memory/computation overlap retain substantial errors.

**Fork build check:** clean native build
`cc9767615437f72ce7200d75df2aea39d6769a77b9a953c9c5c9bfc0d097c9ea`
passed all 32 directed functional cases and the baremetal, Zephyr and source
profiling smokes, with byte-identical stdout to their frozen references. The
profile smoke admitted three regions and produced JSON/Perfetto output.
[Build/run guide](iris/BUILD.md) · [exact rebuild evidence](iris/provenance/fork-rebuild-validation.json).
These migration checks do not establish new timing accuracy; the timing tables
below identify the separate, historically measured binary.

## Current capabilities

| Physical hart | Core / vector unit | VLEN / DLEN | Supported model role |
| --- | --- | --- | --- |
| 0, 1 | Shuttle + Saturn + VME | 256 / 128 bits | RVV integer and IEEE FP16/32/64, configured FP8/BF16 operation subset, VME INT8→INT32 and FP8 matrix compute |
| 2 | Rocket + Saturn DMA vector unit | 256 / 256 bits | Boot, scalar control, synchronization and ordinary RVV integer/IEEE FP; VME and MX FP8/BF16 arithmetic raise illegal-instruction traps |

- All three heterogeneous harts remain instantiated, including when only one or
  two are matrix workers. Detailed timing work prioritizes compute harts 0/1.
- Physical memory/device behavior includes the two 128-KiB TCMs, 128-KiB system
  scratchpad, 4-GiB DRAM address map, console, CLINT timers/IPIs, cross-hart
  atomics/LR/SC and Zephyr execution. The shared-resource timing model is approximate.
- Guest `mcycle` and `mtime` expose modeled time; `minstret` tracks retirement.
  Runs support deterministic scheduling with a seed and fatal-aware termination.
- `source_compute` enables finite source VADD/FADD/VME control actors. Unsupported
  geometry/active source-vector IRQ contexts refuse explicitly. `source_os` is a
  separately tested Zephyr profile with new VADD/OPU/specialized FENCE actors
  disabled and recorded effective costs retained. Accuracy does not transfer
  between these profiles.
- JSON and Perfetto/Chrome outputs provide per-hart/region/function source
  accounting. Pipe-valid occupancy, controller busy and command age are distinct
  modeled quantities. Physical FPGA utilization, useful hardware HPM/TracerV
  measurements, physical memory traffic and hardware rooflines are unavailable.

## Recorded timing accuracy

These tables compare the **frozen native binary
`35a804964d7882f36a8892d7672dcfbbc7becc89c87e2d830c149820c1291388`**
with the measured Ethan FireSim image. They describe that exact tested binary.
The source import relocates external include paths into this repository; a new
build does **not** automatically inherit its historical timing qualification.

Signed error is `100 × (model − FPGA) / FPGA`; positive means the model predicts
more cycles. P90 uses nearest-rank `ceil(0.90 × count)` on absolute errors. All
regions, repeats and measured phases were retained, without outlier or overhead
subtraction. See [machine-readable results and evidence digests](iris/results.json).

### Single-hart isolated compute

Harts 0 and 1 run individually, with the other harts parked. The 1,320 measured
regions include memory and overlap cases as well as arithmetic/matrix compute.

| Scope | Regions | Median signed error | Median absolute error | P90 absolute | Maximum absolute | Within ±2% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Isolated compute: all cases | 1,320 | +0.065% | 0.155% | 6.522% | 150.587% | 1,110/1,320 |
| Hart 0 alone | 660 | +0.057% | 0.129% | 6.522% | 149.243% | 560/660 |
| Hart 1 alone | 660 | +0.065% | 0.155% | 6.506% | 150.587% | 550/660 |

The isolated arithmetic/matrix subset is substantially stronger:

| Scope | Regions | Median signed error | Median absolute error | P90 absolute | Maximum absolute | Within ±2% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| RVV integer add | 576 | +0.032% | 0.129% | 0.508% | 2.370% | 573/576 |
| RVV floating add | 432 | +0.049% | 0.104% | 0.605% | 1.144% | 432/432 |
| VME INT8 matrix | 48 | +0.193% | 0.193% | 0.752% | 11.111% | 47/48 |
| VME E4M3 × E4M3 matrix | 48 | +0.057% | 0.097% | 0.383% | 0.843% | 48/48 |

These finite cases cover the measured LMUL/SEW and matrix geometries; they are
not a guarantee for arbitrary RVV or VME programs. The FP8 timing rows above
cover E4M3×E4M3. Loads, stores, row moves and memory/compute overlap account for
much of the full-suite error; the worst isolated total error is 150.587%.

### Multicore Zephyr and control interactions

All three OS harts remain present. The campaign uses hart 2 as scalar
coordinator and pinned compute workers on hart 0, hart 1, or both. The one-worker
Zephyr rows are distinct from the isolated baremetal experiment above.

| Scope | Regions | Median signed error | Median absolute error | P90 absolute | Maximum absolute | Within ±2% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Zephyr: all regions | 648 | -3.571% | 4.706% | 27.751% | 96.764% | 159/648 |
| Zephyr: hart 0 compute, hart 2 control | 162 | -3.571% | 3.922% | 27.751% | 62.366% | 42/162 |
| Zephyr: hart 1 compute, hart 2 control | 162 | -3.571% | 3.922% | 27.751% | 62.366% | 42/162 |
| Zephyr: harts 0+1 compute, hart 2 control | 324 | -3.922% | 4.706% | 27.751% | 96.764% | 75/324 |
| Zephyr: reserved validation subset | 192 | -24.615% | 24.615% | 28.947% | 90.489% | 32/192 |

The reserved subset has **24.615% median absolute error**, and only **32/192**
regions are within 2%. The broader RVV subset has 2.768% median absolute error
and 5.229% P90; multicore/OS matrix timing is less accurate. The comparison
retains three regions with retired-instruction-count mismatches. Interrupts and
peer traffic are included as measured; this is not an isolated contention-only
causality measurement. Hart-2 cycle accuracy was not scored.

Predictions froze before timing-label release. These references are now opened
and cannot be reused as a fresh blind hold-out after adapting the model. The
broad model comparisons used a controlled postmeasurement stop; they establish
neither normal end-to-end runtime accuracy nor simulation MIPS. No simulated
MIPS or whole-workload speed claim is available for these captures.

## Functional evidence and limits

The latest broad FPGA batch passed **648 regions and 181,440 independently
checked active values plus guards**: RVV SEW8/16/32, LMUL1/2/4/8, matrix shapes
8/16/32, INT8 and all four E4M3/E5M2 operand-format pairs, one/two compute
workers and three trials. A separate nine-checksum INT8 Zephyr example completed
normally on both the FPGA and frozen OS model, using harts 0/1 for compute and
hart 2 for scalar control.

These results establish those concrete executions. They do not certify every
ISA case, FP8 special value, competing vector/tile owner, context migration or
whole GPT-OSS/Llama/Gemma/TinyLlama workload. Complete loaded-image/source
association and the overall ±2% target remain unverified. The source model's
memory/overlap path and concurrent matrix timing still need work.

[Detailed provenance and interpretation](iris/RESULTS.md) records the full
report SHA256 values, source pins, subgroup definitions and remaining gates.
The model source is in `riscv/` and `iris/`; generated component SDK archives
remain explicit external build dependencies. Existing upstream build guidance
below describes stock Spike and does not replace the Iris component build recipe.

---

## Upstream Spike documentation

Spike RISC-V ISA Simulator
============================

About
-------------

Spike, the RISC-V ISA Simulator, implements a functional model of one or more
RISC-V harts.  It is named after the golden spike used to celebrate the
completion of the US transcontinental railway.

Spike supports the following RISC-V ISA features:
  - RV32I and RV64I base ISAs, v2.1
  - RV32E and RV64E base ISAs, v1.9
  - Zifencei extension, v2.0
  - Zicsr extension, v2.0
  - Zicntr extension, v2.0
  - M extension, v2.0
  - A extension, v2.1
  - B extension, v1.0
  - F extension, v2.2
  - D extension, v2.2
  - Q extension, v2.2
  - C extension, v2.0
  - Zbkb, Zbkc, Zbkx, Zknd, Zkne, Zknh, Zksed, Zksh scalar cryptography extensions (Zk, Zkn, and Zks groups), v1.0
  - Zkr virtual entropy source emulation, v1.0
  - V extension, v1.0 (_requires a 64-bit host_)
  - P extension, v0.9.2
  - Zba extension, v1.0
  - Zbb extension, v1.0
  - Zbc extension, v1.0
  - Zbs extension, v1.0
  - Zfh and Zfhmin half-precision floating-point extensions, v1.0
  - Zfa extension, v1.0
  - Zfinx extension, v1.0
  - Zmmul integer multiplication extension, v1.0
  - Zicbom, Zicbop, Zicboz cache-block maintenance extensions, v1.0
  - Conformance to both RVWMO and RVTSO (Spike is sequentially consistent)
  - Machine, Supervisor, and User modes, v1.11
  - Hypervisor extension, v1.0
  - Svnapot extension, v1.0
  - Svpbmt extension, v1.0
  - Svinval extension, v1.0
  - Svadu extension, v1.0
  - Svade extension, v1.0
  - Sdext extension, v1.0-STABLE
  - Sdtrig extension, v1.0-STABLE
  - Smepmp extension v1.0
  - Smstateen extension, v1.0
  - Smdbltrp extension, v1.0
  - Sscofpmf v0.5.2
  - Ssdbltrp extension, v1.0
  - Ssqosid extension, v1.0
  - Zaamo extension, v1.0
  - Zalrsc extension, v1.0
  - Zabha extension, v1.0
  - Zacas extension, v1.0
  - Zawrs extension, v1.0
  - Za64rs, Za128rs extension, v1.0
  - Zicfiss extension, v1.0
  - Zicfilp extension, v1.0
  - Zca extension, v1.0
  - Zcb extension, v1.0
  - Zcf extension, v1.0
  - Zcd extension, v1.0
  - Zcmp extension, v1.0
  - Zcmt extension, v1.0
  - Zfbfmin extension, v0.6
  - Zvfbfmin extension, v0.6
  - Zvfbfwma extension, v0.6
  - Zvabd extension, v0.7
  - Zvbb extension, v1.0
  - Zvbc extension, v1.0
  - Zvkg extension, v1.0
  - Zvkned extension, v1.0
  - Zvknha, Zvknhb extension, v1.0
  - Zvksed extension, v1.0
  - Zvksh extension, v1.0
  - Zvkt  extension, v1.0
  - Zvkn, Zvknc, Zvkng extension, v1.0
  - Zvks, Zvksc, Zvksg extension, v1.0 
  - Zvzip extension, v0.1
  - Zicond extension, v1.0
  - Zilsd extension, v1.0
  - Zclsd extension, v1.0
  - Zilx extension, v0.1
  - Zimop extension, v1.0

Versioning and APIs
-------------------

Projects are versioned primarily to indicate when the API has been extended or
rendered incompatible.  In that spirit, Spike aims to follow the
[SemVer](https://semver.org/spec/v2.0.0.html) versioning scheme, in which
major version numbers are incremented when backwards-incompatible API changes
are made; minor version numbers are incremented when new APIs are added; and
patch version numbers are incremented when bugs are fixed in
a backwards-compatible manner.

Spike's principal public API is the RISC-V ISA.  _The C++ interface to Spike's
internals is **not** considered a public API at this time_, and
backwards-incompatible changes to this interface _will_ be made without
incrementing the major version number.

Build Steps
---------------

We assume that the RISCV environment variable is set to the RISC-V tools
install path.

    $ apt-get install device-tree-compiler libboost-regex-dev libboost-system-dev
    $ mkdir build
    $ cd build
    $ ../configure --prefix=$RISCV
    $ make
    $ [sudo] make install

If your system uses the `yum` package manager, you can substitute
`yum install dtc` for the first step.

Build Steps on OpenBSD
----------------------

Install bash, gmake, dtc, and use clang.

    $ pkg_add bash gmake dtc
    $ exec bash
    $ export CC=cc; export CXX=c++
    $ mkdir build
    $ cd build
    $ ../configure --prefix=$RISCV
    $ gmake
    $ [doas] make install

Compiling and Running a Simple C Program
-------------------------------------------

Install spike (see Build Steps), riscv-gnu-toolchain, and riscv-pk.

Write a short C program and name it hello.c.  Then, compile it into a RISC-V
ELF binary named hello:

    $ riscv64-unknown-elf-gcc -o hello hello.c

Now you can simulate the program atop the proxy kernel:

    $ spike pk hello

Simulating a New Instruction
------------------------------------

Adding an instruction to the simulator requires two steps:

  1.  Describe the instruction's functional behavior in the file
      riscv/insns/<new_instruction_name>.h.  Examine other instructions
      in that directory as a starting point.

  2.  Add the opcode and opcode mask to riscv/opcodes.h.  Alternatively,
      add it to the riscv-opcodes package, and it will do so for you:
        ```
         $ cd ../riscv-opcodes
         $ vi opcodes       // add a line for the new instruction
         $ make install
        ```

  3.  Add the instruction to riscv/riscv.mk.in. Otherwise, the instruction
      will not be included in the build and will be treated as an illegal instruction.

  4.  Rebuild the simulator.

Interactive Debug Mode
---------------------------

To invoke interactive debug mode, launch spike with -d:

    $ spike -d pk hello

To see the contents of an integer register (0 is for core 0):

    : reg 0 a0

To see the contents of a floating point register:

    : fregs 0 ft0

or:

    : fregd 0 ft0

depending upon whether you wish to print the register as single- or double-precision.

To see the contents of a memory location (physical address in hex):

    : mem 2020

To see the contents of memory with a virtual address (0 for core 0):

    : mem 0 2020

You can advance by one instruction by pressing the enter key. You can also
execute until a desired equality is reached:

    : until pc 0 2020                   (stop when pc=2020)
    : until reg 0 mie a                 (stop when register mie=0xa)
    : until mem 2020 50a9907311096993   (stop when mem[2020]=50a9907311096993)

Alternatively, you can execute as long as an equality is true:

    : while mem 2020 50a9907311096993

You can continue execution indefinitely by:

    : r

At any point during execution (even without -d), you can enter the
interactive debug mode with `<control>-<c>`.

To end the simulation from the debug prompt, press `<control>-<c>` or:

    : q

Debugging With Gdb
------------------

An alternative to interactive debug mode is to attach using gdb. Because spike
tries to be like real hardware, you also need OpenOCD to do that.
We'll use the following test program:

```
$ cat rot13.c
#include <stdio.h>
char text[] = "Vafgehpgvba frgf jnag gb or serr!";

// Don't use the stack, because sp isn't set up.
volatile int wait = 1;

int main()
{
    int i = 0;
    while (text[i]) {
        char lower = text[i] | 32;
        if (lower >= 'a' && lower <= 'm')
            text[i] += 13;
        else if (lower > 'm' && lower <= 'z')
            text[i] -= 13;
        i++;
    }
done:
    printf("decoded text: %s\n", text);
}
$ riscv64-unknown-elf-gcc -g -Og --specs=semihost.specs -o rot13 rot13.c
```

To debug this program, first run spike telling it to listen for OpenOCD:
```
$ spike --rbb-port=9824 -m0x10000:0x20000 rot13
Listening for remote bitbang connection on port 9824.
...
```

In a separate shell run OpenOCD with the appropriate configuration file:
```
$ cat spike.cfg 
adapter driver remote_bitbang
remote_bitbang host localhost
remote_bitbang port 9824

set _CHIPNAME riscv
jtag newtap $_CHIPNAME cpu -irlen 5 -expected-id 0xdeadbeef

set _TARGETNAME $_CHIPNAME.cpu
target create $_TARGETNAME riscv -chain-position $_TARGETNAME

gdb report_data_abort enable

init
arm semihosting enable
halt
$ openocd -f spike.cfg
Open On-Chip Debugger 0.12.0
...
Info : starting gdb server for riscv.cpu on 3333
Info : Listening on port 3333 for gdb connections
riscv.cpu halted due to debug-request. Semihosting is active.
...
riscv.cpu: target state: halted
```

In yet another shell, start your gdb debug session:
```
$ riscv64-unknown-elf-gdb rot13
...
Reading symbols from rot13...
(gdb) target extended-remote localhost:3333
...
(gdb) load
...
(gdb) set $sp=0x2fff0
(gdb) b main
Breakpoint 1 at 0x10202: file rot13.c, line 5.
(gdb) c
Continuing.
Disabling abstract command writes to CSRs.

Breakpoint 1, main () at rot13.c:5
5       {
(gdb) print text
$1 = "Vafgehpgvba frgf jnag gb or serr!"
(gdb) until done
[riscv.cpu] Found 4 triggers
main () at rot13.c:16
16          printf("decoded text: %s\n", text);
(gdb) c
Continuing.

Program received signal SIGTRAP, Trace/breakpoint trap.
0x00019ff8 in _exit ()
(gdb) 
...
```

On the OpenOCD terminal you will have:

```
...
decoded text: Instruction sets want to be free!
semihosting: *** application exited with 0 ***
riscv.cpu halted due to breakpoint. Semihosting is active.
```
