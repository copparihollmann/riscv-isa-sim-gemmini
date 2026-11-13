#!/usr/bin/env python3
"""Bind distinct Shuttle/Rocket stage review and its exacte060 prerequisite."""
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda:stream.read(1048576),b''):h.update(data)
    return h.hexdigest()


def main():
    out=ROOT/'build/rocket-pipeline-v3-review';out.mkdir(exist_ok=True,parents=True);(out/'results.json').write_text('{"status":"in_progress"}\n')
    build=ROOT/'build/spike-rocket-pipeline-v3';native=json.loads((build/'pipeline-build.json').read_text());binary,uart=native['binary_sha256'],native['uart_sha256']
    inputs={str(Path(__file__).relative_to(ROOT)):sha(__file__)};gates={}
    names=['csr-directed','regression-final','functional32','live8','memory','uart','forms','nonlinear','edge-cases','scalar-contract','alias-contract','zephyr-scalar','zephyr-mixed','legacy']
    for name in names:
        path=ROOT/f'build/rocket-pipeline-v3-{name}/results.json';d=json.loads(path.read_text())
        if not d['status'].startswith('passed') or d.get('binary_sha256')!=binary or d.get('uart_sha256')!=uart:raise RuntimeError('different/failed candidate gate: '+name)
        inputs[str(path.relative_to(ROOT))]=sha(path);gates[name]=dict(status=d['status'],sha256=sha(path))
    parent=ROOT/'build/counter-pipeline-frozen-e0600503';manifest=json.loads((parent/'manifest.json').read_text());inputs[str((parent/'manifest.json').relative_to(ROOT))]=sha(parent/'manifest.json')
    # Retain the already closed source/phase evidence by content, including old
    # checker versions which have intentionally changed in the current tree.
    for digest in set(manifest['input_sha256'].values()):
        path=parent/'inputs'/digest
        if sha(path)!=digest:raise RuntimeError('893 prerequisite input changed')
        inputs[str(path.relative_to(ROOT))]=digest
    for name in ('iris-with-pipeline.patch','spike','libsifive_uart.so'):
        path=parent/name
        if sha(path)!=manifest['artifact_sha256'][name]:raise RuntimeError('893 prerequisite artifact changed')
        inputs[str(path.relative_to(ROOT))]=sha(path)
    old=ROOT/'pipeline/riscv-isa-sim-counter-pipeline';new=ROOT/'pipeline/riscv-isa-sim-rocket-pipeline';changed=[];patch=''
    for path in sorted((new/'riscv').rglob('*')):
        if not path.is_file():continue
        relative=path.relative_to(new);before=old/relative
        if not before.exists() or before.read_bytes()!=path.read_bytes():
            changed.append(str(relative));patch+=''.join(difflib.unified_diff(before.read_text().splitlines(True) if before.exists() else [],path.read_text().splitlines(True),
                                                                  fromfile='a/'+str(relative) if before.exists() else '/dev/null',tofile='b/'+str(relative)))
    if changed!=['riscv/iris_shuttle_issue.cc','riscv/iris_timing_adapter.cc','riscv/iris_timing_adapter.h','riscv/processor.cc','riscv/processor.h']:raise RuntimeError('counter-overlap source delta scope changed')
    delta=out/'rocket-on-e060.patch'
    if delta.read_text()!=patch:raise RuntimeError('review delta differs from actual frozen sources')
    subprocess.run(['git','-C',str(old),'apply','--check',str(delta)],check=True,capture_output=True)
    inputs[str(delta.relative_to(ROOT))]=sha(delta)
    compiler=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc')
    tools=[compiler]
    for flag in ('-print-prog-name=cc1','-print-prog-name=as','-print-prog-name=ld','-print-libgcc-file-name'):
        tools.append(Path(subprocess.check_output([str(compiler),flag],text=True).strip()).resolve())
    for path in tools:
        if not path.is_file():raise RuntimeError('guest compiler dependency missing')
        inputs[str(path)]=sha(path)
    report=dict(schema='iris.heterogeneous.pipeline.review.v1',status='passed_source_heterogeneous_pipeline_review',binary_sha256=binary,uart_sha256=uart,
                source_sha256=inputs,gates=gates,prerequisite_manifest_sha256=sha(parent/'manifest.json'),delta_files=changed,delta_sha256=sha(delta),
                no_timing_parameters_fitted=True,old_goldens_modified=False,primary_modified=False,component_validation_predictions_started=False,
                calibrated=False,rtl_certified=False,held_out_2pct=False,ethan_image_association_verified=False)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(status=report['status'],gates=len(gates),inputs=len(inputs))))


if __name__=='__main__':main()
