#!/usr/bin/env python3
"""Bind the counter-policy review to closed RTL evidence and native regressions."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda:stream.read(1048576),b''):h.update(data)
    return h.hexdigest()


def main():
    out=ROOT/'build/counter-policy-v2-review';out.mkdir(exist_ok=True,parents=True)
    (out/'results.json').write_text('{"status":"in_progress"}\n')
    build=ROOT/'build/spike-counter-policy-v2';native=json.loads((build/'pipeline-build.json').read_text())
    binary,uart=native['binary_sha256'],native['uart_sha256'];inputs={str(Path(__file__).relative_to(ROOT)):sha(__file__)}
    names=['directed','functional32','live8','memory','uart','forms','nonlinear','edge-cases-final','scalar-contract','alias-contract','zephyr-scalar','zephyr-mixed']
    gates={}
    for name in names:
        path=ROOT/f'build/counter-policy-v2-{name}/results.json';d=json.loads(path.read_text())
        if not d['status'].startswith('passed') or d.get('binary_sha256')!=binary or d.get('uart_sha256')!=uart:
            raise RuntimeError('gate does not match candidate: '+name)
        inputs[str(path.relative_to(ROOT))]=sha(path);gates[name]=dict(status=d['status'],sha256=sha(path))
    unit=ROOT/'build/pipeline-csr-source-proof-v2/results.json';u=json.loads(unit.read_text())
    if u['rows']!=4582 or u['failures']:raise RuntimeError('independent CSR unit proof incomplete')
    inputs[str(unit.relative_to(ROOT))]=sha(unit)
    closed=ROOT/'build/pipeline-csr-proof-closed';capsule=json.loads((closed/'manifest.json').read_text())
    inputs[str((closed/'manifest.json').relative_to(ROOT))]=sha(closed/'manifest.json')
    for path in closed.rglob('*'):
        if path.is_file():inputs[str(path.relative_to(ROOT))]=sha(path)
    phase=ROOT/'build/csr-phase-proof-v2/report.json';p=json.loads(phase.read_text())
    if p['hardware_contacted'] or p['rtl_design_changed'] or p['timing_calibrated'] or p['ethan_image_association_verified']:
        raise RuntimeError('whole-CPU observer scope changed')
    inputs[str(phase.relative_to(ROOT))]=sha(phase)
    for name,digest in p['artifact_sha256'].items():
        path=phase.parent/name
        if sha(path)!=digest:raise RuntimeError('whole-CPU phase proof artifact changed: '+name)
        inputs[str(path.relative_to(ROOT))]=digest
    for name in ('scalar-contract','alias-contract'):
        d=json.loads((ROOT/f'build/counter-policy-v2-{name}/results.json').read_text())
        for row in d['table']:
            expected=256 if name=='scalar-contract' and row['hart']<2 else 257
            if row['model_instret_delta']!=expected or row['reference_instret_delta']!=expected or not row['source_counter_contract_matches']:
                raise RuntimeError('paired whole-CPU counter contract failed')
    # Preserve a genuine behavioral negative control. The old epoch suppresses
    # counting on inhibit-set and counts inhibit-clear, opposite CSRFile edges.
    negative=ROOT/'build/counter-policy-v1-inhibit-negative-control';rows=[json.loads(s.split(' ',1)[1]) for s in (negative/'functional.stdout').read_text().splitlines() if s.startswith('COUNTER_EDGE ')]
    if len(rows)!=3 or any(r['data'][1]-r['data'][0]!=1 or r['data'][2]-r['data'][1]!=1 or r['data'][4:6]!=[12345,12346] for r in rows):
        raise RuntimeError('old-policy negative witness changed')
    legacy=ROOT/'build/spike-counter-policy-v1/pipeline-build.json';old=json.loads(legacy.read_text())
    if sha(legacy.parent/'spike')!=old['binary_sha256']:raise RuntimeError('negative native changed')
    for path in [legacy,legacy.parent/'spike',legacy.parent/'libsifive_uart.so']+list(negative.iterdir()):
        if path.is_file():inputs[str(path.relative_to(ROOT))]=sha(path)
    for name in ('functional.stdout','functional.stderr','edges.elf','edges.S','guest.c','edges.fixture'):
        shutil.copy2(negative/name,out/('negative-'+name))
    report=dict(schema='iris.counter_edge.review.v1',status='passed_source_counter_policy_review',binary_sha256=binary,uart_sha256=uart,
                source_sha256=inputs,gates=gates,independent_CSR_unit_edges=u['rows'],full_cpu_phase_proof_sha256=sha(phase),
                negative_control=dict(binary_sha256=old['binary_sha256'],rejected=True,observed_inhibit_set_delta=1,expected_inhibit_set_delta=2,
                                      observed_inhibit_clear_delta=1,expected_inhibit_clear_delta=0,observed_inhibited_write_then_clear=[12345,12346],expected=[12345,12345]),
                convention='Instruction completion/end is the local retirement edge; guest get_csr samples pre-update state; explicit source counter writes override increments.',
                architectural_retirements_separate=True,old_collectors_and_goldens_modified=False,primary_modified=False,
                calibrated=False,rtl_certified=False,held_out_2pct=False,ethan_image_association_verified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],gates=len(gates),inputs=len(inputs))))


if __name__=='__main__':main()
