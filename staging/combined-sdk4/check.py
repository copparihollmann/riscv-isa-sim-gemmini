#!/usr/bin/env python3
"""Exercise packaged SDK4 admission, typed refusals and the real Merlin hook."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def cases(suite):
    for value in suite:
        if isinstance(value,unittest.TestSuite):yield from cases(value)
        else:yield value.id()
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--package',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    package=a.package.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    os.environ['IRIS_SDK4_PACKAGE']=str(package)
    suite=unittest.defaultTestLoader.discover(str(HERE/'tests'));ids=list(cases(suite))
    with (out/'tests.log').open('w')as stream:result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    module=sys.modules['test_provider'];sdk=[]
    for row in getattr(module.ProviderTests,'sdk_rows',[]):
        record=dict(row)
        for key in ['stdout','stderr']:
            path=out/(row['name']+'.'+key);path.write_bytes(record.pop('raw_'+key));record[key+'_sha256']=sha(path)
        sdk.append(record)
    fatal=[]
    for row in getattr(module.FatalLauncherTests,'rows',[]):
        record=dict(row)
        elf=out/('fatal-h'+str(row['hart'])+'.elf');elf.write_bytes(record.pop('raw_elf'));record['elf_sha256']=sha(elf)
        for key in ['stdout','stderr']:
            path=out/('fatal-h'+str(row['hart'])+'.'+key);path.write_bytes(record.pop('raw_'+key));record[key+'_sha256']=sha(path)
        fatal.append(record)
    (out/'fatal.S').write_bytes(module.FatalLauncherTests.fixture_source)
    (out/'fatal.ld').write_bytes(module.FatalLauncherTests.fixture_linker)
    raw=getattr(module.MerlinContractTests,'merlin_result',None);merlin=None
    if raw:
        for key in ['stdout','stderr']:(out/('merlin.'+key)).write_bytes(raw[key])
        merlin={key:raw[key]for key in ['argv','returncode','elf_sha256']}
        merlin.update(stdout_sha256=sha(out/'merlin.stdout'),stderr_sha256=sha(out/'merlin.stderr'),
            region_count=sum(line.startswith(b'IRIS_REGION ')for line in raw['stdout'].splitlines()),
            binary_sha256=raw['simulator']['binary_sha256'],timing_available=raw['simulator']['timing_available'])
    paths=[Path(__file__),HERE/'tests/test_provider.py',HERE/'build.py',HERE/'provider.py',HERE/'package.py',HERE/'README.md',
        package/'provenance.json',package/'merlin-manifest.json',package/'provider.py',package/'build.py',package/'launch.py',
        ROOT/'integration/iris-mlir/simulator.py',ROOT/'integration/merlin/src/merlin/runtime/backends/device_simulator.py']
    paths.append(module.FatalLauncherTests.compiler)
    report={'schema':'iris.combined_sdk4.package_acceptance.v1','pass':result.wasSuccessful()and len(sdk)==4 and len(fatal)==3 and merlin is not None,
        'package':str(package),'binary_sha256':sha(package/'bin/spike'),'uart_sha256':sha(package/'bin/libsifive_uart.so'),
        'package_provenance_sha256':sha(package/'provenance.json'),'native_device_abi':4,
        'tests':{'run':result.testsRun,'cases':ids,'errors':len(result.errors),'failures':len(result.failures),'skipped':len(result.skipped)},
        'sdk_mismatch_refusals':sdk,'automatic_fatal_resolution':fatal,'actual_generic_merlin_hook':merlin,
        'launcher_sha256':sha(package/'launch.py'),'input_sha256':{str(path):sha(path)for path in paths},
        'artifact_sha256':{path.name:sha(path)for path in out.iterdir()if path.is_file()},
        'primary_published':False,'hardware_contacted':False,'rtl_certified':False,'full_knownness_certified':False,
        'timing_calibrated':False,'held_out_2pct':False,'deployed_image_association_verified':False}
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(out/'results.json')
    raise SystemExit(0 if report['pass']else 1)
if __name__=='__main__':main()
