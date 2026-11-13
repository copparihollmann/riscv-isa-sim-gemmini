#!/usr/bin/env python3
"""Visibility-only fast compute variant for exact source read-address telemetry."""
import argparse
import difflib
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

R = Path(__file__).resolve().parents[1]
FAST = R/'build/saturn-timing-fast-component-v1-final'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--schema', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=8)
    parser.add_argument('--profile', choices=['compute','rocket'], default='compute')
    parser.add_argument('--protocol-ports', type=Path)
    parser.add_argument('--suppress-reset-numeric', action='store_true',
                        help='Only omit FP8 numeric evaluation whose source valid stages are synchronously cleared on this reset edge')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(Path(__file__),out/'builder.py')
    schema_path = args.schema.resolve()
    schema = json.loads(schema_path.read_text())
    reference = R/'build/saturn-timing-component-v1-final'
    base = FAST/'build/saturn-timing-fast-v1/native/compute' if args.profile=='compute' else reference/'build/saturn-timing-native-v1/rocket'
    old = json.loads((base/'build.json').read_text())
    shutil.copytree(base/'rtl', out/'rtl')
    shutil.copy2(base/'ports.json', out/'ports.json')
    if args.suppress_reset_numeric:
        if args.profile != 'compute':
            raise ValueError('Only compute has the substituted OPU numeric cone')
        cell=out/'rtl/OuterProductCell.sv'
        original_cell=cell.read_text()
        if original_cell.count('    if (f8macc)\n') != 1:
            raise ValueError('Unexpected frozen numeric-cone source')
        cell.write_text(original_cell.replace('    if (f8macc)\n',
            '    // Reset clears both FMA valid stages on this same edge.\n'
            '    // This numeric-only write cannot become a qualified result.\n'
            '    if (f8macc && !reset)\n'))
        (out/'reset-numeric.patch').write_text(''.join(difflib.unified_diff(
            original_cell.splitlines(True),cell.read_text().splitlines(True),
            fromfile='frozen-fast/OuterProductCell.sv',tofile='reset-qualified/OuterProductCell.sv')))
    fields = schema['profiles'][args.profile]['optimized_missing']
    if any(f['role'] != 'VRF_arbitration' for f in fields):
        raise ValueError('Review unexpected source visibility gap')
    text = '`verilator_config\n'
    visibility={(f['module'], f['name'].rsplit('.',1)[-1])for f in fields}
    if args.protocol_ports:
        protocols=json.loads(args.protocol_ports.read_text())
        visibility|={(f['module'],f['variable'])for f in protocols['profiles'][args.profile]['fields']}
    for module,var in sorted(visibility):
        text += 'public_flat_rd -module "'+module+'" -var "'+var+'"\n'
    config = out/'activity-readonly.vlt'
    config.write_text(text)
    original = str(R/'build/saturn-timing-fast-v1/native/compute') if args.profile=='compute' else str(R/'build/saturn-timing-native-v1/rocket')
    command = [arg.replace(original,str(out))for arg in old['verilate_argv']]
    command.insert(-1,str(config))
    started = time.monotonic()
    with(out/'verilate.log').open('w')as log:
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    compile = old['compile_argv'][:]
    compile[1] = '-j'+str(args.jobs)
    with(out/'compile.log').open('w')as log:
        subprocess.run(compile,cwd=out/'model',stdout=log,stderr=subprocess.STDOUT,check=True)
    result = {'schema':'iris.saturn_activity_fast_visibility_native.v1',
              'verilate_argv':command,'compile_argv':compile,
              'input_sha256':{str(p):sha(p)for p in[Path(__file__),schema_path,base/'build.json',FAST/'report.json',config]+([args.protocol_ports.resolve()]if args.protocol_ports else[])},
              'source_sha256':{str(p):sha(p)for p in(out/'rtl').iterdir()if p.is_file()},
              'added_readonly_source_wires':[f['name']for f in fields],
              'model_archive_sha256':sha(out/'model'/('VSaturnCompute__ALL.a'if args.profile=='compute'else'VSaturnRocket__ALL.a')),
              'host_seconds':time.monotonic()-started,
              'RTL_logic_changed':bool(args.suppress_reset_numeric),
              'visibility_only':not args.suppress_reset_numeric,
              'numeric_only_reset_write_suppressed':bool(args.suppress_reset_numeric),
              'no_MRF_or_pipeline_control_state_initialized':True,
              'hardware_contacted':False}
    for name,digest in result['source_sha256'].items():
        if not(args.suppress_reset_numeric and Path(name).name=='OuterProductCell.sv'):
            assert digest == sha(base/'rtl'/Path(name).name)
    (out/'build.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'host_seconds':result['host_seconds'],'build_sha256':sha(out/'build.json')}))

if __name__ == '__main__':
    main()
