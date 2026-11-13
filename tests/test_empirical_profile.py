import copy
import json
from pathlib import Path
import tempfile
import unittest

from iris_model.empirical_profile import profile, sha, verify_execution


def sample():
    a = {'schema': 'iris.empirical.prefix.v1', 'hart': 0, 'sequence': 4,
         'value': 900, 'read_cycle': 100, 'retired': 20,
         'endpoint': 'get_csr_before_current_instruction_retirement',
         'calibration_identity': 'test-only',
         'resource_occupancy_scope': 'global_shared_resources',
         'features': {'vme.int8': {'instructions': 1, 'macs': 512}},
         'memory': {}, 'completed_resource_busy_cycles': {'shared': 0},
         'resource_occupancy_prefix': {'shared': {'union_cycles': 50, 'lane_service_cycles': 80}}}
    b = copy.deepcopy(a)
    # A CSR write/inhibition can make mcycle diverge from global elapsed time.
    b.update(sequence=8, value=905, read_cycle=110, retired=24)
    b['features']['vme.int8'] = {'instructions': 2, 'macs': 1024}
    b['completed_resource_busy_cycles']['shared'] = 30
    b['resource_occupancy_prefix']['shared'] = {'union_cycles': 58, 'lane_service_cycles': 96}
    row = {'hart': 0, 'case_id': 'case', 'region': 'kernel', 'start_cycle': 900,
           'end_cycle': 905, 'cycles': 5, 'instret_delta': 6}
    return [a, b], 'IRIS_REGION ' + json.dumps(row)


def run(rows, console):
    return profile((json.dumps(r) for r in rows), console, 500_000_000)


