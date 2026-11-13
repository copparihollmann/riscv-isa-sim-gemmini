"""Offline counter-bound proofs and refusal controls, without hardware access."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).parents[1]))
from fased_activity_bounds import calculate, MOD, verify_associations, REVIEWED_DRIVER


NAMES = [f'{s}OutstandingHistogram_{i}' for s in ('read', 'write') for i in range(5)] + [
    'totalReads', 'totalReadBeats', 'totalWrites', 'totalWriteBeats', 'brespError', 'rrespError']


def raw(rows):
    return (','.join(NAMES)+',\n' + ''.join(
        ','.join(str(r.get(n, 0)) for n in NAMES)+',\n' for r in rows)).encode()


class BoundsTests(unittest.TestCase):
    def end(self):
        return dict(readOutstandingHistogram_0=40, readOutstandingHistogram_1=60,
                    writeOutstandingHistogram_0=90, writeOutstandingHistogram_1=10,
                    totalReadBeats=20, totalReads=5, totalWriteBeats=8, totalWrites=2)

    def test_exact_coverage_activity_and_wire_capacity(self):
        r=calculate(raw([{}, self.end()]), NAMES, 100)
        self.assertTrue(r['all_interval_counter_lifts_unique'])
        self.assertEqual(r['direction_activity']['read']['outstanding_nonempty_fraction_bounds'], [.6, .6])
        self.assertEqual(r['direction_activity']['read']['AXI_wire_payload_capacity_bytes'], 160)
        self.assertEqual(r['direction_activity']['read']['data_channel_accepted_beat_fraction_bounds'], [.2, .2])
        self.assertIsNone(r['usable_write_bytes'])
        self.assertIsNone(r['memory_chip_busy_fraction'])

    def test_missing_overflow_yields_bounds_not_fake_complete_histogram(self):
        r=calculate(raw([{}, self.end()]), NAMES, 110)
        self.assertEqual(r['profiled_memory_cycles_bounds'], [100,110])
        self.assertEqual(r['direction_activity']['read']['outstanding_nonempty_fraction_bounds'], [.6,1-40/110])
        self.assertFalse(r['overflow_bin_complete'])
        self.assertFalse(r['per_region_attribution'])

    def test_counter_wrap_unique_under_interval_bound(self):
        a={n: MOD-10 for n in NAMES if n not in ('brespError','rrespError') and not n.endswith('_4')}
        b={n:(a.get(n,0)+self.end().get(n,0))%MOD for n in NAMES}
        r=calculate(raw([a,b]),NAMES,100)
        self.assertEqual(r['unwrapped_counters']['totalReadBeats'],20)

    def test_extra_wrap_ambiguity_withholds_unwrapped_metrics(self):
        r=calculate(raw([{},self.end()]),NAMES,MOD+100)
        self.assertFalse(r['all_interval_counter_lifts_unique'])
        self.assertIsNone(r['unwrapped_counters'])
        self.assertIsNone(r['direction_activity'])

    def test_global_budget_can_bound_many_intervals(self):
        a=self.end(); b={k:2*v for k,v in a.items()}
        r=calculate(raw([{},a,b]),NAMES,210)
        self.assertEqual(r['profiled_memory_cycles_bounds'],[200,210])
        self.assertEqual([v['memory_cycles_upper_bound'] for v in r['intervals']],[110,110])

    def test_impossible_rate_refused(self):
        a=self.end();a['totalReadBeats']=120
        with self.assertRaises(ValueError): calculate(raw([{},a]),NAMES,110)

    def test_clock_contradiction_refused(self):
        with self.assertRaises(ValueError): calculate(raw([{},self.end()]),NAMES,99)

    def test_changed_overflow_mapping_refused(self):
        a=self.end();a['readOutstandingHistogram_4']=1
        with self.assertRaises(ValueError): calculate(raw([{},a]),NAMES,110)

    def test_unsigned_and_complete_snapshots_required(self):
        for value in (-1,MOD):
            a=self.end();a['totalReads']=value
            with self.assertRaises(ValueError): calculate(raw([{},a]),NAMES,100)
        with self.assertRaises(ValueError): calculate(raw([{}]),NAMES,100)

    def test_no_clock_frequency_or_hart_allocation_invented(self):
        r=calculate(raw([{},self.end()]),NAMES,100)
        self.assertFalse(r['per_hart_attribution'])
        self.assertIsNone(r['serial_TL_bandwidth'])
        self.assertIsNone(r['NoC_link_bandwidth'])
        self.assertNotIn('bytes_per_second',r)


class AssociationTests(unittest.TestCase):
    def fixture(self):
        audit=Path('/audited/report.json');a='a'*64;b='b'*64;bundle='/artifacts/driver-bundle.tar.gz'
        manifest=dict(observability_audit=dict(report=str(audit),sha256=a,fased={'known':True}),
                      input_sha256={str(audit):a,bundle:b},driver=dict(uri='file://'+bundle,sha256=b))
        evidence=dict(fased={'known':True},input_sha256={bundle:b},driver_binary_sha256=REVIEWED_DRIVER,
                      driver_members=[dict(name='FireSim-corigine_mimicturbo_gt',sha256=REVIEWED_DRIVER)])
        ids={'job/prepared-inputs/'+a:a,'job/prepared-inputs/'+b:b}
        return manifest,evidence,audit,a,ids

    def test_matching_actual_associations(self):
        self.assertEqual(verify_associations(*self.fixture()),Path('/artifacts/driver-bundle.tar.gz'))

    def test_unbound_audit_refused(self):
        m,e,p,a,ids=self.fixture();m['observability_audit']['sha256']='0'*64
        with self.assertRaises(ValueError):verify_associations(m,e,p,a,ids)

    def test_different_run_driver_refused(self):
        m,e,p,a,ids=self.fixture();m['driver']['sha256']='0'*64
        with self.assertRaises(ValueError):verify_associations(m,e,p,a,ids)

    def test_changed_binary_semantics_refused(self):
        m,e,p,a,ids=self.fixture();e['driver_binary_sha256']='0'*64
        with self.assertRaises(ValueError):verify_associations(m,e,p,a,ids)


if __name__=='__main__':unittest.main()
