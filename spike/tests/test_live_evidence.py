"""Reject missing or stale evidence before advertising live-clock integration."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE=Path(__file__).resolve().parents[1]/'run_functional.py'
spec=importlib.util.spec_from_file_location('run_functional_evidence_test',MODULE)
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)


class LiveEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.previous=runner.HERE;runner.HERE=self.root/'spike';runner.HERE.mkdir()
        self.out=self.root/'build/timing-live';self.out.mkdir(parents=True)
        self.binary=runner.HERE/'spike';self.binary.write_bytes(b'binary')
        self.uart=self.out/'uart.so';self.uart.write_bytes(b'uart')
        self.data={'status':'passed_integration_fixtures','binary_sha256':runner.sha(self.binary),
                   'uart_sha256':runner.sha(self.uart),'scope':'synthetic fixture only','results':[],
                   'negative_results':[],'source_sha256':{}}
        for name in ['timing/live_check.py','timing/counter_guest.c','timing/order_guest.S','timing/exit_guest.S',
                     'timing/fixtures/three-hart-fast.fixture','timing/fixtures/three-hart-slow.fixture',
                     'benchmarks/start.S','benchmarks/runtime.c','benchmarks/runtime.h','benchmarks/link.ld']:
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(name.encode())
            self.data['source_sha256'][name]=runner.sha(p)
        dts=self.out/'fixture.dts';dts.write_bytes(b'dts')
        self.data['generated_dts_sha256']=runner.sha(dts)
        for name in ['counter-fast','counter-slow','counter-idle-gated','counter-seed','counter-seed-repeat',
                     'order-load-first','order-store-first','exit-busy-peers']:
            paths={kind:self.out/(name+'.'+kind) for kind in ['elf','fixture','graph','stdout','stderr']}
            for kind,path in paths.items():path.write_bytes((name+kind).encode())
            self.data['results'].append({'name':name,'pass':True,'argv':[str(self.binary),
                '--extlib='+str(self.uart),'--iris-timing-fixture='+str(paths['fixture']),
                '--iris-timing-trace='+str(paths['graph']),str(paths['elf'])],
                **{kind+'_sha256':runner.sha(path) for kind,path in paths.items()}})
        for name in ['no-calibration-claim','missing-hart','negative-latency']:
            fixture=self.out/(name+'.fixture');error=self.out/(name+'.stderr')
            fixture.write_bytes(name.encode());error.write_bytes(b'expected diagnostic')
            self.data['negative_results'].append({'name':name,'pass':True,'exit_status':1,
                'fixture_sha256':runner.sha(fixture),'stderr_sha256':runner.sha(error)})
        self.save()

    def tearDown(self):runner.HERE=self.previous;self.temp.cleanup()
    def save(self):(self.out/'results.json').write_text(json.dumps(self.data))
    def tested(self):return runner.live_fixture_evidence(self.binary)[0]['tested']

    def test_complete_bound_fixture(self):self.assertTrue(self.tested())
    def test_uart_and_generated_dts_are_bound(self):
        self.uart.write_bytes(b'changed');self.assertFalse(self.tested())
        self.uart.write_bytes(b'uart');(self.out/'fixture.dts').write_bytes(b'changed')
        self.assertFalse(self.tested())
    def test_duplicate_success_cannot_replace_required_case(self):
        self.data['results'][-1]=self.data['results'][0];self.save()
        self.assertFalse(self.tested())
    def test_rejection_evidence_is_required_and_bound(self):
        self.data['negative_results'].pop();self.save();self.assertFalse(self.tested())
    def test_rejection_must_actually_exit_nonzero(self):
        self.data['negative_results'][0]['exit_status']=0;self.save();self.assertFalse(self.tested())
    def test_stale_rejection_log_is_not_accepted(self):
        (self.out/'missing-hart.stderr').write_bytes(b'changed');self.assertFalse(self.tested())
    def test_missing_source_binding_is_not_accepted(self):
        self.data['source_sha256'].pop('timing/live_check.py');self.save();self.assertFalse(self.tested())


if __name__=='__main__':unittest.main()
