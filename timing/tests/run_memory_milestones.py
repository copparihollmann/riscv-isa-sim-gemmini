"""Bounded native memory identity controls; no guest or physical simulation."""
from pathlib import Path
import argparse
import importlib.util
import json
import subprocess
ROOT=Path(__file__).resolve().parents[2]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build-dir',type=Path,required=True)
    p.add_argument('--boost-include',type=Path)
    args=p.parse_args();build=args.build_dir.absolute()
    if build==ROOT or ROOT in build.parents:p.error('build directory must be outside source')
    build.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('native_fixture',ROOT/'timing/tests/run_native.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    model=module.fixture_model('0'*64)
    model['memory']['caches']['l2']={'sets':16,'ways':2,'line_bytes':64,'policy':'write_back_write_allocate'}
    model['memory']['paths']['device']=['l2']
    model['parameters'].update({'memory.l2.hit_cycles':1,'memory.l2.miss_cycles':1})
    profile=build/'fixture.json';profile.write_text(json.dumps(model))
    flags=['g++','-std=c++20','-O1','-g0','-I'+str(ROOT/'timing'),'-I'+str(ROOT/'timing/core/include')]
    if args.boost_include:flags+=['-I'+str(args.boost_include)]
    for name in ('memory_milestones','posted_memory'):
        binary=build/name
        subprocess.run([*flags,str(ROOT/('timing/tests/test_'+name+'.cpp')),str(ROOT/'riscv/annotated_timing_memory.cc'),str(ROOT/'riscv/annotated_timing_model.cc'),'-lcrypto','-o',str(binary)],check=True,timeout=90)
        subprocess.run([str(binary),str(profile)],check=True,timeout=10)
if __name__=='__main__': main()
