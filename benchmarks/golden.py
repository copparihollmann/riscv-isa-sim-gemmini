"""Host reference checksums for the frozen baseline, independent of guest output."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def checksum(case, hart):
    kernel, n = case["kernel"], case["argument"]
    if kernel == "empty": return hart
    if kernel == "dependent": return 3*n + hart + 1
    if kernel == "branches": return (n//2)*3 + (n-n//2) + hart
    if kernel == "stream":
        words = n//4
        return 4 * (words*(words-1)//2 + words*hart)
    if kernel == "pointer_chase": return (4096*16) % (n//4)
    if kernel in ("local_tcm", "scratchpad"):
        words = n//4
        return words*(words+1)//2
    if kernel in ("atomics", "lrsc", "sync_barrier", "ipi", "timer"): return n
    if kernel.startswith("vec_e"):
        sew, lmul = map(int, kernel.removeprefix("vec_e").split("_m"))
        # All three audited harts have VLEN256; this is independent of DLEN.
        return (256//sew)*lmul*((3+n) % (1 << sew))
    if kernel == "vme_mm": return n*4*32
    if kernel == "refuse_vme": return 1
    raise ValueError("missing independent baseline golden for " + kernel)


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(corpus):
    if corpus.get("batch_source_sha256") != digest(HERE/"batch.c"):
        raise ValueError("frozen baseline source changed; revise and freeze its corpus explicitly")
    if corpus.get("golden_source_sha256") != digest(Path(__file__)):
        raise ValueError("frozen host golden source changed")
    if corpus.get("hardware_manifest_sha256") != digest(HERE.parent/"hardware/manifest.json"):
        raise ValueError("baseline hardware identity changed")
    for case in corpus["cases"]:
        if case.get("expected_checksums_by_hart") != [checksum(case,h) for h in range(3)]:
            raise ValueError("baseline host golden differs from frozen case " + case["case_id"])


def main():
    import argparse
    p=argparse.ArgumentParser(__doc__)
    p.add_argument("--freeze", action="store_true", help="explicitly revise fitting corpus for reviewed source changes")
    args=p.parse_args(); path=HERE/"calibration-corpus.json"
    corpus=json.loads(path.read_text())
    if args.freeze:
        previous=corpus["batch_source_sha256"]
        corpus.update(batch_source_sha256=digest(HERE/"batch.c"), golden_source_sha256=digest(Path(__file__)))
        for case in corpus["cases"]:
            case["expected_checksums_by_hart"]=[checksum(case,h) for h in range(3)]
        if previous != corpus["batch_source_sha256"]:
            corpus["split_id"]="iris-v1-fit-timer-init-2026-11-05"
            corpus["source_revision"]={"previous_batch_sha256":previous,
                "reason":"Initialize undefined-reset mtimecmp before enabling MTIE; no held-out source or timing changed."}
        path.write_text(json.dumps(corpus,indent=2)+"\n")
    verify(corpus)
    print(json.dumps({"status":"verified_frozen_baseline", "cases":len(corpus["cases"]), "split_id":corpus["split_id"]}))


if __name__=="__main__": main()
