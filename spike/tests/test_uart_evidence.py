"""Do not accept stale bytes, missing clock SDKs or incomplete UART refusals."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE=Path(__file__).resolve().parents[1]/'uart_evidence.py'
spec=importlib.util.spec_from_file_location('uart_evidence_test',MODULE)
uart=importlib.util.module_from_spec(spec);spec.loader.exec_module(uart)

class UartEvidenceTests(unittest.TestCase):
    def put(self,name,data=b'input'):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);return path
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.old=uart.ROOT;uart.ROOT=self.root
        self.binary=self.put('spike/bin/spike-iris-functional',b'native')
        self.plugin=self.put('spike/bin/libsifive_uart.so',b'plugin')
        self.put('spike/iris.patch',b'overlay')
        self.out=self.root/'build/uart-primary';self.out.mkdir(parents=True)
        self.report=self.out/'results.json'
        inputs={}
        for name in ['board/uart-device/plugin.cc','board/uart-device/clocked_uart.hpp','board/iris_uart.hpp',
                     'third_party/riscv-isa-sim/riscv/iris_clocked_device.h','benchmarks/uart_drain.h',
                     'benchmarks/uart_drain.S','board/uart-source-evidence.json',
                     'hardware/evidence/firesim-clocks.freq-summary','hardware/memory-paths.json']:
            p=self.put(name,name.encode());inputs[str(p)]=uart.sha(p)
        self.build={'schema':'iris.uart.primary_build.v1','status':'built_and_unit_passed',
                    'binary_sha256':uart.sha(self.binary),'uart_sha256':uart.sha(self.plugin),
                    'native_device_abi':1,'physical_uart_clock_hz':500000000,'rtc_hz':500000,
                    'input_sha256':inputs,'native_overlay_sha256':uart.sha(self.root/'spike/iris.patch'),
                    'tests':[{'name':name,'pass':True} for name in ['clock','helper']]}
        self.data={'schema':'iris.uart.process_tests.v1','status':'passed_uart_process_cases',
                   'binary_sha256':uart.sha(self.binary),'uart_sha256':uart.sha(self.plugin),
                   'native_plugin_mismatch_refused':True,'mismatch_exit_status':1,'cases':[]}
        for mode,kinds in [(0,['functional','live']),(1,['live','source-clock']),
                           (2,['functional','live']),(3,['functional','live']),
                           (4,['functional','live']),(5,['live']),(6,['live'])]:
            for kind in kinds:
                name=f'mode{mode}-{kind}';elf=self.put(f'build/uart-primary/{name}.elf',name.encode())
                out=(bytes(range(256)) if mode in [0,1] else b'')+f'PASSED UART device mode {mode}'.encode()
                stdout=self.put(f'build/uart-primary/{name}.stdout',b'' if mode==3 else out)
                stderr=self.put(f'build/uart-primary/{name}.stderr',b'IRIS_UART_UNKNOWN_RX_DATA' if mode==3 else b'')
                args=[str(self.binary),'--extlib='+str(self.plugin)]
                row={'name':name,'pass':True,'expected_unknown_refusal':mode==3,'exit_status':1 if mode==3 else 0,
                     'elf_sha256':uart.sha(elf),'stdout_sha256':uart.sha(stdout),'stderr_sha256':uart.sha(stderr),
                     'fixture_sha256':None,'graph_sha256':None}
                if kind!='functional':
                    for flag,key,suffix in [('iris-timing-fixture','fixture_sha256','fixture'),('iris-timing-trace','graph_sha256','graph.json')]:
                        path=self.put(f'build/uart-primary/{name}.{suffix}',name.encode());args.append('--'+flag+'='+str(path));row[key]=uart.sha(path)
                if mode==2:row['frame_stimulus_sha256']=uart.sha(self.put('build/uart-primary/rx.frames',b'frame-boundaries'))
                row['argv']=args+[str(elf)];self.data['cases'].append(row)
        old=self.put('old-native',b'old-native');err=self.put('build/uart-primary/old-native.stderr',b'undefined symbol iris_device_clock_abi_v1')
        self.data.update(mismatch_argv=[str(old)],mismatch_binary_sha256=uart.sha(old),mismatch_stderr_sha256=uart.sha(err))
        self.save()
    def tearDown(self):uart.ROOT=self.old;self.temp.cleanup()
    def save(self):
        p=self.put('spike/device-build.json',json.dumps(self.build).encode())
        self.data['input_sha256']={str(p):uart.sha(p)};self.report.write_text(json.dumps(self.data))
    def result(self):return uart.uart_fixture_evidence(self.binary,self.report)[0]
    def test_complete_pair(self):self.assertTrue(self.result()['tested'])
    def test_stale_native(self):
        self.binary.write_bytes(b'new-native');self.assertFalse(self.result()['tested'])
    def test_stale_sdk(self):
        (self.root/'third_party/riscv-isa-sim/riscv/iris_clocked_device.h').write_bytes(b'changed');self.assertFalse(self.result()['tested'])
    def test_missing_drain_source(self):
        self.build['input_sha256'].pop(str(self.root/'benchmarks/uart_drain.S'));self.save();self.assertFalse(self.result()['tested'])
    def test_wrong_source_clock(self):
        self.build['physical_uart_clock_hz']=60000000;self.save();self.assertFalse(self.result()['tested'])
    def test_duplicate_cannot_replace_missing_case(self):
        self.data['cases'][-1]=self.data['cases'][0];self.save();self.assertFalse(self.result()['tested'])
    def test_unknown_rx_cannot_succeed(self):
        self.data['cases'][6]['exit_status']=0;self.save();self.assertFalse(self.result()['tested'])
    def test_missing_plugin_mismatch(self):
        self.data.pop('mismatch_binary_sha256');self.save();self.assertFalse(self.result()['tested'])
    def test_fifo_byte_order_not_just_pass_marker(self):
        path=self.out/'mode0-functional.stdout';path.write_bytes(b'PASSED UART device mode 0')
        self.data['cases'][0]['stdout_sha256']=uart.sha(path);self.save();self.assertFalse(self.result()['tested'])

if __name__=='__main__':unittest.main()