class EmpiricalProfileTests(unittest.TestCase):
    def test_occupancy_union_and_completed_service_are_distinct(self):
        rows, console = sample(); rows[0]['async_compute_pending'] = False
        rows[1]['async_compute_pending'] = True
        report, trace = run(rows, console); region = report['regions'][0]
        self.assertEqual(region['guest_mcycle_delta'], 5)
        self.assertEqual(region['timeline_cycles'], 10)
        self.assertEqual(region['completed_service_cycles_sum']['shared'], 30)
        self.assertEqual(region['modeled_resource_occupancy']['shared']['modeled_busy_fraction'], .8)
        self.assertEqual(region['modeled_resource_occupancy']['shared']['lane_service_cycles_sum'], 16)
        self.assertEqual(region['architectural_work_features']['vme.int8']['macs'], 512)
        self.assertEqual(region['retired_between_mcycle_read_endpoints'], 4)
        self.assertEqual(region['guest_instret_delta'], 6)
        self.assertIsNone(region['roofline'])
        self.assertEqual(region['async_owner_present_at_boundaries'], [False, True])
        self.assertEqual(trace['traceEvents'][0]['dur'], .02)

    def test_uninstrumented_occupancy_is_unavailable(self):
        rows, console = sample()
        for row in rows: del row['resource_occupancy_prefix']
        report, _ = run(rows, console)
        self.assertIsNone(report['regions'][0]['modeled_resource_occupancy'])

    def test_actual_merlin_record_requires_explicit_identity(self):
        rows, _ = sample(); console = 'REGION 0 900 905 6\n'
        with self.assertRaisesRegex(ValueError, 'explicit case ID'): run(rows, console)
        report, _ = profile(map(json.dumps, rows), console, 500_000_000, legacy_case_id='gemm')
        region = report['regions'][0]
        self.assertEqual((region['case_id'], region['guest_instret_delta']), ('gemm', 6))
        self.assertIsNone(region['guest_reported_pass'])

    def test_counter_wrap_does_not_rebase_global_timeline(self):
        rows, _ = sample(); rows[0]['value'] = (1 << 64) - 2; rows[1]['value'] = 3
        console = 'IRIS_REGION ' + json.dumps({'hart': 0, 'case_id': 'wrap', 'region': 'r',
            'start_cycle': rows[0]['value'], 'end_cycle': 3, 'cycles': 5})
        report, _ = run(rows, console)
        self.assertEqual(report['regions'][0]['guest_mcycle_delta'], 5)

    def test_throughput_uses_elapsed_model_time_and_preserves_intent_scope(self):
        rows, console = sample()
        rows[0]['memory'] = {'TCM': {'bytes': 8}}
        rows[1]['memory'] = {'TCM': {'bytes': 72}}
        rows[1]['async_compute_pending'] = True
        report, _ = run(rows, console)
        region = report['regions'][0]
        rates = region['architectural_retirement_rates']
        self.assertEqual(rates['instructions_per_model_cycle'], .4)
        self.assertEqual(rates['architectural_MACs_per_model_cycle'], 51.2)
        self.assertEqual(rates['by_feature']['vme.int8']['architectural_MACs_per_model_cycle'], 51.2)
        self.assertIsNone(rates['peak_efficiency'])
        traffic = region['accepted_memory_timing_intent_rates']['TCM']
        self.assertEqual(traffic['accepted_bytes'], 64)
        self.assertEqual(traffic['accepted_bytes_per_model_cycle'], 6.4)
        self.assertEqual(traffic['accepted_bytes_per_model_second'], 3_200_000_000)
        self.assertIn('not physical completed', traffic['semantics'])
        self.assertEqual(region['guest_mcycle_delta'], 5)
        self.assertEqual(region['timeline_cycles'], 10)
        self.assertEqual(region['async_owner_present_at_boundaries'], [None, True])

    def test_two_pending_owners_and_instruction_fetch_carry_are_explicit(self):
        rows, console = sample()
        rows[0].update(async_compute_pending=False, async_pending_count=0)
        rows[1].update(async_compute_pending=True, async_pending_count=2)
        fetch = {'owner': 7, 'node': 91, 'address': 0x8000003e, 'bytes': 4,
                 'l1misses': 1, 'l2misses': 1, 'submitted': 92, 'issued': True, 'start': 94, 'end': 104}
        rows[0]['pending_instruction_fetch'] = fetch
        rows[1]['pending_instruction_fetch'] = None
        rows[0]['features']['vme.int8'].update(dlen_beats=0, atl_beats=0)
        rows[1]['features']['vme.int8'].update(dlen_beats=4, atl_beats=8)
        report, _ = run(rows, console); region = report['regions'][0]
        self.assertEqual(region['async_owner_count_at_boundaries'], [0, 2])
        self.assertEqual(region['pending_instruction_fetch_at_boundaries'], [fetch, None])
        rates = region['architectural_retirement_rates']['by_feature']['vme.int8']
        self.assertEqual(rates['dlen_beats_per_model_cycle'], .4)
        self.assertEqual(rates['atl_beats_per_model_cycle'], .8)
        rows[1]['async_pending_count'] = False
        with self.assertRaises(ValueError): run(rows, console)
        rows[1]['async_pending_count'] = 2
        rows[0]['pending_instruction_fetch']['end'] = 100
        run(rows, console)  # Completion callback can follow this same-edge read.
        rows[0]['pending_instruction_fetch']['end'] = 99
        with self.assertRaisesRegex(ValueError, 'span'): run(rows, console)

    def test_missing_ambiguous_or_wrong_hart_boundary_refuses(self):
        rows, console = sample()
        with self.assertRaisesRegex(ValueError, 'Missing'): run(rows[:1], console)
        duplicate = copy.deepcopy(rows[-1]); duplicate['sequence'] += 1
        with self.assertRaisesRegex(ValueError, 'Ambiguous'): run(rows + [duplicate], console)
        rows[-1]['hart'] = 1
        with self.assertRaisesRegex(ValueError, 'Missing'): run(rows, console)

    def test_legacy_null_fetch_does_not_claim_complete_frontend_coverage(self):
        rows, console = sample()
        for row in rows: row['pending_instruction_fetch'] = None
        report, _ = run(rows, console); region = report['regions'][0]
        self.assertEqual(region['pending_instruction_fetch_at_boundaries'], [None, None])
        self.assertEqual(region['instruction_fetch_observation_scope_at_boundaries'], [None, None])
        self.assertIn('does not establish', region['instruction_fetch_observation_limit'])
        rows[0]['instruction_fetch_observation_scope'] = 'empirical-private-Icache-refill-owner'
        report, _ = run(rows, console)
        self.assertEqual(report['regions'][0]['instruction_fetch_observation_scope_at_boundaries'],
                         ['empirical-private-Icache-refill-owner', None])
        for invalid in [False, 1, '', '  ', None]:
            rows[0]['instruction_fetch_observation_scope'] = invalid
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, 'scope required'):
                run(rows, console)

    def test_corrupted_prefix_and_invented_occupancy_refuse(self):
        for field, change in [('retired', 19), ('sequence', 3), ('read_cycle', 99),
                              ('calibration_identity', 'other')]:
            rows, console = sample(); rows[-1][field] = change
            with self.subTest(field=field), self.assertRaises(ValueError): run(rows, console)
        rows, console = sample(); rows[-1]['resource_occupancy_prefix']['shared']['union_cycles'] = 61
        with self.assertRaisesRegex(ValueError, 'exceeds'): run(rows, console)
        rows, console = sample(); rows[-1]['features']['vme.int8']['macs'] = 1
        with self.assertRaisesRegex(ValueError, 'decreased'): run(rows, console)

    def test_elf_binding_uses_exact_csr_instruction(self):
        class Instructions:
            def read(self, pc): return 0xc0002573
        rows, console = sample()
        for row in rows: row.update(pc=0x80000000, raw=0xc0002573)
        report, _ = profile(map(json.dumps, rows), console, 500_000_000, Instructions(),
                            [(0x80000000, 0x80000010, 'measure')])
        self.assertEqual(report['regions'][0]['boundary_functions'], ['measure', 'measure'])
        rows[-1]['raw'] = 0xb0002573
        with self.assertRaisesRegex(ValueError, 'differs'): profile(map(json.dumps, rows), console,
                                                                  500_000_000, Instructions())
        rows, console = sample()
        with self.assertRaisesRegex(ValueError, 'requires captured PC'):
            profile(map(json.dumps, rows), console, 500_000_000, Instructions())

    def test_discarded_counter_read_cannot_create_ambiguous_region(self):
        rows, console = sample()
        for row in rows: row.update(pc=0x1000, raw=0xb0002573)
        discarded = copy.deepcopy(rows[0])
        discarded.update(sequence=5, read_cycle=103, retired=21, pc=0x1010,
                         raw=0xb0002073, destination=0, result_discarded=True)
        class Instructions:
            def read(self, pc): return 0xb0002073 if pc == 0x1010 else 0xb0002573
        report, _ = profile(map(json.dumps, [rows[0], discarded, rows[1]]), console,
                            500_000_000, Instructions())
        self.assertEqual(report['regions'][0]['guest_mcycle_delta'], 5)

    def test_run_receipt_rejects_changed_nonboundary_elf_or_stream_bytes(self):
        # These are admission fixtures, not claimed simulated executions.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            elf, fixture, console, prefix = [root / name for name in ('guest.elf', 'model.fixture', 'stdout', 'features')]
            for path in (elf, fixture, console, prefix): path.write_text('test-only-' + path.name)
            receipt = root / 'report.json'
            receipt.write_text(json.dumps({'pass': True,
                'argv': ['/unit-test-only', '--iris-timing-fixture=' + str(fixture), str(elf)],
                'input_sha256': {str(elf): sha(elf), str(fixture): sha(fixture)},
                'artifact_sha256': {'stdout': sha(console), 'features': sha(prefix)}}))
            self.assertEqual(verify_execution(receipt, elf, fixture, console, prefix)['receipt_sha256'], sha(receipt))
            for path in (elf, fixture, console, prefix):
                original = path.read_bytes(); path.write_bytes(original + b'changed')
                with self.subTest(path=path.name), self.assertRaisesRegex(ValueError, 'unique run'):
                    verify_execution(receipt, elf, fixture, console, prefix)
                path.write_bytes(original)

    def test_aggregate_cannot_mix_child_console_prefix_and_sensitivity_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); elf = root / 'guest.elf'; elf.write_text('unit-only')
            fixtures = [root / ('model' + str(i)) for i in range(2)]
            consoles = [root / ('stdout' + str(i)) for i in range(2)]
            prefixes = [root / ('features' + str(i)) for i in range(2)]
            for path in fixtures + consoles + prefixes: path.write_text('unit-' + path.name)
            children = [{'pass': True, 'argv': ['/unit-only', '--iris-timing-fixture=' + str(fixtures[i]), str(elf)],
                         'output_sha256': {str(consoles[i]): sha(consoles[i]), str(prefixes[i]): sha(prefixes[i])}}
                        for i in range(2)]
            receipt = root / 'report.json'
            receipt.write_text(json.dumps({'pass': True, 'runs': children,
                'input_sha256': {str(p): sha(p) for p in [elf] + fixtures},
                'evidence_sha256': {str(p): sha(p) for p in consoles + prefixes}}))
            verify_execution(receipt, elf, fixtures[0], consoles[0], prefixes[0])
            for fixture, console, prefix in ((fixtures[1], consoles[0], prefixes[0]),
                                             (fixtures[0], consoles[0], prefixes[1])):
                with self.assertRaisesRegex(ValueError, 'unique run'):
                    verify_execution(receipt, elf, fixture, console, prefix)


if __name__ == '__main__': unittest.main()
