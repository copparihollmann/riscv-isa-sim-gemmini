"""New fitting cases; no frozen baseline or held-out source is modified."""
REGIONS = {"tcm0": (0x70000000, 0x20000), "tcm1": (0x70020000, 0x20000),
           "scratchpad": (0x580000000, 0x20000), "dram": (0x84000000, 0x20000)}
NODES = 64
WINDOW = 0x8000


def cases():
    rows = []
    for region, (base, size) in REGIONS.items():
        for pattern, stride, spread in [("bank0", 128, 0), ("hart-banks", 128, 1), ("alternating", 64, 0)]:
            for kind, repetitions in [("chase", (33, 257)), ("read", (1, 16)), ("write", (1, 16))]:
                for n in repetitions:
                    for mask in range(1, 8):
                        pointers = [base + h * WINDOW + (64 * (h & 1) if spread else 0) for h in range(3)]
                        expected = []
                        for h, pointer in enumerate(pointers):
                            if pointer + (NODES - 1) * stride + 8 > base + size:
                                raise ValueError("case crosses its source-mapped region")
                            if kind == "chase":
                                expected.append(pointer + ((13 * n) % NODES) * stride)
                            elif kind == "read":
                                expected.append(n * (NODES * (0x1000 + 256 * h) + NODES * (NODES - 1) // 2))
                            else:
                                expected.append(NODES * (n * 256 + h))
                        active = [h for h in range(3) if mask & (1 << h)]
                        rows.append({"case_id": f"memroute.{region}.{pattern}.{kind}.{n}.mask{mask}",
                                     "kind": kind, "region": "kernel", "target_region": region,
                                     "base": base, "stride": stride, "spread": spread, "n": n, "mask": mask,
                                     "node_count": NODES, "window_bytes_per_hart": WINDOW,
                                     "addresses_by_hart": pointers, "expected_checksums": expected,
                                     "kernel_read_bytes_per_hart": n * 8 if kind == "chase" else n * NODES * 8 if kind == "read" else 0,
                                     "kernel_write_bytes_per_hart": n * NODES * 8 if kind == "write" else 0,
                                     "source_route_ids": [f"hart{h}.scalar_data.{region}" for h in active],
                                     "bank_bit6_sequence_by_hart": [[((p + i * stride) >> 6) & 1 for i in range(NODES)] for p in pointers],
                                     "jobs": [{"hart": h, "role": "dependent_reader" if kind == "chase" else kind,
                                               "address": pointers[h], "expected_checksum": expected[h]} for h in active]})
    return rows
