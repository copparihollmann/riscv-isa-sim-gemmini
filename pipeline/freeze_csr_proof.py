#!/usr/bin/env python3
"""Retain the source/unit proof and corroborating failed whole-CPU observation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--input',type=Path,default=ROOT/'build/pipeline-csr-source-proof-v2')
    parser.add_argument('--output',type=Path,default=ROOT/'build/pipeline-csr-proof-closed')
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args();source=args.input.resolve();out=args.output.resolve();manifest=out/'manifest.json'
    if args.verify:
        value=json.loads(manifest.read_text())
        for name,digest in value['artifact_sha256'].items():
            if sha(out/name)!=digest:raise RuntimeError('CSR proof artifact changed: '+name)
        for name,digest in value['input_sha256'].items():
            if sha(out/'inputs'/digest)!=digest:raise RuntimeError('CSR proof source changed: '+name)
        print(json.dumps(dict(status='verified_csr_component_proof_capsule',inputs=len(value['input_sha256']),artifacts=len(value['artifact_sha256']))))
        return
    if manifest.exists():raise RuntimeError('closed proof exists; choose a new output or verify it')
    receipt=json.loads((source/'results.json').read_text())
    if receipt['status']!='passed_component_csr_edge_proof' or receipt['failures']:raise RuntimeError('CSR proof did not pass')
    out.mkdir(exist_ok=True,parents=True);(out/'inputs').mkdir(exist_ok=True);inputs={}
    def retain(path,expected=None):
        path=Path(path).resolve();digest=sha(path)
        if expected is not None and digest!=expected:raise RuntimeError('CSR source mismatch: '+str(path))
        target=out/'inputs'/digest
        if not target.exists():shutil.copy2(path,target)
        inputs[str(path)]=digest
    for name,digest in receipt['source_sha256'].items():retain(ROOT/name,digest)
    for row in receipt['source_evidence']:
        retain(source/row['snapshot'],row['sha256'])
    for dep in (source/'obj').glob('*.d'):
        for word in dep.read_text().replace('\\\n',' ').split()[1:]:
            if word.endswith(':'):continue
            path=(dep.parent/word).resolve()
            if path.is_file():retain(path)
    for name in ('pipeline/CSR_READS.md','pipeline/freeze_csr_proof.py'):retain(ROOT/name)
    for path in source.iterdir():
        if path.is_file():shutil.copy2(path,out/path.name)
    shutil.copytree(source/'source',out/'source')
    shutil.copy2(source/'obj/VCsrPair',out/'csr-unit')
    observation=ROOT/'build/scalar-rtl-observation-v1/report.json';o=json.loads(observation.read_text())
    if o['strict_counter_check_passed'] or o['qualified_accuracy'] or o['source_fir_sha256']!=receipt['source_fir_sha256']:
        raise RuntimeError('corroborating observation identity/qualification changed')
    dest=out/'whole-cpu-observation';dest.mkdir(exist_ok=True)
    shutil.copy2(observation,dest/'report.json')
    signature=ROOT/'build/scalar-rtl-reference-v1/signature';shutil.copy2(signature,dest/'signature')
    elf=ROOT/'build/scalar-rtl-probe-v1/scalar.elf'
    if sha(elf)!=o['same_elf_sha256']:raise RuntimeError('same-ELF reference changed')
    shutil.copy2(elf,dest/'scalar.elf')
    artifacts={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and not p.is_relative_to(out/'inputs')}
    value=dict(schema='iris.shuttle.csr_component_capsule.v1',status='closed_component_proof_with_preserved_cpu_discrepancy',
               input_sha256=inputs,artifact_sha256=artifacts,component_rows=receipt['rows'],
               same_macro_component_deltas=receipt['same_macro_component_deltas'],
               source_fir_sha256=receipt['source_fir_sha256'],full_cpu_strict_counter_check_passed=False,
               native_model_changed=False,whole_cpu_read_phase_validated=False,ethan_image_association_verified=False,
               timing_calibrated=False,held_out_2pct=False)
    manifest.write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(dict(status=value['status'],inputs=len(inputs),artifacts=len(artifacts),output=str(out))))


if __name__=='__main__':main()
