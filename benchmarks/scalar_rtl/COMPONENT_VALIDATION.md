# Scalar component validation

The actual CPU counter/read-phase and scalar pipeline changes are tested with
source-bound, identical-ELF programs on all three harts. These experiments concern
straight-line integer ALU and counter paths. They do not certify the full SoC,
complete frontend/cache behavior, vector/VME timing, final workload holdouts or
Ethan's deployed image. No FPGA is contacted.

The first frozen e060 model predicted ten lengths before reference execution:
0,1,2,3,7,8,31,32,64,512, dependent and eight-chain streams on all three harts.
All60 functional/counter/checksum contracts pass. Shuttle36/40cycle rows match
exactly; the four512-operation regions fail by about6–39%. Rocket's old conservative
fixture is200% high on all20rows. The raw failures remain frozen at
`build/scalar-component-validation-e060-v1/report.json`. Read-only same-ELF
frontend diagnosis is underway; no complete causal explanation is claimed yet.

The later91c4 candidate implements actual overlapping Rocket EX/MEM/WB packets
and source CSR interlocks. Its fresh plan has lengths4,5,6,15,16,17,33,65,127,255.
Predictions were frozen BEFORE any reference execution for these exact inputs:
`build/scalar-component-predictions-rocket-fresh-v1/manifest.json`, SHA256
`87158b215b53effd2c9d35b4765dfcd2a57f7c6123e9acdda8f025b72dd0ae76`.
All60regions match exactly against the standalone RTL. This does not remove the
long-stream failure from the earlier experiment or qualify complete workloads.
The fifth candidate's predictions for the already-measured old ten shapes were
frozen before its developer was unblinded; they must not be called frozen before
reference execution.

The plan independently checks exact compiled ADDI counts/chains, initialized
operands, counter encodings and checksums. The collector requires a complete
448-byte coherent mailbox with all three harts done. The source-proved B02
contract expects N retired on Shuttle and N+1 on Rocket; N=0 is legitimate.
The original256-only strict collector and its old failure remain unchanged.

Audit the fresh results with:

```sh
python3 benchmarks/scalar_rtl/verify_components.py \
  --run build/scalar-component-validation-rocket-fresh-v1 \
  --predictions build/scalar-component-predictions-rocket-fresh-v1 \
  --prediction-manifest-sha256 87158b215b53effd2c9d35b4765dfcd2a57f7c6123e9acdda8f025b72dd0ae76
```

`verify_components.py` checks archived inputs rather than requiring old mutable
source paths still match. It recomputes every row from both raw signatures and
the independently decoded ELF. `check_validation.py` tests false certification,
omitted cases, fabricated errors, inverted aggregate claims, wrong prediction
anchors and a wrong raw checksum with repaired enclosing hashes. These six
adversarial checks pass for both epochs. `review_components.py` produces a frozen
Markdown table, audit JSON and source/summary digests in a new output directory.

For a new source-derived candidate, create a genuinely new plan and freeze its
model/source/binary predictions before collecting references. Then use
`validate_components.py --plan <plan> --predictions <directory> --output <new-dir>`.
It runs at most two local RTL instances concurrently and archives all actual
ELF/runtime inputs. Preserve partial output and poll the live process on an
observation timeout. Do not restart or rewrite an earlier receipt. Final
Merlin/Miles holdouts remain separate from all these component experiments.
