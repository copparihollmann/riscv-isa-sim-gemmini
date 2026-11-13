"""Require actual positive controls and named refusals before qualifying memory."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE=Path(__file__).resolve().parents[1]/'run_functional.py'
spec=importlib.util.spec_from_file_location('memory_evidence_runner',MODULE)
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)

class MemoryEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.previous=runner.HERE;runner.HERE=self.root/'spike';(runner.HERE/'bin').mkdir(parents=True)
        self.out=self.root/'build/memory-live';self.out.mkdir(parents=True)
        self.binary=runner.HERE/'spike';self.binary.write_bytes(b'binary')
        self.uart=runner.HERE/'bin/libsifive_uart.so';self.uart.write_bytes(b'uart')
        self.data={'status':'passed_address_routed_live_fixtures','binary_sha256':runner.sha(self.binary),
            'uart_sha256':runner.sha(self.uart),'scope':'synthetic scalar M-mode only','calibrated':False,
            'iris_accuracy_certified':False,'results':[],'negative_results':[],'source_sha256':{}}
        for name in ['timing/memory_live_check.py','timing/memory_guest.c','timing/memory_guard_guest.S',
            'timing/scalar_memory.hpp','timing/scalar_memory.cpp','timing/memory_path.hpp','timing/memory_path.cpp',
            'timing/iris_timing.hpp','timing/iris_timing.cpp','timing/order_guest.S',
            'benchmarks/start.S','benchmarks/runtime.c','benchmarks/runtime.h','benchmarks/link.ld']:
            path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(name.encode())
            self.data['source_sha256'][name]=runner.sha(path)
        for name in ['regions-fast','regions-slow','load-first','store-first','seed17','seed17-repeat']:
            paths={kind:self.out/(name+'.'+kind) for kind in ['elf','fixture','graph','stdout','stderr']}
            for kind,path in paths.items():path.write_bytes((name+kind).encode())
            self.data['results'].append({'name':name,'pass':True,'argv':[str(self.binary),
                '--extlib='+str(self.uart),'--iris-timing-fixture='+str(paths['fixture']),
                '--iris-timing-trace='+str(paths['graph']),str(paths['elf'])],
                **{kind+'_sha256':runner.sha(path) for kind,path in paths.items()}})
        errors={'vector':'MEMORY_OPERATION_UNMODELED','mprv':'TRANSLATED_MEMORY_UNMODELED',
            'missing-port':'memory stage port missing','ambiguous':'AMBIGUOUS_MEMORY_ROUTE',
            'missing-route':'MEMORY_ROUTE_MISSING','zero-clock':'explicit clock',
            'rv32':'IRIS_TIMING_SCALAR_MEMORY_REQUIRES_RV64'}
        for name,error in errors.items():
            fixture=self.out/(name+'.fixture');fixture.write_bytes(name.encode())
            stderr=self.out/(name+'.stderr');stderr.write_text(error)
            row={'name':name,'pass':True,'exit_status':1,'fixture_sha256':runner.sha(fixture),'stderr_sha256':runner.sha(stderr)}
            if name in {'vector','mprv'}:
                row['functional_exit_status']=0
                for suffix,key in [('elf','elf'),('functional.stdout','functional_stdout'),('functional.stderr','functional_stderr')]:
                    path=self.out/(name+'.'+suffix);path.write_bytes((name+suffix).encode());row[key+'_sha256']=runner.sha(path)
            self.data['negative_results'].append(row)
        self.save()
    def tearDown(self):runner.HERE=self.previous;self.temp.cleanup()
    def save(self):(self.out/'results.json').write_text(json.dumps(self.data))
    def tested(self):return runner.memory_fixture_evidence(self.binary)[0]['tested']
    def test_complete_bound_fixture(self):self.assertTrue(self.tested())
    def test_rv32_rejection_is_required(self):
        self.data['negative_results'].pop();self.save();self.assertFalse(self.tested())
    def test_synthetic_fixture_cannot_claim_calibration(self):
        self.data['calibrated']=True;self.save();self.assertFalse(self.tested())
    def test_functional_positive_control_is_required(self):
        self.data['negative_results'][0]['functional_exit_status']=1;self.save();self.assertFalse(self.tested())
    def test_graph_bytes_are_bound(self):
        (self.out/'seed17.graph').write_bytes(b'changed');self.assertFalse(self.tested())
    def test_unrelated_failure_does_not_qualify_rejection(self):
        path=self.out/'rv32.stderr';path.write_text('ELF failed to load')
        self.data['negative_results'][-1]['stderr_sha256']=runner.sha(path);self.save();self.assertFalse(self.tested())

if __name__=='__main__':unittest.main()
