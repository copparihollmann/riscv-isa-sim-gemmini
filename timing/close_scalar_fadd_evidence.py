#!/usr/bin/env python3
"""Close historical guest input versions and source-cited scalar-FADD evidence."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    cas = out / 'objects'
    cas.mkdir()
    resolved = []
    aliases = []
    sources = [ROOT / ('build/' + n + '/src') for n in
               ('scalar-fadd-candidate-d518', 'scalar-fadd-candidate-7e434d8e',
                'scalar-fadd-candidate-next-v1')]

    def archive(logical, digest, kind):
        logical = Path(logical)
        candidates = [logical]
        if logical.is_relative_to(ROOT):
            candidates += [r / logical.relative_to(ROOT) for r in sources]
        actual = next((q for q in candidates if q.is_file() and sha(q) == digest), None)
        if actual is None:
            raise ValueError('No exact historical bytes for ' + str(logical) + ':' + digest)
        dest = cas / digest
        if not dest.exists():
            shutil.copy2(actual, dest)
        if sha(dest) != digest:
            raise ValueError('CAS identity failure')
        row = dict(logical_original_path=str(logical), sha256=digest,
                   verified_actual_source=str(actual), archived_object=str(dest), kind=kind)
        resolved.append(row)
        if actual != logical:
            aliases.append(row)

    directed = ROOT / 'build/scalar-fadd-directed-v3/report.json'
    reports = json.loads(directed.read_text())['cases']
    for case in reports:
        for name, digest in case['input_sha256'].items():
            archive(name, digest, 'actual_directed_runtime_input')
            if Path(name).name == 'build.json':
                build = json.loads(Path(name).read_text())
                for path, expected in build['input_sha256'].items():
                    archive(path, expected, 'actual_guest_build_input')
    citations = []
    for rel, ranges, claim in (
        ('generators/shuttle/src/main/scala/exu/Core.scala',
         [(105, 111), (494, 542), (675, 688), (1148, 1162), (1394, 1411)],
         'FPR is read in EX; no FP bypass; pre-edge scoreboard stalls; physical write sets ready'),
        ('generators/rocket-chip/src/main/scala/tile/FPU.scala',
         [(768, 804), (818, 848), (940, 1008)],
         'ID latches RF addresses; EX reads Mem; l3 physical write; no same-edge read bypass'),
        ('generators/rocket-chip/src/main/scala/rocket/RocketCore.scala',
         [(1025, 1073), (1139, 1150)],
         'FPR RAW/WAW blocks ID through EX/MEM/WB; physical write can coincide with next ID'),
    ):
        source = Path('/scratch/eygao/iris-cy') / rel
        content = source.read_text().splitlines()
        archive(source, sha(source), 'pinned_source_citation')
        citations.append(dict(path=str(source), sha256=sha(source), line_ranges=ranges,
                              claim=claim, excerpts=[dict(first=lo, text='\n'.join(content[lo - 1:hi]))
                                                     for lo, hi in ranges]))
    inputs = {str(Path(__file__)): sha(Path(__file__))}
    for name in (
        'build/scalar-fadd-directed-v3/report.json',
        'build/scalar-fadd-functional32-v1/results.json',
        'build/scalar-fadd-five-OS-v1/report.json',
        'build/scalar-fadd-five-OS-positive-v1/report.json',
        'build/scalar-fadd-positive-QA-fixture-v1/receipt.json',
        'build/scalar-fadd-whole-RTL-proof-v2/report.json',
        'build/scalar-fadd-whole-RTL-run-v2/run.json',
        'build/scalar-fadd-whole-RTL-run-v2/stderr',
        'build/scalar-fadd-whole-RTL-v3/build.json',
        'build/scalar-fadd-RTL-control-v2/build.json',
        'build/scalar-fadd-RTL-control-v2/stdout',
        'build/scalar-fadd-IRQ-parent-control-v1/run/report.json',
        'build/scalar-fadd-companion-on-523-v1/report.json',
        'build/scalar-fadd-companion-on-523-v1/scalar-fadd-on-523.patch',
        'build/scalar-fadd-candidate-next-v1/manifest.json',
        'build/scalar-fadd-candidate-next-v1/verification.json',
    ):
        q = ROOT / name
        inputs[str(q)] = sha(q)
    for q in cas.iterdir():
        inputs[str(q)] = sha(q)
    r = dict(schema='iris.scalar_fadd_phase_and_guest_byte_closure.v1',
             status='qualified_finite_scalar_FADD_phase_experimental_native',
             input_sha256=inputs, historical_guest_inputs=resolved,
             historical_source_path_aliases=aliases, source_citations=citations,
             source_revisions=dict(chipyard='b4542facf6cc9457f6e358e8f80a8b3a0ff5df19',
                                   shuttle='a536ed1df91a0f65770e36758291d02a8cb929c4',
                                   rocket_chip='fc745a8c377fdbf1d278eea81da9ac47b4b5fbc0',
                                   saturn='536774bd4c5e3bcd7813a4a0dc72fc87e5818532',
                                   spike='72958551566a30f19444bd7e354552824e4d0a98'),
             phase_conclusion='Actual saved whole-CPU H/S/D EX->FPR write is4 Shuttle/3 Rocket edges; earliest next dependent EX is write+1 on all3 harts. Shuttle reads FPR in EX, not RRD.',
             numeric_scope='9 directed modes plus actual saved-RTL nine32-add mathematical outputs; other scalar FP uses generic drain',
             IRQ_scope='arrival while pending plus exact final numerical state tested; exact hardware interrupt delivery phase unqualified',
             calibration_scope='opt-in new scalar.fadd.fp16/32/64 feature families; old coefficients never relabeled; v18 reused for OS mechanics QA only',
             source_image_association_verified=False, hardware_contacted=False,
             global_heldout_timings_consumed=False, timing_certified=False,
             ready_for_parent_independent_QA=True)
    (out / 'report.json').write_text(json.dumps(r, indent=2) + '\n')
    print(json.dumps(dict(status=r['status'], archived_versions=len(resolved),
                          historical_aliases=len(aliases), report_sha256=sha(out / 'report.json'))))


if __name__ == '__main__':
    main()
