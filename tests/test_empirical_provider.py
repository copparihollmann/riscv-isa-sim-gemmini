"""Admission/tamper controls, not evidence of a real fitted package."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

from spike.empirical_provider import experimental_empirical_simulator, runtime_binding_inputs, sha


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.inputs = {}
        def put(name, value):
            path = self.root / name
            path.write_text(json.dumps(value) if not isinstance(value, str) else value)
            self.inputs[str(path)] = sha(path)
            return path
        self.native = put('spike', 'unit-test-native-placeholder')
        self.uart = put('uart.so', 'unit-test-uart-placeholder')
        self.provider = put('provider.py', 'unit-test-only')
        self.fixture = put('timing.fixture', 'empirical_profile experimental-effective-services test-only bounded\n'
            'base_hz 500000000\nrtc_divider 1000\n'
            'counter_policy source-ungated-stall\nhart 0 1 source\nhart 1 1 source\nhart 2 1 source\n')
        self.rom = put('boot.rom', 'unit-test-boot'); self.dtb = put('board.dtb', 'unit-test-dtb')
        params = put('parameters.json', {'actual_parameter_fit_performed': True, 'full_2pct_certified': False})
        fit = put('fit.json', {'full_2pct_certified': False})
        self.binding = put('binding.json', {'schema': 'iris.empirical_runtime_binding.v1',
            'actual_parameter_fit_performed': True, 'global_heldout_timings_consumed': False,
            'native_binary_sha256': sha(self.native), 'uart_library_sha256': sha(self.uart),
            'fixture_sha256': sha(self.fixture), 'parameters_sha256': sha(params),
            'fit_report_sha256': sha(fit), 'calibration_identity': 'test-only',
            'split': {'training_parent_case_ids': ['train'], 'validation_parent_case_ids': ['cv']}})
        self.test = put('selftest.json', {'schema': 'iris.empirical_package_selftest.v1', 'pass': True,
            'native_binary_sha256': sha(self.native), 'uart_library_sha256': sha(self.uart),
            'fixture_sha256': sha(self.fixture), 'three_harts_numerically_verified': True,
            'modeled_time_sensitivity_verified': True,
            'input_sha256': {str(self.rom): sha(self.rom), str(self.dtb): sha(self.dtb)},
            'runs': [{'argv': ['--hart-isa=0:rv64gcv_zvti8i32mm', '--hart-isa=1:rv64gcv_zvti8i32mm',
                               '--hart-isa=2:rv64gcv']}]})
        closure = put('source-closure.json', {'schema': 'iris.empirical.source_closure_verification.v1',
            'pass': True, 'binary_sha256': sha(self.native), 'uart_sha256': sha(self.uart)})
        self.manifest = {'schema': 'iris.empirical_simulator.v1', 'mode': 'experimental_fpga_empirical',
            'runtime_environment': {name: os.environ.get(name) for name in ('LD_LIBRARY_PATH', 'LD_PRELOAD', 'LD_AUDIT')},
            'input_sha256': self.inputs, 'model_provider': str(self.provider),
            'native_binary': str(self.native), 'binary': str(self.native),
            'native_binary_sha256': sha(self.native), 'binary_sha256': sha(self.native),
            'uart_library': str(self.uart), 'uart_library_sha256': sha(self.uart), 'native_device_abi': 4,
            'per_hart_isa': {'0': 'rv64gcv_zvti8i32mm', '1': 'rv64gcv_zvti8i32mm', '2': 'rv64gcv'},
            'matrix_hart_ids': [0, 1], 'isa_extensions': ['zvti8i32mm'],
            'memory_regions': [[0x70000000, 0x40000], [0x80000000, 0x100000000], [0x580000000, 0x20000]],
            'qualification': {'rtl_certified': False, 'accuracy_2percent_certified': False, 'whole_model_certified': False},
            'calibration_identity': 'test-only', 'timing_scope': 'synthetic admission fixture only',
            'calibration': {'parameters': str(params), 'parameters_sha256': sha(params),
                'fixture': str(self.fixture), 'fixture_sha256': sha(self.fixture),
                'fit_report': str(fit), 'fit_report_sha256': sha(fit),
                'runtime_binding': str(self.binding), 'runtime_binding_sha256': sha(self.binding),
                'reference': {**{f: 'a' * 64 for f in ('image_archive_sha256', 'bitstream_sha256',
                    'driver_sha256', 'capture_archive_sha256')}, 'source_image_association_verified': False}},
            'selftest': {'receipt': str(self.test), 'sha256': sha(self.test)},
            'launch_args': ['--iris-vme', '--device=sifive_uart,0x10020000',
                '--iris-timing-fixture=' + str(self.fixture), '--extlib=' + str(self.uart),
                '--iris-bootrom=' + str(self.rom), '--dtb=' + str(self.dtb)],
            'built_from': {'source_snapshot_verified': True, 'receipt': str(closure),
                           'receipt_sha256': sha(closure)}}
        self.path = self.root / 'manifest.json'

    def tearDown(self): self.temp.cleanup()

    def select(self):
        self.path.write_text(json.dumps(self.manifest))
        return experimental_empirical_simulator(self.path)

    def rebind(self, path, section, hash_field):
        self.inputs[str(path)] = sha(path); self.manifest[section][hash_field] = sha(path)

    def test_explicit_available_remains_experimental(self):
        result = self.select()
        self.assertTrue(result['available'], result)
        self.assertTrue(result['timing_available'])
        self.assertFalse(result['timing_calibrated'])
        self.assertFalse(result['accuracy_2percent_certified'])
        self.assertEqual(result['execution_input_sha256'][str(self.path)], sha(self.path))

    def test_changed_native_uart_fixture_or_fit_refuses(self):
        for name in ('native', 'uart', 'fixture', 'binding'):
            path = getattr(self, name); old = path.read_bytes(); path.write_bytes(old + b' ')
            with self.subTest(name=name): self.assertFalse(self.select()['available'])
            path.write_bytes(old)

    def test_rebound_mismatching_runtime_native_refuses(self):
        value = json.loads(self.binding.read_text()); value['native_binary_sha256'] = '0' * 64
        self.binding.write_text(json.dumps(value)); self.rebind(self.binding, 'calibration', 'runtime_binding_sha256')
        result = self.select(); self.assertFalse(result['available']); self.assertIn('identity mismatch', result['reason'])

    def test_global_holdout_or_overlapping_partitions_refuse(self):
        original = self.binding.read_text()
        for field in ('global_heldout_timings_consumed', 'split'):
            value = json.loads(original)
            if field == 'split': value['split']['validation_parent_case_ids'] = ['train']
            else: value[field] = True
            self.binding.write_text(json.dumps(value)); self.rebind(self.binding, 'calibration', 'runtime_binding_sha256')
            with self.subTest(field=field): self.assertFalse(self.select()['available'])

    def test_hart2_matrix_fake_certification_and_missing_selftest_refuse(self):
        original = copy.deepcopy(self.manifest)
        for change in ('hart2', 'certification', 'sensitivity'):
            self.manifest = copy.deepcopy(original)
            if change == 'hart2': self.manifest['per_hart_isa']['2'] += '_zvti8i32mm'
            elif change == 'certification': self.manifest['qualification']['accuracy_2percent_certified'] = True
            else:
                value = json.loads(self.test.read_text()); value['modeled_time_sensitivity_verified'] = False
                self.test.write_text(json.dumps(value)); self.rebind(self.test, 'selftest', 'sha256')
            with self.subTest(change=change): self.assertFalse(self.select()['available'])

    def test_nonfinite_document_refuses(self):
        for value in ('NaN', 'Infinity', '1e309'):
            self.path.write_text('{"bad":' + value + '}')
            with self.subTest(value=value):
                self.assertFalse(experimental_empirical_simulator(self.path)['available'])

    def test_competing_or_unbound_launch_overrides_refuse(self):
        original = list(self.manifest['launch_args'])
        for value in ('--iris-timing-fixture=/other', '--extlib=/other.so', '--dtb=/other.dtb',
                      '--isa=rv64im', '--hart-isa=2:rv64gcv_zvti8i32mm', '-p1',
                      '-m0x80000000:0x100000000'):
            self.manifest['launch_args'] = original + [value]
            with self.subTest(argument=value): self.assertFalse(self.select()['available'])

    def test_declared_binding_input_must_exist_and_be_in_manifest_closure(self):
        nested = self.root / 'original-fit-packet.json'; nested.write_text('unit-only-original-fit')
        value = json.loads(self.binding.read_text())
        value['input_sha256'] = {str(nested): sha(nested)}
        self.binding.write_text(json.dumps(value)); self.rebind(self.binding, 'calibration', 'runtime_binding_sha256')
        # Existing file with a correct declared hash is still outside the
        # package closure until the publisher propagates its identity.
        self.assertFalse(self.select()['available'])
        self.inputs[str(nested)] = sha(nested)
        self.assertTrue(self.select()['available'])
        nested.unlink()
        self.assertFalse(self.select()['available'])

    def test_tampered_binding_input_refuses_even_when_manifest_is_rebound(self):
        nested = self.root / 'fit-source.txt'; nested.write_text('unit-only-before')
        value = json.loads(self.binding.read_text()); value['input_sha256'] = {str(nested): sha(nested)}
        self.binding.write_text(json.dumps(value)); self.rebind(self.binding, 'calibration', 'runtime_binding_sha256')
        self.inputs[str(nested)] = sha(nested)
        self.assertTrue(self.select()['available'])
        nested.write_text('unit-only-after'); self.inputs[str(nested)] = sha(nested)
        self.assertFalse(self.select()['available'])

    def normalized_binding(self):
        leaf = self.root / 'original-fit-input.txt'; leaf.write_text('unit-only-fit-source')
        original = json.loads(self.binding.read_text())
        original.pop('split')
        original['parent_split_ids'] = {'train': ['train'], 'internal_validation': ['cv']}
        original['input_sha256'] = {str(leaf): sha(leaf)}
        source = self.root / 'original-binding.json'; source.write_text(json.dumps(original))
        normalized = copy.deepcopy(original)
        normalized['split'] = {'training_parent_case_ids': ['train'], 'validation_parent_case_ids': ['cv']}
        # The original's own declared map must propagate transitively even
        # when the normalized packet declares only its original packet.
        normalized['input_sha256'] = {str(source): sha(source)}
        normalized['canonicalization'] = {'source': str(source), 'source_sha256': sha(source),
                                           'parameters_or_model_changed': False}
        return normalized, source, leaf

    def test_normalization_propagates_original_input_map_and_checks_partitions(self):
        normalized, source, leaf = self.normalized_binding()
        expected = {str(source): sha(source), str(leaf): sha(leaf)}
        self.assertEqual(runtime_binding_inputs(normalized), expected)
        self.binding.write_text(json.dumps(normalized)); self.rebind(self.binding, 'calibration', 'runtime_binding_sha256')
        self.inputs.update(expected)
        self.assertTrue(self.select()['available'])
        normalized['split']['validation_parent_case_ids'] = ['other-cv']
        self.binding.write_text(json.dumps(normalized)); self.rebind(self.binding, 'calibration', 'runtime_binding_sha256')
        self.assertFalse(self.select()['available'])

    def test_normalization_missing_or_tampered_original_refuses(self):
        for change in ('missing-declaration', 'changed-original', 'changed-raw-fields', 'changed-original-input'):
            with self.subTest(change=change):
                normalized, source, leaf = self.normalized_binding()
                if change == 'missing-declaration': normalized['input_sha256'] = {}
                elif change == 'changed-original': source.write_text(source.read_text()+' ')
                elif change == 'changed-raw-fields': normalized['calibration_identity'] = 'other'
                else: leaf.write_text('unit-only-tampered-fit-source')
                with self.assertRaises(ValueError): runtime_binding_inputs(normalized)


if __name__ == '__main__': unittest.main()
