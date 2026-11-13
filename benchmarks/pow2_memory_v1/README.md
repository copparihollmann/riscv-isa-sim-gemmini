This packet measures one active hart at a time at 13 power-of-two address footprints: 1 KiB through 4 MiB. Every footprint runs on each of harts 0, 1 and 2, with two full dependent-pointer traversals and three trials: 117 cohorts and 234 measured regions.

The exact four-instruction loop executes one 8-byte load per 64-byte address slot. All three harts prepare disjoint DRAM windows before a footprint/trial group. Inactive harts wait using the qualified WFI/MSIP generation-barrier runtime. Six measurements occur without console output; hart 0 then prints the six buffered records and a group frontier. Earlier traversals, preparation and the preceding console output affect cache history. No flush, cold-cache, physical-miss or physical-traffic claim is made.

Each record preserves raw mcycle/minstret and enclosing CLINT mtime samples. The source timebase is 500 kHz, or 1,000 source core cycles per tick. CLINT sampling is outside the CSR region, includes sampling overhead, and permits equal timestamps for sub-tick intervals. Nothing is subtracted from the raw observations.

The split was frozen before hardware: all 4 KiB, 64 KiB and 512 KiB cases across every hart, pass and trial are reserved. The coordinator alone reads their timing labels. The other 180 regions form the training export. That export also removes absolute timestamps to prevent disclosure through gaps between retained rows.

Frozen local evidence is in `build/pow2-memory-single-packet-closure-v1/report.json`. Seeds 0 and 17 passed all 234 regions; an actual kernel-omission ELF failed all 234 and exited nonzero. The proof checks 117 permutations over 1,179,504 indices, the compiled case table, 80-byte record ABI, exact load loop and CLINT sampling order.

The coordinator's prepared job is `runs/fpga-pow2-memory-single-v1-001`. Its manifest changes legitimately during the managed lifecycle; the closure's manifest digest is explicitly PRELAUNCH.

Postcapture analysis uses the additive reader adapter, preserving the frozen v1 analyzer and its original failure:

```sh
python3 firesim/analyze_pow2_packets_v2.py --kind memory \
  runs/fpga-pow2-memory-single-v1-001 \
  --output build/NEW-ROOT-ONLY-analysis \
  --training-export build/NEW-TRAIN-only-export
```

Only the coordinator runs this command on the combined archive. The v2 change retains the already inventory-hashed `ready.json` that the shared reader otherwise omits, verifies immutable prepared admission records and invokes the frozen v1 validator unchanged. It does not change the guest, RTL, runtime or observed measurements. Neither local functional tests nor these observations certify complete source/image association or a universal 2% timing bound.
