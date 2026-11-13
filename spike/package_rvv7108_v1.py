#!/usr/bin/env python3
"""Build a new optional descriptor for the exact, unaccepted fitted7108 epoch."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from spike import empirical_provider_rvv7108_v1 as provider
from spike.empirical_launch_v2 import launcher_text

def write(path,value):
    path.write_text(json.dumps(value,indent=2)+'\n')

def gather(value,inputs):
    if isinstance(value,dict):
        for key,items in value.items():
            if key.endswith('sha256') and isinstance(items,dict):
                for name,want in items.items():
                    if isinstance(name,str) and name.startswith('/') and isinstance(want,str) and len(want)==64:
                        if name in inputs and inputs[name]!=want:raise ValueError('Conflicting evidence input: '+name)
                        inputs[name]=want
            gather(items,inputs)
    elif isinstance(value,list):
        for item in value:gather(item,inputs)

def build(output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    inputs={}
    def add(path,expected=None):
        path=Path(path).resolve();want=expected or provider.sha(path)
        if provider.sha(path)!=want:raise ValueError('Changed frozen input: '+str(path))
        if str(path)in inputs and inputs[str(path)]!=want:raise ValueError('Conflicting input identity')
        inputs[str(path)]=want
    for relative,want in list(provider.CORE.values())+list(provider.EVIDENCE.values()):
        path=ROOT/relative;add(path,want)
        if path.suffix=='.json':gather(provider.document(path),inputs)
    capsule=ROOT/'build/warm-OPU-frozen-7108a6ec-v1'
    manifest=provider.document(capsule/'manifest.json')
    for name,want in manifest['artifact_sha256'].items():add(capsule/name,want)
    inventory=provider.document(capsule/'native-inventory.json')
    seen={}
    with tarfile.open(capsule/'native-source.tar.gz','r:gz')as archive:
        for member in archive:
            allowed_link=(member.issym() and member.name=='spike_dasm/spike_dasm_option_parser.cc'
                          and member.linkname=='../fesvr/option_parser.cc')
            if not(member.isfile() or allowed_link) or member.name not in inventory or member.name in seen:
                raise ValueError('Unexpected/duplicate/nonregular source member: '+member.name)
            if Path(member.name).is_absolute() or '..' in Path(member.name).parts:raise ValueError('Unsafe source member')
            seen[member.name]=hashlib.sha256(archive.extractfile(member).read()).hexdigest()
    if seen!=inventory or len(seen)!=2138:raise ValueError('Native source inventory mismatch')
    # Both the archived native source and every external compile-time input are
    # byte checked; no source/image association is inferred from reconstruction.
    for name,want in provider.document(capsule/'compiled-inputs.json').items():add(name,want)
    build_report=provider.document(capsule/'pipeline-build.json');gather(build_report,inputs)
    for name,want in inputs.items():
        if provider.sha(name)!=want:raise ValueError('Changed evidence/source input: '+name)
    closure=output/'source-closure.json'
    write(closure,dict(schema='iris.rvv7108_source_snapshot_verification.v1',**{'pass':True},
        native_sources=len(seen),source_symlinks={'spike_dasm/spike_dasm_option_parser.cc':'../fesvr/option_parser.cc'},
        external_compiled_inputs=manifest['external_compiled_inputs'],
        manifest_sha256=provider.EVIDENCE['capsule'][1],
        native_binary_sha256=provider.CORE['native_binary'][1],uart_library_sha256=provider.CORE['uart_library'][1],
        build_configuration='Exact frozen pipeline-build.json commands and all declared link/header inputs; no rebuild performed.',
        complete_source_image_attestation=False,
        input_sha256={k:v for k,v in inputs.items()if k.startswith(str(capsule))or k in build_report.get('input_sha256',{})}))
    add(closure);add(Path(provider.__file__));add(Path(__file__));add(ROOT/'iris_model/empirical_run.py')
    fatal=provider.document(ROOT/provider.EVIDENCE['fatal'][0])
    python=Path(next(p for p in fatal['input_sha256']if p.startswith('/usr/bin/python')))
    native=ROOT/provider.CORE['native_binary'][0]
    launcher=ROOT/provider.CORE['binary'][0]
    if launcher.read_text()!=launcher_text(native,provider.CORE['native_binary'][1],python,provider.sha(python)):
        raise ValueError('Verified launcher differs from isolated fatal-aware template')
    add(ROOT/'spike/empirical_launch_v2.py');add(python)
    model=dict(schema='iris.empirical_simulator.v1',package_kind=provider.MODEL_KIND,
        mode='experimental_finite_calibration',calibration_identity=provider.MODEL_KIND,
        **{k:str(ROOT/v[0])for k,v in provider.CORE.items()},
        binary_sha256=provider.CORE['binary'][1],native_binary_sha256=provider.CORE['native_binary'][1],
        uart_library_sha256=provider.CORE['uart_library'][1],native_device_abi=4,
        model_provider=str(Path(provider.__file__).resolve()),per_hart_isa=provider.ISA,
        matrix_hart_ids=[0,1],memory_regions=provider.MEMORY,launch_args=provider.launch_args(),
        runtime_environment={k:None for k in ('LD_PRELOAD','LD_AUDIT','LD_LIBRARY_PATH')},
        evidence={k:str(ROOT/v[0])for k,v in provider.EVIDENCE.items()},
        source_closure=str(closure),qualification=provider.QUALIFICATION,
        input_sha256=inputs,optional_only=True,current_pointer_changed=False,
        limits=[
            'Experimental finite978-TRAIN calibration, not accepted timing qualification or +/-2%.',
            'TRAIN total median absolute error18.066%,p9025.119%;911/978 targets below ownzero model floor.',
            'Whole-VRF ownership, conservative vector-memory and partial-group chaining limits remain.',
            'Hart2 retains functional control; no hart2 timing accuracy claim.',
            'SourceOPU overlap mode OFF; no full source/loaded-image or physical traffic/bandwidth certification.',
            '1320 calibration replay used an intentional postmeasurement debugger stop; separate compiler/OS/smoke gates have normal guest exits.',
            'Existing parameter/mapping receipts remain immutable and retain their original UNACCEPTED fields.',
            'Absolute local input paths are intentional; this descriptor is usable in this workspace, not a self-contained portable distribution.'])
    target=output/'manifest.json';write(target,model)
    result=provider.experimental_empirical_simulator(target)
    write(output/'verification.json',dict(schema='iris.optional_rvv7108_package_verification.v1',
        **{'pass':result['available']},manifest_sha256=provider.sha(target),
        checked_inputs=len(inputs),native_sources=len(seen),provider_result=result))
    if not result['available']:raise ValueError(result['reason'])
    (output/'README.txt').write_text('Optional fitted7108 experimental model. Current default is unchanged.\n\n'
        'python3 -m iris_model.empirical_run --model '+str(target)+' --elf YOUR_UNSTRIPPED_RV64_ELF --output NEW_DIRECTORY --timeout600\n\n'
        'Verify: python3 spike/empirical_provider_rvv7108_v1.py --model '+str(target)+'\n\n'
        +'\n'.join(model['limits'])+'\n')
    return target

if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(build(a.output))
