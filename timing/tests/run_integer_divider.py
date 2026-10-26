#!/usr/bin/env python3
"""Focused model selection/decode checks; no simulator or calibrated labels."""
import argparse
import copy
import importlib.util
import json
import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--build-dir', type=Path, required=True)
p.add_argument('--boost-include', type=Path)
a = p.parse_args()
a.build_dir.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location('fixtures', ROOT/'timing/tests/run_native.py')
f = importlib.util.module_from_spec(spec); spec.loader.exec_module(f)
model = f.fixture_model('0'*64)
model['parameters'].pop('cpu.divide.latency_cycles', None)
model['parameters'].pop('cpu.divide.occupancy_cycles', None)
model['resources'].append(dict(id=127, name='cpu.muldiv', capacity=1, queue_capacity=0))
model.setdefault('cpu_execution_resources', {}).update({'cpu.divide':'cpu.muldiv', 'cpu.multiply':'cpu.muldiv'})
selection = dict(schema='merlin.rocket_integer_divider_service_bound.v1', xlen=64,
    div_unroll=1, early_out=True, early_out_granularity=1,
    response_ready='assumed_immediate', rtl_sha256='a'*64, source_sha256='b'*64)
selected=copy.deepcopy(model); selected.setdefault('cpu', {})['integer_divider_service']=selection
operand=copy.deepcopy(selected);operand['cpu']['integer_divider_service']['schema']='merlin.rocket_integer_divider_operand_service.v2'
cases=[('legacy',model,'legacy'),('selected',selected,'selected'),('operand',operand,'selected')]
for name,key,value in [('unroll','div_unroll',2),('xlen','xlen',32),('earlyout','early_out',False),
    ('granularity','early_out_granularity',2),('backpressure','response_ready','unbounded'),
    ('pin','rtl_sha256','bad'),('unknown','extra',1)]:
    d=copy.deepcopy(selected);d['cpu']['integer_divider_service'][key]=value;cases.append((name,d,'reject'))
for key in ['cpu.divide.latency_cycles','cpu.divide.occupancy_cycles']:
    d=copy.deepcopy(selected);d['parameters'][key]=1;cases.append((key,d,'reject'))
for key,value in [('capacity',2),('queue_capacity',1)]:
    d=copy.deepcopy(selected);d['resources'][-1][key]=value;cases.append((key,d,'reject'))
d=copy.deepcopy(selected);d['cpu_execution_resources']['cpu.multiply']='other';cases.append(('separate',d,'reject'))
exe=a.build_dir/'test-integer-divider'
flags=['g++','-std=c++20','-O1','-g0','-I'+str(ROOT/'timing'),'-I'+str(ROOT/'timing/core/include')]
if a.boost_include: flags.append('-I'+str(a.boost_include))
subprocess.run([*flags,str(ROOT/'timing/tests/test_integer_divider_model.cpp'),str(ROOT/'riscv/annotated_timing_model.cc'),'-lcrypto','-o',str(exe)],check=True,timeout=120)
for name,doc,mode in cases:
    path=a.build_dir/(name+'.json');path.write_text(json.dumps(doc))
    subprocess.run([str(exe),str(path),mode],check=True,timeout=10)
print(f'{len(cases)} selection cases and eight divide/remainder decodings passed')

service=a.build_dir/'test-divider-service'
subprocess.run([*flags,str(ROOT/'timing/tests/test_integer_divider_service.cpp'),'-o',str(service)],check=True,timeout=120)
subprocess.run([str(service)],check=True,timeout=30)
print('8264 operand cases match selected RTL register interpreter and architectural results')
