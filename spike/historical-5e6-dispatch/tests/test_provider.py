import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE=Path(__file__).resolve().parents[1]/'provider.py'
spec=importlib.util.spec_from_file_location('provider',MODULE)
provider=importlib.util.module_from_spec(spec);spec.loader.exec_module(provider)

class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)/'spike';self.root.mkdir()
        self.old=provider.HERE;provider.HERE=self.root
        self.data={}
    def tearDown(self):
        provider.HERE=self.old;self.temp.cleanup()
    def make(self):
        files=['iris.patch','build.py','provider.py','functional_selftest.cc','decoder_cases.hpp','bin/spike','bin/spike-zvt-reference','bin/libsifive_uart.so','results/case.stdout','results/case.stderr','case.elf']
        for name in files:
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(name.encode())
        hardware=self.root.parent/'hardware/manifest.json';hardware.parent.mkdir();hardware.write_text('{}')
        tests=[]
        for name in ['smoke','batch','batch-seed-1','batch-seed-1-repeat','batch-seed-2','fatal-entry','vme-directed','vme-directed-reference','vme-fused-lm2-gemm-transpose','vme-fused-lm2-gemm-transpose-reference','miles-heldout','miles-heldout-reference','miles-i8-heldout','miles-i8-heldout-reference','hart2-vector-arithmetic','hart2-vector-move','cpu-dtypes','vme-directed-mx','vme-directed-mx-reference','vme-fp8-directed','vme-fp8-directed-reference','vme-fp8-gemm','vme-fp8-gemm-reference','native-fp8','wide-reduce-fp8','ieee-bf16','shared-fpu','fpcomp','bitmanip','cease-capability','cpu_config','csr_config']:
            out=self.root/f'results/{name}.stdout';err=self.root/f'results/{name}.stderr';out.write_bytes(b'ok');err.write_bytes(b'')
            tests.append({'name':name,'argv':[str(self.root/'case.elf')],'elf_sha256':provider._sha(self.root/'case.elf'),'stdout_sha256':provider._sha(out),'stderr_sha256':provider._sha(err),'pass':True})
        self.data={'binary':str(self.root/'bin/spike'),'binary_sha256':provider._sha(self.root/'bin/spike'),'target_patch_sha256':provider._sha(self.root/'iris.patch'),'source_inputs':{name:provider._sha(self.root/name) for name in files[:5]},'external_source_inputs':{},'reference_binary_sha256':provider._sha(self.root/'bin/spike-zvt-reference'),'hardware_manifest_sha256':provider._sha(hardware),'decoder_source_inputs':{},'device_binary_sha256':provider._sha(self.root/'bin/libsifive_uart.so'),'evidence_inputs':{},'selftest':{'fpcomp':{'pass':True,'forms':22,'operation_cases':8448,'handler_executions':12672,'illegal_sew8_cases':132,'generic_semantics_cases':9,'core_priority_cases':6,'vector_config_refusals':2,'source_selected_chunk_flags':True,'mask_tail_checked':True,'source_altfmt_checked':True},'shared_fpu':{'pass':True,'forms':45,'operation_cases':21000,'reduction_cases':1200,'masked_exception_flags':True,'raw_vf_input':True,'vstart_zero_required':True,'fs_dirty_checked':True},'ieee_fma':{'pass':True,'forms':45,'operation_cases':23360,'reduction_cases':1120,'scalar_bf16_illegal_cases':6,'hart2_ieee_flags':True},'native_fp8':{'pass':True,'forms':45,'narrow_cases':20480,'wide_cases':11520,'reduction_cases':640},'handler_results':[{'mode':mode,'functional_handlers':'pass'} for mode in ['upstream-zvt','iris-experimental']],'guest_results':tests}}
        self.data['selftest']['configured_csrs']={'pass':True,'checks':1656,'actual_csr_instructions':2031,'harts':3,'isa_profiles':2,'hardware_hpm_count':0,'generic_preserved':True,'binary_sha256':self.data['binary_sha256'],'overlay_sha256':self.data['target_patch_sha256']}
        self.data['device_implementation']='iris-clocked-uart-source-bound'
        self.data['uart_device_integration']={'tested':True,'process_cases':12,'unknown_rx_refusals':2,'native_device_abi':1,'native_plugin_mismatch_refused':True}
        self.save()
    def save(self): (self.root/'provenance.json').write_text(json.dumps(self.data))
    def test_missing_and_malformed_fail_closed(self):
        self.assertFalse(provider.experimental_functional_simulator()['available'])
        (self.root/'provenance.json').write_text('{')
        self.assertFalse(provider.experimental_functional_simulator()['available'])
        self.assertFalse(provider.device_simulator()['available'])
    def test_valid_experimental_but_full_unavailable(self):
        self.make();self.assertTrue(provider.experimental_functional_simulator()['available']);self.assertFalse(provider.device_simulator()['available'])
    def test_uart_digest_mismatch(self):
        self.make();(self.root/'bin/libsifive_uart.so').write_bytes(b'changed');self.assertFalse(provider.experimental_functional_simulator()['available'])
    def test_missing_uart_clock_or_abi_evidence(self):
        self.make();self.data['uart_device_integration'].pop('native_plugin_mismatch_refused');self.save();self.assertFalse(provider.experimental_functional_simulator()['available'])
    def test_csr_receipt_must_match_native(self):
        self.make();self.data['selftest']['configured_csrs']['binary_sha256']='old';self.save();self.assertFalse(provider.experimental_functional_simulator()['available'])
    def test_csr_source_has_zero_hardware_counters(self):
        self.make();self.data['selftest']['configured_csrs']['hardware_hpm_count']=29;self.save();self.assertFalse(provider.experimental_functional_simulator()['available'])
    def test_failed_duplicate_handler_cannot_hide(self):
        self.make();self.data['selftest']['handler_results'].append({'mode':'iris-experimental','functional_handlers':'fail'});self.save();self.assertFalse(provider.experimental_functional_simulator()['available'])
    def test_truthy_string_is_not_success(self):
        self.make();self.data['selftest']['guest_results'][0]['pass']='false';self.save();self.assertFalse(provider.experimental_functional_simulator()['available'])
    def test_missing_native_oracle_coverage(self):
        self.make();self.data['selftest']['native_fp8']['reduction_cases']=0;self.save();self.assertFalse(provider.experimental_functional_simulator()['available'])
    def test_failed_native_math(self):
        self.make();self.data['selftest']['native_fp8']['pass']=False;self.save();self.assertFalse(provider.experimental_functional_simulator()['available'])
    def test_missing_ieee_policy_coverage(self):
        self.make();self.data['selftest']['ieee_fma']['reduction_cases']=0;self.save();self.assertFalse(provider.experimental_functional_simulator()['available'])
    def test_failed_ieee_policy(self):
        self.make();self.data['selftest']['ieee_fma']['pass']=False;self.save();self.assertFalse(provider.experimental_functional_simulator()['available'])
    def test_missing_shared_masked_flags(self):
        self.make();self.data['selftest']['shared_fpu']['masked_exception_flags']=False;self.save();self.assertFalse(provider.experimental_functional_simulator()['available'])
    def test_missing_shared_reductions(self):
        self.make();self.data['selftest']['shared_fpu']['reduction_cases']=0;self.save();self.assertFalse(provider.experimental_functional_simulator()['available'])
    def test_missing_fpcomp_tail_flags(self):
        self.make();self.data['selftest']['fpcomp']['mask_tail_checked']=False;self.save();self.assertFalse(provider.experimental_functional_simulator()['available'])
    def test_missing_fpcomp_trap_cases(self):
        self.make();self.data['selftest']['fpcomp']['illegal_sew8_cases']=0;self.save();self.assertFalse(provider.experimental_functional_simulator()['available'])
    def test_missing_coverage(self):
        self.make();self.data['selftest']['guest_results'].pop();self.save();self.assertFalse(provider.experimental_functional_simulator()['available'])
    def test_stale_elf(self):
        self.make();(self.root/'case.elf').write_bytes(b'changed');self.assertFalse(provider.experimental_functional_simulator()['available'])

if __name__=='__main__':unittest.main()
