#!/usr/bin/env python3
"""Expand frozen binding source/evidence closure; never change model parameters."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    original=ROOT/'calibration/compute-fit-fadd-shape-7de-binding-v1/runtime-binding.json'
    binding=json.loads(original.read_text());inputs=binding['input_sha256'];before=dict(inputs)
    for name,expected in inputs.items():
        if sha(name)!=expected:raise ValueError('Frozen original input changed: '+name)
    def add(path,expected=None):
        path=Path(path).resolve();actual=sha(path)
        if expected is not None and actual!=expected:raise ValueError('Expanded source/evidence changed: '+str(path))
        if str(path)in inputs and inputs[str(path)]!=actual:raise ValueError('Conflicting expanded source identity')
        inputs[str(path)]=actual
    add(original);add(Path(__file__).resolve())
    raw_path=ROOT/'calibration/compute-fit-fadd-shape-7de-constrained-v1/parameters.json'
    raw=json.loads(raw_path.read_text())
    for path in (ROOT/'timing/empirical_compute_fit_v2.py',raw_path.with_name('fit-source.py')):add(path,raw['source_sha256'])
    for name in ('empirical_compute_select_v2.py','empirical_fadd_shape_sweep_v1.py',
                 'empirical_fadd_shape_finalize_v1.py','empirical_compute_features_v2.py','empirical_live_features_v4.py'):
        add(ROOT/'timing'/name)
    queue=[ROOT/'calibration/compute-fit-fadd-shape-7de-initial-v1/selection.json',
           ROOT/'calibration/compute-fit-fadd-shape-7de-selected-v1/selection.json',
           ROOT/'calibration/compute-fit-fadd-shape-7de-sweep-v1/selection.json']
    queue.extend(ROOT.glob('calibration/compute-fit-fadd-shape-7de-sweep-v1/*/evaluation/report.json'))
    seen=set()
    while queue:
        path=Path(queue.pop()).resolve()
        if path in seen:continue
        seen.add(path);add(path);document=json.loads(path.read_text())
        if not isinstance(document,dict):continue
        for field in ('input_sha256','output_sha256','evidence_sha256','native_inputs_sha256'):
            for name,expected in document.get(field,{}).items():
                target=Path(name);target=target if target.is_absolute()else ROOT/target
                add(target,expected)
                # Traverse only this fresh fit's owned JSON lineage, preserving
                # separately declared historical-prior scope rather than
                # silently reinterpreting unrelated historical documents.
                if target.suffix=='.json'and 'compute-fit-fadd-shape-7de'in str(target):queue.append(target)
    binding['source_provenance_expansion']={'original_binding':str(original),'original_binding_sha256':sha(original),
        'parameters_or_model_changed':False,'actual_counters_or_reference_changed':False,
        'added_input_count':len(inputs)-len(before),'own_fit_lineage_documents_visited':len(seen),
        'interpretation':'Direct verifier materialization of own fitter/selector/sweep code and numeric evidence; existing native/fixture/parameters/report identities unchanged.'}
    out=ROOT/'calibration/compute-fit-fadd-shape-7de-binding-v2';out.mkdir(exist_ok=False)
    (out/'runtime-binding.json').write_text(json.dumps(binding,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'binding':str(out/'runtime-binding.json'),'sha256':sha(out/'runtime-binding.json'),
        'inputs':len(inputs),'added':len(inputs)-len(before),'parameters_changed':False}))


if __name__=='__main__':main()
