#!/usr/bin/env python3
"""Freeze/verify the isolated pipeline's bytes without trusting mutable sources."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ['build/pipeline-directed-full-alu/results.json',
           'build/pipeline-memory-regression-final/results.json',
           'build/pipeline-zephyr-scalar-mask7/results.json',
           'build/pipeline-zephyr-mixed-mask7/results.json']


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--snapshot',type=Path,default=ROOT/'build/pipeline-frozen-b14e192f')
    parser.add_argument('--verify',action='store_true')
    args = parser.parse_args()
    out = args.snapshot.resolve()
    if args.verify:
        manifest = json.loads((out/'closed-manifest.json').read_text())
        for name,sha in manifest['artifact_sha256'].items():
            if digest((out/name).read_bytes())!=sha:
                raise RuntimeError('snapshot artifact mismatch: '+name)
        for name,sha in manifest['input_sha256'].items():
            if digest((out/'inputs'/sha).read_bytes())!=sha:
                raise RuntimeError('snapshot source mismatch: '+name)
        print(json.dumps(dict(status='verified_closed_pipeline_snapshot',inputs=len(manifest['input_sha256']),
                              artifacts=len(manifest['artifact_sha256']),calibrated=False)))
        return
    out.mkdir(exist_ok=True,parents=True)
    (out/'inputs').mkdir(exist_ok=True)
    inputs = {}
    archive_path = ROOT/'build/snapshot-db964603/source-and-evidence.tar.gz'
    prior = json.loads((out/'manifest.json').read_text())
    inputs.update(prior.get('native_dependency_sha256',{}))
    with tarfile.open(archive_path) as archive:
        members = {m.name:m for m in archive if m.isfile()}

        def retain(name,expected,extra=()):
            target=out/'inputs'/expected
            if target.exists() and digest(target.read_bytes())==expected:
                inputs[name]=expected
                return
            for path in [ROOT/name]+list(extra):
                if path.is_file() and digest(path.read_bytes())==expected:
                    target.write_bytes(path.read_bytes());inputs[name]=expected
                    return
            if name in members:
                raw=archive.extractfile(members[name]).read()
                if digest(raw)==expected:
                    target.write_bytes(raw);inputs[name]=expected
                    return
            raise RuntimeError('cannot freeze exact historical source: '+name)

        for report_name in REPORTS:
            report=ROOT/report_name
            value=json.loads(report.read_text())
            if not value['status'].startswith('passed') or value['binary_sha256']!=digest((out/'spike').read_bytes()):
                raise RuntimeError('report failed or from a different model: '+report_name)
            for name,sha in value.get('source_sha256',{}).items():
                retain(name,sha)
            destination=out/'reports'/report.parent.name
            destination.mkdir(exist_ok=True,parents=True)
            for path in report.parent.iterdir():
                if path.is_file():
                    shutil.copyfile(path,destination/path.name)
            if 'build_receipt_sha256' in value:
                build=Path(value['argv'][-1]).parents[1]
                receipt=build/'build.json'
                if digest(receipt.read_bytes())!=value['build_receipt_sha256']:
                    raise RuntimeError('Zephyr build receipt mismatch')
                shutil.copyfile(receipt,destination/'build.json')
                build_data=json.loads(receipt.read_text())
                for name,sha in build_data['input_sha256'].items():
                    retain(name,sha,[build/'input-snapshot'/name])
                for name,sha in build_data['artifact_sha256'].items():
                    path=build/name
                    if digest(path.read_bytes())!=sha:
                        raise RuntimeError('Zephyr artifact changed: '+str(path))
                    shutil.copyfile(path,destination/path.name)
        for name in ('pipeline/README.md','pipeline/freeze.py','timing/PIPELINED_SHUTTLE.md'):
            retain(name,digest((ROOT/name).read_bytes()))
        for name in ('board/addressing.hpp','board/physical_map.hpp','board/iris_boot.hpp','board/iris_clint.hpp','board/iris_plic.hpp',
                     'spike/devices/src/sifive_uart.cc'):
            raw=archive.extractfile(members[name]).read()
            retain(name,digest(raw))
    # These exact libraries were linked into the processor guard executable.
    libdir=ROOT/'build/spike-shuttle-pipeline'
    libout=out/'native-libraries';libout.mkdir(exist_ok=True)
    for name in ('libriscv.a','libdisasm.a','libsoftfloat.a','libfesvr.a','libfdt.a','config.h','config.log'):
        shutil.copyfile(libdir/name,libout/name)
    artifacts={str(p.relative_to(out)):digest(p.read_bytes()) for p in out.rglob('*')
               if p.is_file() and not p.is_relative_to(out/'inputs') and p.name!='closed-manifest.json'}
    manifest=dict(schema='iris.shuttle.closed_snapshot.v1',calibrated=False,rtl_certified=False,held_out_2pct=False,
                  binary_sha256=digest((out/'spike').read_bytes()),uart_sha256=digest((out/'libsifive_uart.so').read_bytes()),
                  prerequisite=prior['prerequisite'],full_overlay_sha256=prior['full_overlay_sha256'],
                  extension_overlay_sha256=prior['extension_overlay_sha256'],
                  parent_archive_sha256=digest(archive_path.read_bytes()),source_base_git_sha='72958551566a30f19444bd7e354552824e4d0a98',
                  input_sha256=inputs,artifact_sha256=artifacts,reports=REPORTS)
    (out/'closed-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(status='closed_pipeline_snapshot',inputs=len(inputs),artifacts=len(artifacts),calibrated=False)))


if __name__=='__main__':
    main()
