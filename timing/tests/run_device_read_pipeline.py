"""Synthetic native composition controls only; no guest/physical simulation."""
from pathlib import Path
import argparse,copy,importlib.util,json,subprocess
ROOT=Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build-dir',type=Path,required=True);p.add_argument('--boost-include',type=Path);args=p.parse_args();build=args.build_dir.absolute()
 if build==ROOT or ROOT in build.parents:p.error('build directory must be outside checkout')
 build.mkdir(parents=True,exist_ok=True)
 sp=importlib.util.spec_from_file_location('fixture',ROOT/'timing/tests/run_native.py');fixture=importlib.util.module_from_spec(sp);sp.loader.exec_module(fixture)
 model=fixture.fixture_model('0'*64);model['memory']['caches']['l2']={'sets':16,'ways':2,'line_bytes':64,'policy':'write_back_write_allocate'}
 model['memory']['paths'].update(cpu_data=['l1d','l2'],device=['l2']);model['memory']['transaction_accounting']='coherence_request_separate_v1'
 model['parameters'].update({'memory.l2.hit_cycles':1,'memory.l2.miss_cycles':1})
 model['resources'].append({'id':3,'name':'memory.l1d.probe','capacity':1,'queue_capacity':2})
 model['memory']['caches']['l1d']['coherence_probe_service']={'schema':'merlin.private_cache_probe_service.v1','resource':'memory.l1d.probe','beat_bytes':16,'lookup_cycles':20,'dirty_enter_cycles':1,'data_pipeline_cycles':2,'metadata_cycles':1}
 paths=[]
 for name in ('old','source','bad_scalar'):
  row=copy.deepcopy(model)
  if name!='old':row['memory']['device_read_pipeline']={'schema':'merlin.source_device_read_pipeline.v1','enabled':1,'cache':'l2','directory_stages':1,'mshr_plan_stages':1,'source_d_stages':2,'scalar_lookup_cycles':1,'source_receipt_sha256':'0'*64}
  if name=='bad_scalar':row['parameters']['memory.l2.miss_cycles']=2
  path=build/(name+'.json');path.write_text(json.dumps(row));paths.append(path)
 binary=build/'device_read_pipeline';flags=['g++','-std=c++20','-O1','-g0','-I'+str(ROOT/'timing'),'-I'+str(ROOT/'timing/core/include')]
 if args.boost_include:flags+=['-I'+str(args.boost_include)]
 subprocess.run([*flags,str(ROOT/'timing/tests/test_device_read_pipeline.cpp'),str(ROOT/'riscv/annotated_timing_memory.cc'),str(ROOT/'riscv/annotated_timing_model.cc'),'-lcrypto','-o',str(binary)],check=True,timeout=90)
 subprocess.run([str(binary),*map(str,paths)],check=True,timeout=10)
 print('Native cache source pipeline: cold/hit replacement, coherent max, CPU/write unchanged, mismatched scalar refusal PASS')
if __name__=='__main__':main()
