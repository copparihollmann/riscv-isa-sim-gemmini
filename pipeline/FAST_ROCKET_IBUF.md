# Rocket instruction parcel buffer

`fast_rocket_ibuf.hpp` implements the saved Iris Rocket `IBuf`: a four-byte
fetch packet, one decoded instruction per edge and one retained 16-bit parcel.
It preserves compressed expansion, partial instructions, backpressure, kill,
replay, the exceptions on both parcels and the owning BTB entry/history.

`evaluate(inputs)` computes the physical outputs without advancing state.
`commit()` advances one core edge. A committed reset is required before active
use. Repeated evaluation is allowed; a failed evaluation invalidates commit.
The packet's `known` field describes actual known instruction bits. Unknown
consumed bits refuse. An unused adjacent parcel remains unknown, including the
source `rs3` payload on a compressed instruction. No unreset buffer payload is
initialized by the model.

The implementation uses functional RVC encoding tables generated from the
saved `RVCExpander`, including its separate register-field outputs. These are
instruction decoding tables. They contain no program counters or cycle data.

Rebuild the source differential and SDK with:

```sh
python3 pipeline/check_fast_rocket_ibuf.py --output build/NEW-rocket-ibuf
```

The checker compares 300,000 continuous edges and 6,300,000 physical outputs
against independently compiled saved RTL, checks 262,144 RVC field cases,
exercises reset/knownness/phase guards and rejects three corrupted models.
Its input hashes bind Rocket revision
`fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0` and the exact saved RTL bytes.

This component has no cache service, branch predictor, pipeline timing, IRQ or
architectural execution. A future packet producer must supply real instruction
bytes and independently model their arrival. It does not qualify the Ethan
image or complete Rocket/SoC timing.
