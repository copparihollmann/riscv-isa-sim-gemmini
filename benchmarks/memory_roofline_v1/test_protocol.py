"""Independent arithmetic checks and rejection of plausible corrupt evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from build import accounting, cases, oracle, weighted
from validate import validate

class Protocol(unittest.TestCase):
    def test_exact_inventory_and_bounds(self):
        rows=cases();self.assertEqual(len(rows),144)
        self.assertEqual(sum(c['kind']==5 for c in rows),12)
        for c in rows:
            self.assertEqual(c['bytes'] & (c['bytes']-1),0)
            limit=8388608 if c['tier']==0 else 16384 if c['tier']==1 else 32768
            self.assertLessEqual(c['pitch']*c['rows'] if c['kind']==5 else c['bytes'],limit)
            if c['kind']==4:self.assertGreaterEqual(c['bytes']//64*c['repeats'],1024)
    def test_periodic_weighted_matches_naive(self):
        for values in [[3,11,7],[2**32-1,5],[19]]:
            for n in [0,1,2,3,7,64,127]:
                self.assertEqual(weighted(n,values),sum(values[i%len(values)]*(i+1) for i in range(n))%2**64)
    def test_numerical_oracles_and_byte_accounting(self):
        for kind in [0,1,2,3,5,6]:
            c=dict(kind=kind,bytes=128,repeats=3,pitch=2048,rows=7)
            if kind in [0,6]:expected=sum((17*i+11)&65535 for i in range(32))*3%2**32
            elif kind==5:expected=sum((17*(row*512+i)+11)&65535 for row in range(7) for i in range(32))*3%2**32
            else:expected=sum((0x3c3c3c3c if kind==1 else ((17*i+11)&65535) if kind==2 else ((17*i+11)&65535)+3*((29*i+23)&65535))*(i+1) for i in range(32))%2**64
            self.assertEqual(oracle(c,0x90000000),expected)
        c=dict(kind=2,bytes=2048,repeats=32,pitch=0,rows=0)
        self.assertEqual(accounting(c)['requested_bytes'],131072)
        self.assertEqual(accounting(c)['active_data_address_span_bytes'],4096)
    def test_parser_rejects_corruption_missing_duplicate_foreign_hart(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);elf=p/'guest';elf.write_bytes(b'fixture')
            import hashlib
            c=dict(tier=0,kind=0,bytes=2048,repeats=32,pitch=0,rows=0,expected_checksum=123,**accounting(dict(kind=0,bytes=2048,repeats=32,pitch=0,rows=0)))
            manifest=dict(ELF=str(elf),ELF_sha256=hashlib.sha256(b'fixture').hexdigest(),negative_omitted_kernel=False,input_sha256={},cases=[c],expected_regions=1)
            (p/'manifest.json').write_text(json.dumps(manifest));(p/'cases.json').write_text(json.dumps([dict(id='memroof_c0_r0',expected_checksums_by_hart=[123])]))
            r=dict(case_id='memroof_c0_r0',region='memory_kernel',hart=0,start_cycle=20,end_cycle=80,start_instret=1,end_instret=8,instret_delta=7,checksum=123,warmup=False,**{'pass':True})
            def text(row):return 'IRIS_PROGRESS v1 START 1\nIRIS_REGION '+json.dumps(row)+'\nIRIS_MEMROOF 0 0 0 0 2048 32 0 0 10 11 123 0\nIRIS_PROGRESS v1 DONE 1 memroof_c0_r0 123\nIRIS_BATCH_DONE passed=1 failed=0\nDONE\n'
            self.assertTrue(validate(text(r),p)['pass'])
            for k,v in [('checksum',124),('hart',2),('pass',False),('end_cycle',19),('instret_delta',99)]:
                bad=copy.deepcopy(r);bad[k]=v
                with self.assertRaises(ValueError):validate(text(bad),p)
            with self.assertRaises(ValueError):validate(text(r).replace('IRIS_MEMROOF','REMOVED'),p)
            with self.assertRaises(ValueError):validate(text(r)+'IRIS_REGION '+json.dumps(r)+'\n',p)

if __name__=='__main__':unittest.main()
