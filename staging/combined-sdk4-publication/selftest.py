#!/usr/bin/env python3
"""Rebuild actual SDK4 handlers and replay its corrected32 guest corpus."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
import uuid

HERE=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--kind',choices=['all','handlers','guests'],default='all')
    p.add_argument('--native-build',type=Path);p.add_argument('--output',type=Path);p.add_argument('--dtc',type=Path);a=p.parse_args()
    spec=importlib.util.spec_from_file_location('primary_selftest_provider',HERE/'provider.py');provider=importlib.util.module_from_spec(spec);spec.loader.exec_module(provider)
    value=provider.experimental_functional_simulator()
    if value.get('available')is not True:raise ValueError(value.get('reason'))
    release=Path(value['selected_release']);out=(a.output or HERE.parent/'build'/('sdk4-selftest-'+uuid.uuid4().hex)).resolve();out.mkdir(parents=True,exist_ok=False)
    frozen=release/'evidence/combined';capsule=json.loads((frozen/'manifest.json').read_text());lock=json.loads((release/'source-lock.json').read_text())
    original=Path(lock['historical_repository_root']);cache={}
    def data(name):
        entry=capsule['files'][name];key=entry['sha256']
        if key not in cache:
            raw=(frozen/entry['object']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=entry['object_sha256']:raise ValueError('Proof object changed')
            payload=gzip.decompress(raw)if entry['compression']=='gzip'else raw
            if len(payload)!=entry['bytes']or hashlib.sha256(payload).hexdigest()!=key:raise ValueError('Proof payload changed')
            cache[key]=payload
        return cache[key]
    source=release/'source/third_party/riscv-isa-sim-combined';native=Path(a.native_build).resolve()if a.native_build else out/'matched-native-sdk'
    if a.native_build:
        if sha(native/'spike')!=capsule['binary_sha256']or sha(native/'libsifive_uart.so')!=capsule['uart_sha256']:raise ValueError('Build does not match selected native/UART pair')
    else:
        native.mkdir()
        for name in ['libriscv.a','libdisasm.a','libsoftfloat.a','libfesvr.a','libfdt.a','libspike_main.a','config.h']:
            (native/name).write_bytes(data('build/spike-combined/'+name))
    env=dict(os.environ,PATH='/scratch/eygao/iris-cy/.conda-env/bin:'+os.environ['PATH'])
    if a.dtc:env['PATH']=str(a.dtc.resolve().parent)+os.pathsep+env['PATH']
    rows=[]
    if a.kind in['all','handlers']:
        fixture_root=out/'fixture-root';receipt=json.loads(data('build/combined-handlers/results.json'))
        for row in receipt['rows']:
            dep=data('build/combined-handlers/'+row['name']+'.d').decode().replace('\\\n',' ').splitlines()[0]
            for token in shlex.split(dep.split(':',1)[1]):
                path=Path(token)
                if path.is_relative_to(original):
                    name=str(path.relative_to(original))
                    if name.startswith('third_party/'):continue
                    target=fixture_root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data(name))
            def mapped(word):
                for before,after in [(str(original/'build/spike-combined'),str(native)),
                    (str(original/'third_party/riscv-isa-sim-combined'),str(source)),(str(original),str(fixture_root))]:
                    if before in word:return word.replace(before,after)
                return word
            command=[mapped(word)for word in row['compile_argv']];command[-1]=str(out/row['name'])
            if '-MF'in command:command[command.index('-MF')+1]=str(out/(row['name']+'.d'))
            compiled=subprocess.run(command,capture_output=True,env=env)
            (out/(row['name']+'.compile.stdout')).write_bytes(compiled.stdout);(out/(row['name']+'.compile.stderr')).write_bytes(compiled.stderr)
            if compiled.returncode:raise ValueError('SDK4 handler compilation failed: '+row['name'])
            run=subprocess.run([command[-1]],capture_output=True,env=env,timeout=180)
            for name,payload in [('stdout',run.stdout),('stderr',run.stderr)]:(out/(row['name']+'.'+name)).write_bytes(payload)
            passed=run.returncode==0 and run.stdout==data('build/combined-handlers/'+row['name']+'.stdout')
            rows.append({'name':row['name'],'kind':'actual_handler','compile_argv':command,'exit_status':run.returncode,'pass':passed})
    if a.kind in['all','guests']:
        receipt=json.loads(data('build/combined-functional/results.json'))
        reference=HERE/'bin/spike-zvt-reference'
        legacy=json.loads(data('build/snapshot-5e6cc309/provenance.json'))
        if sha(reference)!=legacy['reference_binary_sha256']:raise ValueError('Zvt reference differs from frozen lineage')
        for row in receipt['rows']:
            elf_name=str(Path(row['argv'][-1]).relative_to(original));elf=out/(row['name']+'.elf');elf.write_bytes(data(elf_name))
            command=list(row['argv']);command[0]=str(reference if row['name'].endswith('-reference')else native/'spike'if a.native_build else release/'bin/spike')
            command=[('--extlib='+str(native/'libsifive_uart.so'if a.native_build else release/'bin/libsifive_uart.so'))if word.startswith('--extlib=')else word for word in command]
            command[-1]=str(elf);case_env=dict(env);case_env.update(row.get('environment',{}));before=time.monotonic()
            run=subprocess.run(command,capture_output=True,env=case_env,timeout=180)
            for name,payload in [('stdout',run.stdout),('stderr',run.stderr)]:(out/(row['name']+'.'+name)).write_bytes(payload)
            passed=run.returncode==row['expected_exit_status']and b'IRIS_UNDEFINED_STATE'not in run.stderr
            if row['expected_exit_status']:
                passed &= all(text.encode()in run.stderr for text in row['expected_diagnostics'])
            else:
                old_rows=[json.loads(line.split(b' ',1)[1])for line in data('build/combined-functional/'+row['name']+'.stdout').splitlines()if line.startswith(b'IRIS_REGION ')]
                new_rows=[json.loads(line.split(b' ',1)[1])for line in run.stdout.splitlines()if line.startswith(b'IRIS_REGION ')]
                if old_rows:
                    key=lambda values:{(v['case_id'],v['region'],v['hart']):v['checksum']for v in values}
                    passed &= len(old_rows)==len(new_rows)and all(v.get('pass')is True for v in new_rows)and key(old_rows)==key(new_rows)
                else:passed &= b'PASSED'in run.stdout
            rows.append({'name':row['name'],'kind':'guest','argv':command,'exit_status':run.returncode,'elf_sha256':sha(elf),'pass':bool(passed),'host_seconds':time.monotonic()-before})
    passed=all(row['pass']for row in rows)
    result={'schema':'iris.primary_sdk4.selftest.v1','pass':passed,'binary_sha256':capsule['binary_sha256'],'uart_sha256':capsule['uart_sha256'],
        'native_device_abi':4,'rows':rows,'kind':a.kind,'static_library_sha256':{path.name:sha(path)for path in native.glob('*.a')},
        'input_sha256':{str(Path(__file__)):sha(__file__),str(release/'provenance.json'):sha(release/'provenance.json')},
        'rtl_certified':False,'timing_certified':False,'primary_modified':False}
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'results.json');raise SystemExit(0 if passed else 1)
if __name__=='__main__':main()
