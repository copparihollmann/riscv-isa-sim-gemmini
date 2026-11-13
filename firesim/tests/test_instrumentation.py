import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('iris_observability',Path(__file__).resolve().parents[1]/'inspect_instrumentation.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class InstrumentationInventoryTests(unittest.TestCase):
    def test_writable_latencies_are_not_periodic_counter_samples(self):
        text='''registry.add_widget(new FASEDMemoryTimingModel(
  AddressMap{
    std::vector<std::pair<std::string, uint32_t>>{
      { R"ESC(readLatency)ESC", 4 },
      { R"ESC(totalReads)ESC", 68 },
    },
    std::vector<std::pair<std::string, uint32_t>>{
      { R"ESC(readLatency)ESC", 4 },
    }
  }
#endif'''
        actual=module.fased_registers(text)
        self.assertEqual(actual['periodic_stats_registers'],['totalReads'])
        self.assertFalse(actual['selected_latency_values_in_periodic_stats'])
        self.assertFalse(actual['latency_histogram_data_available'])

    def test_include_or_type_name_is_not_an_instantiated_trace_bridge(self):
        source='#include "bridges/tracerv.h"\nclass autocounter_t;\nregistry.add_widget(new uart_t(\nregistry.add_widget(new clockmodule_t(\n'
        self.assertEqual(module.bridges(source),[{'class':'uart_t','line':3},{'class':'clockmodule_t','line':4}])

    def test_missing_generated_constructor_contract_refuses(self):
        with self.assertRaises(ValueError):
            module.bridges('UARTBRIDGEMODULE_struct;\n// registry.add_widget(new uart_t(\n')

    def test_member_hash_binds_actual_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'image.tar.gz';data=b'actual programmed candidate bytes\0\xff'
            with tarfile.open(path,'w:gz') as archive:
                info=tarfile.TarInfo('platform/firesim.bit');info.size=len(data)
                archive.addfile(info,io.BytesIO(data))
            self.assertEqual(module.inventory(path),[{'name':'platform/firesim.bit','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}])

    def test_link_in_artifact_tar_is_not_treated_as_a_bitstream(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'image.tar'
            with tarfile.open(path,'w') as archive:
                info=tarfile.TarInfo('platform/firesim.bit');info.type=tarfile.SYMTYPE;info.linkname='/elsewhere/image.bit'
                archive.addfile(info)
            with self.assertRaises(ValueError):
                module.inventory(path)


if __name__=='__main__':unittest.main()
