"""Actual staged package, generic Merlin hook and typed tamper controls."""
import copy
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
PACKAGE=Path(os.environ.get('IRIS_SDK4_PACKAGE',str(ROOT/'build/combined-sdk4-package-v2'))).resolve()
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

class ProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider=module('staged_sdk4_provider',PACKAGE/'provider.py')
        cls.provenance=json.loads((PACKAGE/'provenance.json').read_text())

    def test_full_model_remains_unavailable(self):
        value=self.provider.device_simulator(unit='saturn_vme',config='IrisConfig')
        self.assertFalse(value['available']);self.assertIsNone(value['binary'])

    def test_explicit_functional_pair_and_metadata_are_complete(self):
        value=self.provider.experimental_functional_simulator()
        self.assertTrue(value['available'],value.get('reason'));self.assertEqual(value['native_device_abi'],4)
        self.assertEqual(value['matrix_hart_ids'],[0,1]);self.assertFalse(value['timing_available'])
        self.assertEqual(value['binary'],str(PACKAGE/'launch.py'))
        self.assertEqual(value['native_binary_sha256'],self.provider.BINARY)
        self.assertFalse(value['rtl_certified']);self.assertFalse(value['zephyr_smp_certified'])
        self.assertEqual(value['provenance']['per_hart']['2']['dlen_bits'],256)
        self.assertEqual(value['provenance']['evidence']['local_groups'],19)

    def test_metadata_cannot_claim_wrong_hart_layout_or_certification(self):
        original=self.provider.load
        for change in ['hart2isa','hart2matrix','dlen','abi','certified']:
            data=copy.deepcopy(self.provenance)
            if change=='hart2isa':data['launch_isa']['2']=self.provider.COMPUTE
            elif change=='hart2matrix':data['per_hart']['2']['matrix_unit']=True
            elif change=='dlen':data['per_hart']['0']['dlen_bits']=256
            elif change=='abi':data['native_device_abi']=3
            else:data['timing_calibrated']=True
            with self.subTest(change=change),patch.object(self.provider,'load',side_effect=lambda name:data if name=='provenance.json'else original(name)):
                self.assertFalse(self.provider.experimental_functional_simulator()['available'])

    def altered_file(self,name):
        original=self.provider.local
        with tempfile.TemporaryDirectory()as temporary:
            changed=Path(temporary)/'changed';changed.write_bytes(b'changed ordinary fixture')
            with patch.object(self.provider,'local',side_effect=lambda key:changed if key==name else original(key)):
                value=self.provider.experimental_functional_simulator()
        self.assertFalse(value['available']);self.assertIn('changed',value['reason'].lower())

    def test_binary_tamper_refuses_without_launch(self):self.altered_file('bin/spike')
    def test_uart_tamper_refuses_without_launch(self):self.altered_file('bin/libsifive_uart.so')
    def test_launcher_tamper_refuses_without_launch(self):self.altered_file('launch.py')
    def test_sdk_source_tamper_refuses(self):self.altered_file('source/third_party/riscv-isa-sim-combined/riscv/simif.h')
    def test_proof_object_tamper_refuses(self):
        manifest=json.loads((PACKAGE/'evidence/combined/manifest.json').read_text())
        self.altered_file('evidence/combined/'+next(iter(manifest['files'].values()))['object'])

    def test_path_escape_is_not_a_package_input(self):
        with self.assertRaisesRegex(ValueError,'outside closure'):self.provider.local('../outside')

    def test_both_fresh_builds_are_identical_and_packaged_builder_is_not_primary(self):
        for name in ['rebuild.json','packaged-rebuild.json']:
            value=json.loads((PACKAGE/'evidence'/name).read_text())
            self.assertTrue(value['binary_byte_identical']);self.assertTrue(value['uart_byte_identical'])
            self.assertEqual(value['source_overlay_sha256'],self.provider.OVERLAY)
            self.assertFalse(value['primary_modified'])
        value=json.loads((PACKAGE/'evidence/packaged-rebuild.json').read_text())
        self.assertEqual(value['source_mode'],'packaged_source_snapshot')

    def test_existing_sdk_mismatch_controls_refuse_with_packaged_pair(self):
        proof=json.loads((ROOT/'build/combined-sdk/results.json').read_text())
        rows=[]
        for item in proof['rows']:
            argv=[str(PACKAGE/'bin/spike')if word==str(ROOT/'build/spike-combined/spike')
                  else '--extlib='+str(PACKAGE/'bin/libsifive_uart.so')if word=='--extlib='+str(ROOT/'build/spike-combined/libsifive_uart.so')
                  else word for word in item['argv']]
            result=subprocess.run(argv,capture_output=True,timeout=20)
            self.assertNotEqual(result.returncode,0);self.assertIn(b'iris_device_clock_abi_',result.stderr)
            rows.append({'name':item['name'],'argv':argv,'exit_status':result.returncode,
                'raw_stdout':result.stdout,'raw_stderr':result.stderr})
        self.assertEqual(len(rows),4)
        type(self).sdk_rows=rows

class MerlinContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter=module('sdk4_oot_adapter',ROOT/'integration/iris-mlir/simulator.py')
        cls.backend=module('sdk4_merlin_backend',ROOT/'integration/merlin/src/merlin/runtime/backends/device_simulator.py')

    def settings(self):return patch.dict(os.environ,MERLIN_IRIS_MODEL_MANIFEST=str(PACKAGE/'merlin-manifest.json'),MERLIN_IRIS_ALLOW_EXPERIMENTAL_FUNCTIONAL='1',MERLIN_IRIS_TIMING='off')
    def matrix(self):return types.SimpleNamespace(unit='saturn_vme',config='IrisConfig',provider=lambda:types.SimpleNamespace(device_simulator=self.adapter.device_simulator))

    def test_existing_oot_requires_explicit_optin(self):
        with self.settings(),patch.dict(os.environ,MERLIN_IRIS_ALLOW_EXPERIMENTAL_FUNCTIONAL='0'):
            value=self.adapter.device_simulator(unit='saturn_vme',config='IrisConfig')
        self.assertFalse(value['available']);self.assertIn('requires',value['reason'])

    def test_existing_oot_refuses_timing_claim(self):
        with self.settings(),patch.dict(os.environ,MERLIN_IRIS_TIMING='on'):
            value=self.adapter.device_simulator(unit='saturn_vme',config='IrisConfig')
        self.assertFalse(value['available']);self.assertIn('uncalibrated',value['reason'])

    def test_generic_merlin_hook_executes_shipped_threehart_elf(self):
        with self.settings():
            result=self.backend.run(self.matrix(),PACKAGE/'selftest/smoke.elf',harts=3,active_hart_ids=(0,1),
                isa='rv64gcv_zfh_zvfh_zvl256b_zvbb',memory=(0x80000000,0x100000000),timeout=60)
        self.assertEqual(result['returncode'],0,result['stderr'])
        rows=[json.loads(line.split(b' ',1)[1])for line in result['stdout'].splitlines()if line.startswith(b'IRIS_REGION ')]
        self.assertEqual(len(rows),12);self.assertEqual({row['hart']for row in rows},{0,1,2})
        self.assertTrue(all(row['pass']is True for row in rows))
        self.assertFalse(result['simulator']['timing_available'])
        type(self).merlin_result=result

    def test_matrix_distribution_to_hart2_refuses_before_process(self):
        with self.settings(),patch.object(self.backend.subprocess,'run',side_effect=AssertionError('must not execute')):
            with self.assertRaisesRegex(self.backend.DeviceSimulatorError,'without the selected matrix unit'):
                self.backend.run(self.matrix(),PACKAGE/'selftest/smoke.elf',harts=3,active_hart_ids=(2,),
                    isa='rv64gcv',memory=(0x80000000,0x100000000))

class FatalLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary=tempfile.TemporaryDirectory();cls.root=Path(cls.temporary.name)
        cls.compiler=Path('/scratch/eygao/iris-cy/.conda-env/riscv-tools/bin/riscv64-unknown-elf-gcc')
        cls.launcher=module('packaged_fatal_resolver',PACKAGE/'launch.py')
        cls.provenance=json.loads((PACKAGE/'provenance.json').read_text());cls.rows=[];cls.elves=[];cls.compile_commands=[]
        source=cls.root/'fatal.S';source.write_text('''\n.section .text.init\n.global _start\n_start:\n csrr t0,mhartid\n li t1,HART\n bne t0,t1,park\n j z_fatal_error\npark:\n wfi\n j park\n.global z_fatal_error\n.type z_fatal_error,@function\nz_fatal_error:\n j z_fatal_error\n.section .tohost,"aw",@progbits\n.balign 64\n.global tohost\ntohost: .dword 0\n.global fromhost\nfromhost: .dword 0\n''')
        linker=cls.root/'guest.ld';linker.write_text('OUTPUT_ARCH(riscv)\nENTRY(_start)\nSECTIONS { . = 0x80000000; .text : { *(.text.init) *(.text*) } .tohost : ALIGN(64) { *(.tohost) } }\n')
        for hart in range(3):
            elf=cls.root/('fatal'+str(hart)+'.elf');command=[str(cls.compiler),'-march=rv64gc_zicsr','-mabi=lp64d','-nostdlib','-static',
                '-Wl,--build-id=none,--no-relax','-DHART='+str(hart),'-T',str(linker),str(source),'-o',str(elf)]
            result=subprocess.run(command,capture_output=True);assert result.returncode==0,result.stderr
            cls.elves.append(elf);cls.compile_commands.append(command)
        cls.fixture_source=source.read_bytes();cls.fixture_linker=linker.read_bytes()

    @classmethod
    def tearDownClass(cls):cls.temporary.cleanup()

    def arguments(self,elf):
        return ['--iris-vme','--isa='+self.provenance['launch_isa']['2'],'-p3',
            '-m0x70000000:0x40000,0x80000000:0x100000000,0x580000000:0x20000',
            '--dtb='+str(PACKAGE/'board/iris.dtb'),
            *['--hart-isa='+str(h)+':'+self.provenance['launch_isa'][str(h)]for h in range(3)],str(elf)]

    def test_automatic_elf_fatal_resolution_ends_all_three_harts_with_diagnostics(self):
        environment=dict(os.environ);environment.pop('IRIS_FATAL_PCS',None)
        for hart,elf in enumerate(self.elves):
            with self.subTest(hart=hart):
                argv=[str(PACKAGE/'launch.py'),*self.arguments(elf)]
                result=subprocess.run(argv,capture_output=True,env=environment,timeout=10)
                self.assertNotEqual(result.returncode,0)
                for token in ['IRIS_FATAL','hart='+str(hart),'pc=0x','cause=0x','epc=0x','tval=0x']:
                    self.assertIn(token.encode(),result.stderr)
                self.rows.append({'hart':hart,'argv':argv,'compile_argv':self.compile_commands[hart],
                    'exit_status':result.returncode,'raw_stdout':result.stdout,'raw_stderr':result.stderr,'raw_elf':elf.read_bytes()})

    def test_same_guest_without_fatal_resolution_would_spin(self):
        environment=dict(os.environ);environment.pop('IRIS_FATAL_PCS',None)
        with self.assertRaises(subprocess.TimeoutExpired):
            subprocess.run([str(PACKAGE/'bin/spike'),*self.arguments(self.elves[0])],capture_output=True,env=environment,timeout=0.15)

    def test_malformed_elf_is_refused_before_native_exec(self):
        elf=self.root/'malformed.elf';elf.write_bytes(b'\x7fELF truncated')
        result=subprocess.run([str(PACKAGE/'launch.py'),*self.arguments(elf)],capture_output=True,timeout=10)
        self.assertNotEqual(result.returncode,0);self.assertIn(b'IRIS_LAUNCH_REFUSED',result.stderr)

    def test_stripped_elf_symbol_resolution_is_explicitly_refused(self):
        strip=self.compiler.with_name('riscv64-unknown-elf-strip');elf=self.root/'stripped.elf'
        result=subprocess.run([str(strip),'--strip-all','-o',str(elf),str(self.elves[0])],capture_output=True)
        self.assertEqual(result.returncode,0)
        result=subprocess.run([str(PACKAGE/'launch.py'),*self.arguments(elf)],capture_output=True,timeout=10)
        self.assertNotEqual(result.returncode,0);self.assertIn(b'unstripped ELF symbol table required',result.stderr)

if __name__=='__main__':unittest.main()
