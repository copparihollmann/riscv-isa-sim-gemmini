#!/usr/bin/env python3
"""Bind a relocated verified SDK4 package to a fresh outside-package manifest."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--package',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    package=a.package.resolve();out=a.output.resolve()
    if out==package or package in out.parents:raise ValueError('Deployment evidence must be outside the frozen package')
    spec=importlib.util.spec_from_file_location('selected_sdk4_provider',package/'provider.py');provider=importlib.util.module_from_spec(spec);spec.loader.exec_module(provider)
    verified=provider.experimental_functional_simulator()
    if verified.get('available')is not True:raise ValueError(verified.get('reason'))
    out.mkdir(parents=True,exist_ok=False);prov=verified['provenance'];elf=package/'selftest/smoke.elf'
    argv=[verified['binary'],'--isa='+verified['per_hart_isa']['2'],'-p3',
        '-m'+','.join(hex(base)+':'+hex(size)for base,size in verified['memory_regions']),
        *['--hart-isa='+str(h)+':'+verified['per_hart_isa'][str(h)]for h in range(3)],*verified['launch_args'],str(elf)]
    start=time.monotonic();got=subprocess.run(argv,capture_output=True,timeout=60)
    (out/'selftest.stdout').write_bytes(got.stdout);(out/'selftest.stderr').write_bytes(got.stderr)
    rows=[json.loads(line.split(b' ',1)[1])for line in got.stdout.splitlines()if line.startswith(b'IRIS_REGION ')]
    passed=got.returncode==0 and len(rows)==12 and{row['hart']for row in rows}=={0,1,2}and all(row.get('pass')is True for row in rows)
    test={'pass':passed,'binary_sha256':verified['binary_sha256'],'native_binary_sha256':verified['native_binary_sha256'],
        'region_count':len(rows),'regions':rows,'scope':'three-hart-int8-smoke','argv':argv,'returncode':got.returncode,
        'host_seconds':time.monotonic()-start}
    (out/'selftest.json').write_text(json.dumps(test,indent=2)+'\n')
    if not passed:raise ValueError('Fresh package smoke failed; deployment manifest withheld')
    inputs=[Path(__file__).resolve(),package/'provider.py',package/'provenance.json',package/'launch.py',package/'bin/spike',
        package/'bin/libsifive_uart.so',package/'board/bootrom.rv64.img',package/'board/iris.dtb',elf,
        out/'selftest.json',out/'selftest.stdout',out/'selftest.stderr']
    manifest={'schema':'iris.experimental_simulator.v1','binary':verified['binary'],'binary_sha256':verified['binary_sha256'],
        'native_binary_sha256':verified['native_binary_sha256'],'model_provider':str(package/'provider.py'),
        'source_identity':{'spike_base':prov['upstream_spike_sha'],'patch_sha256':prov['target_patch_sha256'],
            'hardware_manifest_sha256':prov['hardware_manifest_sha256']},'isa_extensions':['zvt32t','zvti8i32mm'],
        'per_hart_isa':verified['per_hart_isa'],'launch_args':verified['launch_args'],'memory_regions':verified['memory_regions'],
        'selftest':{'pass':True,'binary_sha256':verified['binary_sha256'],'scope':test['scope'],'receipt':str(out/'selftest.json')},
        'input_sha256':{str(path):sha(path)for path in inputs},'rtl_certified':False,'timing_calibrated':False,'zephyr_smp_certified':False}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(out/'manifest.json')
if __name__=='__main__':main()
