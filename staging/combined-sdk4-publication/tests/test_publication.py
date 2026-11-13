"""Versioned defaults plus generic launcher/native/support identity guards."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
CANDIDATE=Path(os.environ.get('IRIS_PUBLICATION_ROOT',ROOT/'build/sdk4-publication-candidate-v3/root')).resolve()
DEPLOY=Path(os.environ.get('IRIS_PUBLICATION_MANIFEST',ROOT/'build/sdk4-publication-gates-v1/default-configure-model-final/manifest.json')).resolve()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

class DefaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.provider=load('publication_primary_provider',CANDIDATE/'spike/provider.py')
    def test_default_full_model_unavailable(self):self.assertFalse(self.provider.device_simulator()['available'])
    def test_native_default_and_fatal_entrypoint_are_distinct(self):
        native=CANDIDATE/'spike/bin/spike-iris-functional';launcher=CANDIDATE/'spike/bin/spike-iris-launch'
        self.assertEqual(native.read_bytes()[:4],b'\x7fELF');self.assertTrue(launcher.read_bytes().startswith(b'#!'))
        self.assertEqual(sha(native),'35901887c93ab80aa92e68aac2f26cefa6cc785ae8251d5dc283471aa97faf5d')
        exports=subprocess.check_output(['nm','-D',str(native)],text=True)
        self.assertIn('iris_device_clock_abi_v4',exports);self.assertNotIn('iris_device_clock_abi_v1',exports)
    def test_explicit_provider_selects_one_release_and_preserves_native_identity(self):
        result=self.provider.experimental_functional_simulator()
        self.assertTrue(result['available'],result.get('reason'));self.assertEqual(result['native_device_abi'],4)
        self.assertEqual(sha(CANDIDATE/'spike/bin/spike-iris-functional'),result['native_binary_sha256'])
        self.assertEqual(sha(CANDIDATE/'spike/bin/spike-iris-launch'),result['binary_sha256'])
        self.assertNotEqual(result['native_binary_sha256'],result['binary_sha256'])
    def test_missing_or_external_current_pointer_refuses(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);(root/'releases').mkdir()
            with patch.object(self.provider,'HERE',root):self.assertFalse(self.provider.experimental_functional_simulator()['available'])
            (root/'current').symlink_to(CANDIDATE/'spike/current',target_is_directory=True)
            with patch.object(self.provider,'HERE',root):self.assertFalse(self.provider.experimental_functional_simulator()['available'])
    def test_sdk_and_canonical_inspection_overlay_match(self):
        header=CANDIDATE/'spike/include/riscv/iris_clocked_device.h'
        self.assertIn('iris_device_clock_abi_v4',header.read_text())
        source=CANDIDATE/'third_party/riscv-isa-sim-current'
        diff=subprocess.check_output(['git','-C',str(source),'diff','--binary','HEAD'])
        self.assertEqual(hashlib.sha256(diff).hexdigest(),'e33269e90102a8a9137473eb4d6a0c7c276a2553972ab4e668ab62f041a82060')
        for name in ['riscv/processor.h','riscv/vector_unit.h','riscv/simif.h','riscv/csrs.cc']:
            self.assertEqual(sha(source/name),sha(CANDIDATE/'spike/source'/name))
    def test_old_provenance_schema_cannot_become_current(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);release=root/'releases/legacy';release.mkdir(parents=True);(root/'current').symlink_to('releases/legacy',target_is_directory=True)
            (release/'provenance.json').write_text('{"schema":"old-abi1"}')
            with patch.object(self.provider,'HERE',root):self.assertFalse(self.provider.experimental_functional_simulator()['available'])
    def test_changed_compatibility_sdk_refuses_before_provider_import(self):
        with tempfile.TemporaryDirectory()as temporary:
            root=Path(temporary);release=root/'releases/fixture';release.mkdir(parents=True)
            (root/'current').symlink_to('releases/fixture',target_is_directory=True)
            current=(CANDIDATE/'spike/current').resolve()
            for name in ['provider.py','provenance.json']:(release/name).write_bytes((current/name).read_bytes())
            (release/'compat-sdk').mkdir();(release/'compat-sdk/library').write_bytes(b'changed library fixture')
            (release/'publication-inputs.json').write_text(json.dumps({'schema':'iris.primary_sdk4.release_views.v1',
                'input_sha256':{'compat-sdk/library':hashlib.sha256(b'previous library').hexdigest()}}))
            with patch.object(self.provider,'HERE',root):value=self.provider.experimental_functional_simulator()
            self.assertFalse(value['available']);self.assertIn('SDK/source view changed',value['reason'])

class GenericIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.backend=load('publication_generic_backend',CANDIDATE/'integration/merlin/src/merlin/runtime/backends/device_simulator.py')
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup);self.root=Path(self.temporary.name)
        self.launcher=self.root/'launcher';self.launcher.write_text('#!/usr/bin/env python3\nprint("OUT")\n');self.launcher.chmod(0o755)
        self.native=self.root/'native';self.native.write_bytes(b'native fixture')
        self.support=self.root/'support';self.support.write_bytes(b'UART fixture')
        self.elf=self.root/'guest';self.elf.write_bytes(b'ELF fixture')
        self.descriptor={'available':True,'binary':str(self.launcher),'binary_sha256':sha(self.launcher),
            'native_binary':str(self.native),'native_binary_sha256':sha(self.native),'isa_extensions':[],
            'provenance':{'scope':'local fake executable; not model evidence'},'execution_input_sha256':{str(self.support):sha(self.support)}}
    def matrix(self):return types.SimpleNamespace(unit='u',config='c',provider=lambda:types.SimpleNamespace(device_simulator=lambda **kw:self.descriptor))
    def run_guest(self):return self.backend.run(self.matrix(),self.elf,harts=1,isa='rv64gc',memory=(0x80000000,4096))
    def test_native_and_support_are_validated_with_launcher(self):
        result=self.run_guest();self.assertEqual(result['returncode'],0)
        self.assertEqual(result['execution_input_sha256'][str(self.native)],sha(self.native))
        self.assertEqual(result['execution_input_sha256'][str(self.support)],sha(self.support))
    def test_native_mismatch_refuses_before_any_process(self):
        self.native.write_bytes(b'changed')
        with patch.object(self.backend.subprocess,'run',side_effect=AssertionError('must not execute')):
            with self.assertRaisesRegex(self.backend.DeviceSimulatorError,'missing or changed'):self.run_guest()
    def test_native_mutation_during_guest_is_rejected(self):
        self.launcher.write_text('#!/usr/bin/env python3\nfrom pathlib import Path\nPath('+repr(str(self.native))+').write_bytes(b"changed")\n')
        self.descriptor['binary_sha256']=sha(self.launcher)
        with self.assertRaisesRegex(self.backend.DeviceSimulatorError,'changed during run'):self.run_guest()
    def test_support_mutation_during_guest_is_rejected(self):
        self.launcher.write_text('#!/usr/bin/env python3\nfrom pathlib import Path\nPath('+repr(str(self.support))+').write_bytes(b"changed")\n')
        self.descriptor['binary_sha256']=sha(self.launcher)
        with self.assertRaisesRegex(self.backend.DeviceSimulatorError,'changed during run'):self.run_guest()
    def test_conflicting_input_digest_refuses(self):
        self.descriptor['execution_input_sha256'][str(self.native)]='0'*64
        with self.assertRaisesRegex(self.backend.DeviceSimulatorError,'conflicting'):self.run_guest()
    def test_legacy_native_only_descriptor_retains_contract(self):
        self.descriptor.pop('native_binary');self.descriptor.pop('native_binary_sha256');self.descriptor.pop('execution_input_sha256')
        self.assertEqual(self.run_guest()['returncode'],0)

class ExistingOotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter=load('publication_oot_adapter',CANDIDATE/'integration/iris-mlir/simulator.py')
        cls.backend=load('publication_oot_backend',CANDIDATE/'integration/merlin/src/merlin/runtime/backends/device_simulator.py')
    def settings(self):return patch.dict(os.environ,MERLIN_IRIS_MODEL_MANIFEST=str(DEPLOY),MERLIN_IRIS_ALLOW_EXPERIMENTAL_FUNCTIONAL='1',MERLIN_IRIS_TIMING='off')
    def matrix(self):return types.SimpleNamespace(unit='saturn_vme',config='IrisConfig',provider=lambda:types.SimpleNamespace(device_simulator=self.adapter.device_simulator))
    def test_old_configure_command_emits_both_input_identities(self):
        manifest=json.loads(DEPLOY.read_text());self.assertNotEqual(manifest['binary_sha256'],manifest['native_binary_sha256'])
        self.assertIn(manifest['native_binary'],manifest['input_sha256'])
        with self.settings():value=self.adapter.device_simulator(unit='saturn_vme',config='IrisConfig')
        self.assertTrue(value['available'],value.get('reason'));self.assertEqual(value['native_device_abi'],4)
        self.assertEqual(value['execution_input_sha256'][value['native_binary']],value['native_binary_sha256'])
    def test_existing_generic_hook_runs_real_threehart_smoke(self):
        with self.settings():result=self.backend.run(self.matrix(),CANDIDATE/'benchmarks/build/smoke.elf',harts=3,active_hart_ids=(0,1),
            isa='rv64gcv_zfh_zvfh_zvl256b_zvbb',memory=(0x80000000,0x100000000),timeout=60)
        self.assertEqual(result['returncode'],0,result['stderr'])
        rows=[json.loads(line.split(b' ',1)[1])for line in result['stdout'].splitlines()if line.startswith(b'IRIS_REGION ')]
        self.assertEqual(len(rows),12);self.assertEqual({row['hart']for row in rows},{0,1,2})
        self.assertFalse(result['simulator']['timing_available']);type(self).result=result
    def test_manifest_native_identity_tamper_refuses(self):
        manifest=json.loads(DEPLOY.read_text());manifest['native_binary_sha256']='0'*64
        with tempfile.TemporaryDirectory()as temporary:
            path=Path(temporary)/'bad.json';path.write_text(json.dumps(manifest))
            with self.settings(),patch.dict(os.environ,MERLIN_IRIS_MODEL_MANIFEST=str(path)):
                value=self.adapter.device_simulator(unit='saturn_vme',config='IrisConfig')
        self.assertFalse(value['available']);self.assertIn('native identity',value['reason'])

if __name__=='__main__':unittest.main()
