# Audited Iris hardware evidence

See the separate [datatype audit](dtypes.md) for scalar, vector, and VME operation
support by hart, including FP8 hardware and advertised/configured discrepancies.

Run `python3 hardware/audit.py` from the project root to regenerate `manifest.json`,
the small evidence snapshots, and tracked-source patches from Ethan's local tree.
Use `--root PATH --output PATH` to audit a different checkout without modifying it.
Missing required evidence terminates the audit instead of supplying defaults.

This manifest describes local source and elaboration evidence. It does **not**
certify that the deployed FPGA image was built from those inputs. The bitstream
hash, its build-input digests, calibration data, and exact elaboration build-input
digests remain unknown. The manifest therefore sets `certified` and
`calibration_usable` to false.

## Provenance

| Repository | Local commit |
| --- | --- |
| Chipyard | `b4542facf6cc9457f6e358e8f80a8b3a0ff5df19` |
| Saturn | `536774bd4c5e3bcd7813a4a0dc72fc87e5818532` |
| Rocket | `fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0` |
| Shuttle | `a536ed1df91a0f65770e36758291d02a8cb929c4` |
| Testchipip | `86c9a824fd42b854526018f9111087b0f3d1d31c` |
| Chipyard Spike checkout | `9c190a07c6838f6392bafa4ad83acea462c7f759` |
| FireSim checkout | `69b17767e0b227e31ea341c50899e49f02d6f5ea` |

Chipyard declares FireSim `e1bdea8bb042b900995436ecc3d7c44100eb9da0`;
the local checkout differs. Chipyard and Saturn also have tracked modifications.
Of particular relevance, the local Iris config changes the NoC endpoint mapping
from `debug[0]` to `serial_tl_0_0`, and Saturn disables the OPU clock gate.
The manifest records full tracked diffs and their hashes, plus individual source
hashes. A commit alone is insufficient to identify this local build input.

Clean, detached clones of the four primary source pins are under
`third_party/{chipyard,saturn,rocket-chip,shuttle}`. Their local source bundles are
under `third_party/source-bundles`; origins point to the upstream repositories.
Submodules inside those clones have not been recursively initialized. The
functional model's newer Zvt-capable Spike identity is recorded by its own build
provenance and must not be confused with the older Chipyard Spike pin.

## Extracted facts

The frozen `IrisFiresimNOCflushCombinedConfig` [device tree](evidence/firesim-dts.dts)
and [memory map](evidence/firesim-memmap.json) provide the following values. Every
manifest fact includes its evidence identity and original line interval; evidence
identities resolve to SHA-256 hashes and repository revisions.

| Component | Observed configuration |
| --- | --- |
| Harts 0–1 | Shuttle; 8 KiB I-cache and 8 KiB D-cache, 64 sets, 2 ways, 64-byte blocks |
| Hart 2 | Rocket; 16 KiB I-cache, 128 sets, 2 ways; 16 KiB D-cache, 64 sets, 4 ways; 64-byte blocks |
| Compute vector units | VLEN 256, DLEN 128, with OPU; source-derived |
| Rocket vector unit | VLEN 256, DLEN 256, DMA configuration without OPU; source-derived |
| DRAM | Base `0x80000000`, size `0x100000000` (4 GiB) |
| TCM 0 | Base `0x70000000`, size `0x20000` (128 KiB) |
| TCM 1 | Base `0x70020000`, size `0x20000` (128 KiB) |
| System scratchpad | Base `0x580000000`, size `0x20000` (128 KiB); 2 banks in source |
| L2 | 512 KiB, 4 banks, 4 ways, 512 sets per bank, 64-byte blocks |
| CLINT | Base `0x2000000`, size `0x10000`; MSIP and MTIP connected to all three harts |
| Timer timebase | 500,000 Hz |
| Console | SiFive UART at `0x10020000`, interrupt source 1 through PLIC |
| PLIC | Base `0xc000000`, size `0x4000000` |
| Power-on reset vector | `0x10000`, explicitly connected in generated FIRRTL |
| Program boot-address register | MMIO `0x1000`, source default `0x80000000` |

