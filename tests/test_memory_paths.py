import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('memory_paths_audit', ROOT / 'hardware/memory_paths.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class MemoryEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / 'hardware/memory-paths.json').read_text())

    def test_complete_source_audit_keeps_measurements_unavailable(self):
        result = audit.validate(self.data)
        self.assertEqual(result['route_count'], 36)
        self.assertFalse(result['calibrated'])
        self.assertFalse(result['deployed_image_association_verified'])

    def test_missing_hart2_memory_route_is_rejected(self):
        data = copy.deepcopy(self.data)
        data['routes'] = [row for row in data['routes'] if row['id'] != 'hart2.vector_data.dram']
        with self.assertRaisesRegex(ValueError, 'per-hart memory route'):
            audit.validate(data)

    def test_corrupt_elaboration_snapshot_digest_is_rejected(self):
        data = copy.deepcopy(self.data)
        data['sources']['graph0']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            audit.validate(data)

    def test_structural_audit_cannot_claim_calibration_or_image_match(self):
        for field in ('calibrated', 'deployed_image_association_verified'):
            data = copy.deepcopy(self.data)
            data[field] = True
            with self.assertRaisesRegex(ValueError, 'cannot certify'):
                audit.validate(data)

    def test_default_endpoint_value_cannot_become_fitted_latency(self):
        data = copy.deepcopy(self.data)
        data['unmeasured_timing_parameters']['selected_fased_runtime_registers'] = 30
        with self.assertRaisesRegex(ValueError, 'fitted timing'):
            audit.validate(data)

    def test_tampered_benchmark_binding_is_rejected(self):
        data = copy.deepcopy(self.data)
        data['benchmark_input_sha256']['benchmarks/v2/cases.py'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'benchmark input changed'):
            audit.validate(data)


if __name__ == '__main__':
    unittest.main()
