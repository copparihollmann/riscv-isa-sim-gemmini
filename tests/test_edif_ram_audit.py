"""Physical INIT evidence requires complete instances and real hierarchy paths."""
import io
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'hardware'))
from edif_ram_audit import expression,hierarchy_paths,ram_instance,scan


def instance(nonzero=False,missing=None):
    props=['  (property RTL_RAM_NAME (string "ShuttleDCacheMSHRFile/mshrs_3/rpq/ram_flattened_reg"))']
    for letter in'ABCDEFGH':
        if letter!=missing:props.append('  (property INIT_'+letter+' (string "64\'h'+('1'if nonzero and letter=='C'else'0')+'"))')
    return '\n'.join(['(instance ram (viewref netlist (cellref RAM32M16 (libraryref hdi_primitives)))',*props,')'])


def source(include_tile=True):
    text='''(edif toy
 (Library hdi_primitives
  (cell RAM32M16 (celltype GENERIC))
 )
 (Library work
  (cell Empty (celltype GENERIC))
  (cell Queue16
   (view netlist (contents
'''
    text+='\n'.join('    '+line for line in instance().splitlines())+'\n'
    text+='''   ))
  )
  (cell Tile
   (view netlist (contents
    (instance rpq (viewref netlist (cellref Queue16 (libraryref work))))
   ))
  )
  (cell Top
   (view netlist (contents
    (instance unrelated (viewref netlist (cellref Empty (libraryref work))))
'''
    if include_tile:
        text+='    (instance hart0 (viewref netlist (cellref Tile (libraryref work))))\n'
        text+='    (instance hart1 (viewref netlist (cellref Tile (libraryref work))))\n'
    text+='''   ))
  )
 )
 (design toy
  (cellref Top (libraryref work))
 )
)
'''
    return text.encode()


class RamAuditTests(unittest.TestCase):
    def test_inline_instances_do_not_hide_next_hierarchy_edge(self):
        result=scan(io.BytesIO(source()));record=result['instances'][0]
        self.assertEqual(record['cell_instance_paths'],[['hart0','rpq'],['hart1','rpq']])
        self.assertEqual(result['RPQ_property_count'],1)
        self.assertTrue(record['all_RAM32M16_INIT_parameters_explicit'])
        self.assertTrue(record['all_explicit_INIT_values_zero'])
        self.assertFalse(record['logical_RTL_cmd_INIT_certified'])
        self.assertFalse(record['loaded_FPGA_INIT_certified'])

    def test_unreachable_same_named_memory_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'unreachable'):scan(io.BytesIO(source(False)))

    def test_nonzero_or_missing_init_is_not_reported_as_complete_zero(self):
        nonzero=ram_instance(instance(True),('work','Queue'),1,20)
        self.assertFalse(nonzero['all_explicit_INIT_values_zero'])
        partial=ram_instance(instance(missing='H'),('work','Queue'),1,20)
        self.assertFalse(partial['all_RAM32M16_INIT_parameters_explicit'])

    def test_unknown_width_overflow_duplicate_properties_and_truncated_instances_refuse(self):
        text=instance()
        invalid=[text.replace("64'h0","64'hx",1),text.replace("64'h0","1'h2",1),text[:-1],
            text.replace('  (property INIT_A', '  (property INIT_H',1)]
        for changed in invalid:
            with self.subTest(changed=changed[:60]),self.assertRaises(ValueError):ram_instance(changed,('work','Queue'),1,20)

    def test_quote_parentheses_and_keyword_case_preserve_source_properties(self):
        node=expression('(INSTANCE (rename x "x(y)") (PROPERTY INIT (STRING "1\'b0")))')
        self.assertEqual(node,['instance',['rename','x','x(y)'],['property','INIT',['string',"1'b0"]]])

    def test_recursive_hierarchy_refuses(self):
        with self.assertRaisesRegex(ValueError,'Recursive'):
            hierarchy_paths(('work','Top'),{('work','Top')},{('work','Top'):[('self',('work','Top'))]})


if __name__=='__main__':unittest.main()