The scratchpad is marked `status = "disabled"` in the DTS but is still R/W/X
addressable in the generated memory map. Do not translate that DTS marker into an
access fault or treat it as general OS-managed DRAM. The memory map marks atomics
unsupported there and supported in DRAM and both TCM ranges.

The compute-hart ISA strings contain `xsfmmbase`, `xsfmm32a8i`, `xsfmm32a8f`, and
`xsfmm32t`; hart 2's string omits them. The complete per-hart strings are in the
manifest; one global ISA string is insufficient to represent this design.

## VME and Zephyr implications

The [matrix decoder](evidence/matrix-config-decode.scala) configures matrix state;
the [Saturn instruction definitions](evidence/saturn-decode.scala) determine the
OPU instructions' actual decode fields. VME moves and discard share a funct6
slot but differ in `rs2`. Do not decode by funct6 alone or enforce only one
canonical full instruction word where RTL deliberately ignores bits.

The [OPU](evidence/outer-product-unit.scala) has four accumulator tiles, with tile
edge `VLEN / 8 = 32` and 32-bit accumulation. Its storage uses `Reg`, not
`RegInit`: reading uninitialized tile state has no deterministic architectural
value established by this evidence. Require software initialization or fail with
an explicit unknown-state diagnostic. Do not silently promise zeroed tiles.
The [sequencer](evidence/outer-product-sequencer.scala) implements discard as a
no-op and derives A's sign/format from instruction bit 7 and B's sign/format from
the configuration's `altfmt`, not another opcode bit.

The [boot ROM](evidence/boot-rom.S) waits for MSIP, has hart 0 wake the secondary
harts, and passes hart ID and DTB address into the program. The generated reset
constant is `0x10000`, despite Rocket's generic `BootROMParams` default of
`0x10040`. A Zephyr model must preserve the actual boot protocol, the distinct
hart capabilities, timer frequency, and shared-memory/device ordering.

## Timing remains uncalibrated

The [clock summary](evidence/firesim-clocks.freq-summary) includes 500, 1000, and
100 MHz target clocks. Hart-to-domain assignment and the deployed-image match
still need verification. CPU DTS `clock-frequency = 0` is unspecified metadata,
not a physical zero clock. The reported 60 MHz FPGA simulation throughput is a
host execution rate and must not determine guest `mcycle` or `mtime`.

The FireSim source config connects Iris's 16-bit phit/flit serial-TL link to a
bringup device clocked at 100 MHz. Link transaction latency, effective payload
bandwidth, DRAM model settings, cache/TCM/scratchpad latency, issue restrictions,
and contention behavior require exact image association and measurements. No
fitted or certified cycle parameters are included in this audit.

## Attempted RTL smoke

The existing compiled VCS `chipyard.harness.TestHarness.IrisConfig` executable and
its runtime directory were copied into the isolated `build/rtl` directory. A
bounded launch of the exact three-hart smoke ELF failed before simulation with
exit status 127: `libvirsim.so` was unavailable. `ldd` reported eleven missing
Synopsys runtime libraries, and the configured `/tools/synopsys/vcs` installation
and `/tools/commercial/flexlm/flexlm.sh` license setup were not mounted.

[rtl-probe.json](rtl-probe.json) retains the actual command, binary/ELF hashes,
dependency failures, and separate VCS/FireSim DTS identities.
[rtl-probe.stderr](rtl-probe.stderr) retains the loader error. No license checkout
or RTL execution occurred, and no timing data was collected. Restoring the VCS
runtime mount is a concrete prerequisite; the presence of an executable alone
does not establish a runnable RTL reference. The VCS IrisConfig and FireSim
combined config have distinct DTS hashes and must not silently share calibration.
