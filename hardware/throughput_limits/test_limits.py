#!/usr/bin/env python3
"""Geometry mutation and conditional capacity refusal controls."""
import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import derive as d
ROOT=Path(__file__).resolve().parents[2]
class Limits(unittest.TestCase):
 @classmethod
 def setUpClass(c):
  c.base=ROOT/'build/throughput-limits-source-v3/modules';c.modules={n:{'text':(c.base/(n+'.sv')).read_text()}for n in d.MODULES}
 def mutate_refuse(self,module,old,new):
  x=copy.deepcopy(self.modules);self.assertIn(old,x[module]['text']);x[module]['text']=x[module]['text'].replace(old,new,1)
  with self.assertRaises(ValueError):d.derive_geometry(x)
 def test_actual_geometry(self):
  x=d.derive_geometry(self.modules);self.assertEqual(x['opu_macs_per_accepted_array_edge'],256);self.assertEqual(x['atl_data_bits_by_hart'],[256,256,64])
 def test_removed_cell(self):self.mutate_refuse('OuterProductCluster','OuterProductCell cells_3_3','UnqualifiedCell cells_3_3')
 def test_removed_cluster(self):self.mutate_refuse('OuterProductUnit','OuterProductCluster clusters_0_0','UnqualifiedCluster clusters_0_0')
 def test_changed_fp_depth(self):self.mutate_refuse('ShuttleFPPipe','FPUFMAPipe_l4_f32','FPUFMAPipe_l3_f32')
 def test_changed_fp8_history(self):self.mutate_refuse('OuterProductSequencer','reg [1:0] fp8_hist_valid;','reg [0:0] fp8_hist_valid;')
 def test_changed_integer_width(self):self.mutate_refuse('AdderArray','output [7:0]  io_out_0','output [15:0] io_out_0')
 def test_removed_segmented_block(self):self.mutate_refuse('FPFMAPipe','SegmentedFMAPipe pipe_out_fma_pipe_1','UnknownPipe pipe_out_fma_pipe_1')
 def test_shared_scalar_ready_bypass(self):self.mutate_refuse('SharedScalarElementwiseFPFMA','assign io_stall = ~io_fp_req_ready;','assign io_stall = 0;')
 def test_changed_bus_width(self):self.mutate_refuse('SaturnRocketUnit','output [63:0]  auto_atl_out_a_bits_data','output [255:0] auto_atl_out_a_bits_data')
 def test_shape_bound_exhaustive(self):
  for tm in range(33):
   for tn in range(33):
    for tk in range(5):
     for fp8 in (False,True):
      s=d.shape_schedule(tm,tn,tk,fp8);self.assertEqual(s['macs'],tm*tn*tk);self.assertTrue(all(0<v<=256 for v in s['per_edge_cell_macs']));self.assertEqual(s['microissues'],((tm+15)//16)*((tn+15)//16)*tk if tm*tn*tk else 0)
      if s['microissues']:self.assertEqual(s['last_result_edge']-s['earliest_issue_edges'][-1],2 if fp8 else 0)
 def test_fp8_same_entry_counterexample(self):
  x=d.shape_schedule(16,16,4,True);self.assertEqual(x['earliest_issue_edges'],[0,3,6,9]);self.assertEqual(d.shape_schedule(32,32,4,True)['earliest_issue_edges'],list(range(16)))
 def test_partial_shape_counterexample(self):self.assertEqual(d.shape_schedule(17,17,1)['per_edge_cell_macs'],[256,16,16,1])
 def test_Rocket_DLEN_is_not_FP_lane_count(self):
  self.assertEqual(d.vector_work_bound(2,'rvv.fp.fadd',16,32,2)['conditional_min_service_edges'],32);self.assertEqual(d.vector_work_bound(0,'rvv.fp.fadd',16,32,2)['conditional_min_service_edges'],4)
 def test_LMUL_does_not_replicate(self):self.assertEqual(d.vector_work_bound(0,'rvv.integer.vadd',8,256,8)['conditional_min_service_edges'],16)
 def test_illegal_and_unproved_queries_refuse(self):
  for thunk in [lambda:d.capacity(2,'vme.fp8'),lambda:d.capacity(2,'rvv.bf16.fma'),lambda:d.capacity(0,'rvv.div'),lambda:d.capacity(True,'scalar.fadd'),lambda:d.capacity(0,'rvv.integer.vadd',128),lambda:d.shape_schedule(33,32,1),lambda:d.shape_schedule(16,16,5),lambda:d.shape_schedule(True,16,1),lambda:d.vector_work_bound(0,'rvv.integer.vadd',8,33,1),lambda:d.vector_work_bound(0,'rvv.integer.vadd',8,4,3)]:
   with self.assertRaises(ValueError):thunk()
if __name__=='__main__':unittest.main(verbosity=2)
