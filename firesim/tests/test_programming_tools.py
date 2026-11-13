"""Pure command-adapter controls; no SSH or programming tool execution."""
import importlib.util
from pathlib import Path
import types
import unittest

spec=importlib.util.spec_from_file_location('program_tools',Path(__file__).parents[1]/'managed_programming_tools.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class ProgrammingToolsTests(unittest.TestCase):
    def test_only_exact_installed_managed_command_gets_explicit_tools(self):
        calls=[];namespace=types.SimpleNamespace(run=lambda *a,**k:calls.append((a,k))or'original-result')
        module.install(namespace)
        command='/usr/local/bin/firesim-fpga-util.py --bitstream-map /private/map --fpga-db /fixed/db'
        self.assertEqual(namespace.run(command,warn_only=False),'original-result')
        self.assertIn('--vivado-bin /tools/xilinx/2026.1/Vivado_Lab/bin/vivado_lab',calls[0][0][0])
        self.assertIn('--hw-server-bin /tools/xilinx/2026.1/Vivado_Lab/bin/hw_server',calls[0][0][0])
        self.assertEqual(calls[0][1],{'warn_only':False})
        for other in ['echo '+command,command+'; echo bad','/usr/local/bin/firesim-load-xdma-module','ordinary']:
            namespace.run(other);self.assertEqual(calls[-1][0][0],other)

    def test_duplicate_install_is_refused(self):
        namespace=types.SimpleNamespace(run=lambda *a,**k:None);module.install(namespace)
        with self.assertRaisesRegex(RuntimeError,'already installed'):module.install(namespace)


if __name__=='__main__':unittest.main()
