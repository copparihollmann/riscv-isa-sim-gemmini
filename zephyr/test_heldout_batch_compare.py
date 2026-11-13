"""Arithmetic/admission fixtures only; these numbers are not RTL ground truth."""
import copy
import unittest
from heldout_batch_compare import compare_regions

def row(cycles,hart=0):
    return {'case_id':'parser.fixture','region':'kernel','hart':hart,'start_cycle':100,'end_cycle':100+cycles,
        'instret_delta':12,'checksum':19,'parent_case_id':'parser.parent'}

class Comparison(unittest.TestCase):
    def test_signed_error_and_boundary(self):
        for model,error,within in [(98,-2,True),(102,2,True),(97,-3,False),(103,3,False),(100,0,True)]:
            result=compare_regions([row(model)],[row(100)])[0]
            self.assertEqual(result['signed_error_percent'],error)
            self.assertEqual(result['within_two_percent'],within)
    def test_each_hart_keeps_its_identity(self):
        result=compare_regions([row(90,1),row(110,0)],[row(100,0),row(100,1)])
        self.assertEqual([(x['hart'],x['signed_error_percent'])for x in result],[(0,10),(1,-10)])
    def test_refusals(self):
        good=row(100)
        for bad in [{**good,'end_cycle':100},{**good,'checksum':True},{**good,'start_cycle':True}]:
            with self.assertRaises(ValueError):compare_regions([bad],[good])
        with self.assertRaises(ValueError):compare_regions([good,good],[good])
        with self.assertRaises(ValueError):compare_regions([row(100,1)],[good])
        with self.assertRaises(ValueError):compare_regions([{**good,'checksum':20}],[good])
        with self.assertRaises(ValueError):compare_regions([{**good,'parent_case_id':'wrong'}],[good])

if __name__=='__main__':unittest.main()
