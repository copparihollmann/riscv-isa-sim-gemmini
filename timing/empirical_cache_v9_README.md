Optional Shuttle Dcache replacement policy, epoch V9

The flag is `empirical_dcache_random shuttle-miss-allocation-proxy-v1`.
It is default OFF. Runtime costs are unchanged; enabling it creates a new
history/timing epoch that requires its own numeric tests and timing evaluation.

Harts0/1 have64sets,2ways and64-byte lines. On a new private data-tag allocation,
V9 selects the source global16-bit LFSR lowbit, without preferring an invalid
way, then advances the exact feedback expression bits10 XOR12 XOR13 XOR15.
Each hart has independent reset-known state1. Hits do not advance. Icache,
vector bypass and TCM/MMIO do not advance. A tag-only reset/flush keeps PRNG
state; source hardware reset, represented by construction, resets it.

The exact associated generated SV and standalone PRNG oracle are bound in
build/cache-replacement-source-gap-closure-v1/report.json. Actual Shuttle RTL
captures a victim in S1 and advances at MSHR request acceptance. This helper
combines those phases in one accepted new-allocation proxy. Permission-only
misses, secondary merges and cycle ordering are not certified by this policy.
Rocket's4-way source selector also uses the LFSR but advances on the final
cached Grant; Rocket remains on the explicitly approximate legacy LRU policy.
L2 and approximate instruction-tag policies remain unchanged too.

V8 response-ready tag generations are preserved. An older accepted response
cannot validate a replacement generation. Writers invalidate peer copies;
failed matching responses invalidate their tag; all accepted actor ownership,
functional values and definedness remain in existing native callbacks.

The conditional source example proves that64 separated stride128 fills can
leave45 nodes resident while V8 LRU leaves64. It does not reproduce the actual
FPGA replacement history or prove the cause of every memory timing outlier.
This remains an experimental policy, with no full-source/image/2% claim.
