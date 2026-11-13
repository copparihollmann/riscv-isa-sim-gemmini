# U250 dual-Shuttle VME bitstreams (2026-11-12)

Target: 2× Shuttle harts (0/1), VLEN256 / DLEN128, INT8 OPU (`VectorParams.opuParams`),
128-bit system bus, 16 GiB target memory, FASED `FRFCFS16GBQuadRank` (detailed DDR3
FR-FCFS timing; U250 DDR4 is only the host backing store). Built on as3 with Vivado 2021.1.

| Host freq | WNS | TNS | firesim.tar.gz sha256 |
|---|---|---|---|
| 15 MHz | +0.054 ns | 0 | 86ac25b1abb2e09042dc1a5533d99f0a760e87916dccaec0e4b41aa4a4bde623 |
| 25 MHz | +0.055 ns | 0 | 449c00014b50ad61cf88665a3460b3716a1e14a1b49ecb72bfca35e2f3b76460 |

Where the large artifacts live (not in git):
- Build tree + full results: `as3:/scratch/copparihollmann/u250-vme-20261112/`
- Run copy: `firesim1:/scratch/copparihollmann/bitstreams/u250-vme-20261112/` (SHA256SUMS)
- Shared copy: `/nscratch/copparihollmann/bitstreams/u250-vme-20261112/`

Sources: Chipyard b4542facf6cc9457f6e358e8f80a8b3a0ff5df19 plus `patches/chipyard.patch`
(also pushed as branch `iris-vme-u250-20261112` on copparihollmann/chipyard), Saturn
536774bd + `patches/saturn.patch` (FireSim OPU clock-gate bypass), FireSim e1bdea8b +
`patches/firesim.patch` + `firesim-untracked/deploy/firesim-native`. Exact pins in
`submodule-status.txt`. `provenance/`, `scripts/`, `results/*/manifest.json` are the
original build records.
