#!/usr/bin/env python3
"""Add readonly internal wire visibility to unchanged saved whole-SoC RTL."""
import argparse
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

R = Path(__file__).resolve().parents[1]
REFERENCE = R/'build/saturn-timing-component-v1-final'

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--schema', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=16)
    parser.add_argument('--protocol-ports', type=Path)
    args = parser.parse_args()
    schema_path = args.schema.resolve()
    schema = json.loads(schema_path.read_text())
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    shutil.copy2(Path(__file__),out/'builder.py')
    base = REFERENCE/'build/saturn-timing-reference-v1'
    receipt = json.loads((base/'build.json').read_text())
    shutil.copytree(base/'rtl', out/'rtl')
    source = {str(p):sha(p)for p in (base/'rtl').iterdir()if p.is_file()}
    for old,digest in source.items():
        assert sha(out/'rtl'/Path(old).name) == digest
    original = str(R/'build/saturn-timing-reference-v1')
    config = (base/'boundary-readonly.vlt').read_text()
    visibility = sorted({(field['module'], field['name'].rsplit('.',1)[-1])
                         for profile in schema['profiles'].values()
                         for field in profile['fields'] if field['requires_whole_visibility']})
    if args.protocol_ports:
        protocols = json.loads(args.protocol_ports.read_text())
        visibility = sorted(set(visibility)|{(f['module'],f['variable'])
            for profile in protocols['profiles'].values()for f in profile['fields']})
    for module,var in visibility:
        config += 'public_flat_rd -module "'+module+'" -var "'+var+'"\n'
    (out/'boundary-readonly.vlt').write_text(config)
    (out/'sim_files.f').write_text((base/'sim_files.f').read_text().replace(original,str(out)))
    command = [arg.replace(original,str(out))for arg in receipt['verilate_argv']]
    (out/'verilate-command.json').write_text(json.dumps(command,indent=2)+'\n')
    started = time.monotonic()
    with (out/'verilate.log').open('w')as log:
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    compile = receipt['compile_argv'][:]
    compile[1] = '-j'+str(args.jobs)
    (out/'compile-command.json').write_text(json.dumps(compile,indent=2)+'\n')
    with (out/'compile.log').open('w')as log:
        subprocess.run(compile,cwd=out/'model',stdout=log,stderr=subprocess.STDOUT,check=True)
    result = {'schema':'iris.saturn_activity_whole_reference_build.v1',
              'verilate_argv':command,'compile_argv':compile,
              'input_sha256':{str(p):sha(p)for p in[Path(__file__),schema_path,base/'build.json',REFERENCE/'report.json']+([args.protocol_ports.resolve()]if args.protocol_ports else[])},
              'source_sha256':source,'public_visibility_sha256':sha(out/'boundary-readonly.vlt'),
              'additional_readonly_wire_visibility':visibility,
              'host_seconds':time.monotonic()-started,
              'model_archive_sha256':sha(out/'model/VTestDriver__ALL.a'),
              'source_RTL_logic_modified':False,'clocks_or_internal_state_driven':False,
              'hardware_contacted':False}
    (out/'build.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'host_seconds':result['host_seconds'],'visibility_fields':len(visibility),
                      'build_sha256':sha(out/'build.json')}))

if __name__ == '__main__':
    main()
