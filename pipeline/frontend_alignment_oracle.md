The offline oracle reproduces a source branch-prediction mechanism behind the scalar alignment discrepancy. It does not calibrate a timing parameter or certify the FPGA image.

Run `python3 pipeline/frontend_alignment_oracle_check.py --output NEW`. The checker links the already compiled saved ShuttleFrontend objects. It sends the literal `050d / 2785 / fef59ee3` loop through the physical instruction-refill interface, source RRD selection and source MEM branch-update equations. A 1,024-edge initial wait permits the actual 512-entry BHT reset sweep to complete. Every accepted branch resolves two core edges after RRD. The finite stimulus holds unexpected wrong-path parcels by legal consumer backpressure, so this is a frontend component experiment, not a complete CPU execution test.

`build/frontend-alignment-source-proof-v1/report.json` contains 38 cases: the two actual loop addresses with three unreset-state seeds, plus 32 halfword placements. The read-only observer and unobserved wrapper return byte-identical public-output transcripts in every case. All duplicate-entry observations independently assert the actual pre/post rule `isValid_after == isValid_before & ~idxHit`.

With seed 1 and 256 iterations, the loop at 0x80000468 has 132 MEM mispredicts and 64 duplicate-entry clears; its steady cadence is four cycles per iteration. At 0x80000712 there are 10 initial mispredicts, zero duplicate clears and a two-cycle steady cadence. The BHT has already saturated to taken when the first loop repeatedly loses its BTB entries. The latter loop's 32-bit BNE crosses an 8-byte fetch boundary; the former stays inside one word. This finding rules out a blanket penalty for crossing fetch words.

Source identities are pinned by the checker and the saved frontend component's archived input manifest. The relevant original code is Shuttle `a536ed1df91a0f65770e36758291d02a8cb929c4`:

- `ifu/FetchBuffer.scala:18–31, 43–55, 88–113`: seven-slot packed FIFO; per-uop prediction metadata; enqueue/dequeue and clear priority.
- `ifu/BTB.scala:52–62, 80–109, 125–136`: registered updates; prediction-entry/replacement selection; insertion and duplicate-index invalidation.
- `ifu/Frontend.scala:171–200, 245–325, 328–394`: F1 prediction, half-instruction reconstruction, source replay/redirect and fetch-buffer admission.
- `exu/Core.scala:690–743`: MEM target/prediction comparison, fetch-PC correction for a 32-bit instruction across the edge, and BTB/BHT updates.

Rocket `fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0`, `rocket/BTB.scala:75–123`, supplies the actual BHT hash, nonstandard two-bit state encoding, speculative history and reset sweep. Generated `ShuttleBTB.sv:931–937` preserves flush-over-duplicate-over-insert priority. None of these internal values is fed into the model as an input.

The early `build/frontend-alignment-source-oracle-v1/*-v2.*` diagnostic started the loop after only 32 edges, while the BHT reset sweep was active. Those files remain preserved but are not the final proof. Earlier cycle-0 redirect diagnostics also remain as failed harness setup evidence. Final comparisons use the independently rerun `frontend-alignment-source-proof-v1` corpus.
