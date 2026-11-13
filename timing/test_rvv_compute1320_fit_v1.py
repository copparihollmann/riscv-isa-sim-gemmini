"""Closed-form/singular numerical controls for the frozen estimator; no labels."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from rvv_compute1320_fit_v1 import rank,nnls,columns
class Estimator(unittest.TestCase):
 def test_exact_identified(self):
  x=[[1,0],[0,1],[1,1],[2,1]];b,r=nnls(x,[2,3,5,7]);self.assertAlmostEqual(b[0],2,places=9);self.assertAlmostEqual(b[1],3,places=9);self.assertTrue(r['converged'])
 def test_negative_target_boundary(self):
  b,r=nnls([[1,0],[0,1],[1,1]],[-2,-3,-5]);self.assertEqual(b,[0,0]);self.assertEqual(r['relative_squared_residual'],38)
 def test_boundary_projection(self):
  # Min (b0-2)^2+(b1+1)^2 under b>=0 => (2,0).
  b,_=nnls([[1,0],[0,1]],[2,-1]);self.assertEqual(b,[2,0])
 def test_singular_design(self):self.assertEqual(rank([[1,2],[2,4],[3,6]]),1)
 def test_independent_scale(self):self.assertEqual(rank([[1e-9,0],[0,1e9],[1e-9,1e9]]),2)
 def test_zero_feature_rows_retained_objective(self):
  b,r=nnls([[1,0],[0,1],[0,0]],[2,3,7]);self.assertEqual(b,[2,3]);self.assertEqual(r['relative_squared_residual'],49)
 def test_predeclared_rowmove_restriction(self):
  self.assertEqual(len(columns('Shuttle')),13);self.assertEqual(len(columns('Rocket')),12);self.assertIn(('vme.row_move','instructions'),columns('Shuttle'));self.assertNotIn(('vme.row_move','work'),columns('Shuttle'));self.assertNotIn(('vme.row_move','instructions'),columns('Rocket'))
if __name__=='__main__':unittest.main()
