"""No hardware labels: exact ownzero rank/math and synthetic refusal controls."""
import copy,json,math,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import rvv_compute_asm_fit_v2 as fit
import emit_rvv_compute_asm_fixture_v2 as emitter
ROOT=Path(__file__).resolve().parents[1];BASIS=ROOT/'build/rvv-compute-asm-C12-basis-v2';ZERO=ROOT/'build/rvv-compute-asm-C12-model-inputs-v1/ownzero.fixture'
class FixedPlan(unittest.TestCase):
 def test_exact_actual_rank13(self):
  r=json.loads((BASIS/'report.json').read_text());m=r['models']['Shuttle'];self.assertEqual((m['rank'],len(m['columns']),m['TRAIN_rows']),(13,13,978));self.assertNotIn('Rocket',r['models'])
 def test_collinear_refusal_basis(self):self.assertEqual(fit.rank([[1,2],[2,4],[3,6]]),1)
 def test_positive_exact_NNLS(self):
  b,r=fit.nnls([[1,0],[0,1],[1,1]],[2,3,5]);self.assertAlmostEqual(b[0],2,places=9);self.assertAlmostEqual(b[1],3,places=9);self.assertTrue(r['converged'])
 def test_negative_targets_not_negative_costs(self):
  b,r=fit.nnls([[1,0],[0,1],[1,1]],[2,-3,-1]);self.assertAlmostEqual(b[0],.5,places=9);self.assertEqual(b[1],0)
 def test_all_negative_remain_residual(self):
  b,r=fit.nnls([[1,0],[0,1],[1,1]],[-1,-2,-3]);self.assertEqual(b,[0,0]);self.assertGreater(r['relative_squared_residual'],0)
 def test_zero_column_refuses(self):
  with self.assertRaises(ValueError):fit.nnls([[1,0],[2,0]],[2,4])
 def proposal(self):
  r=json.loads((BASIS/'report.json').read_text());r['synthetic_counterfactual_only']=True;r['models']['Shuttle']['coefficients']=[0.0]*13;return r
 def apply(self,r,base=None):
  with tempfile.TemporaryDirectory()as td:
   td=Path(td);path=td/'synthetic.json';path.write_text(json.dumps(r));out=td/'mapped';proof=emitter.emit(path,ZERO if base is None else base,out,'synthetic-mapping-no-HW');return proof,(out/'runtime.fixture').read_text()
 def test_mapping_only14eligible_rules(self):
  proof,text=self.apply(self.proposal());self.assertEqual(proof['eligible_rules_written'],14);self.assertTrue(proof['all_other_costs_modes_resources_II_cache_history_and_ISA_unchanged']);self.assertIn('empirical_opu_entry source-VDQ4-IQ3-entry-MM-TK124-COMplus1-v3',text)
 def test_negative_coefficient_refuses(self):
  r=self.proposal();r['models']['Shuttle']['coefficients'][0]=-1
  with self.assertRaises(ValueError):self.apply(r)
 def test_nonfinite_coefficient_refuses(self):
  r=self.proposal();r['models']['Shuttle']['coefficients'][0]=float('inf')
  with self.assertRaises(ValueError):self.apply(r)
 def test_wrong_hart_scope_refuses(self):
  r=self.proposal();r['models']['Shuttle']['harts']=[0,1,2]
  with self.assertRaises(ValueError):self.apply(r)
 def test_wrong_plan_refuses(self):
  r=self.proposal();r['plan_sha256']='0'*64
  with self.assertRaises(ValueError):self.apply(r)
 def test_modified_controller_zero_fixture_refuses(self):
  with tempfile.TemporaryDirectory()as td:
   path=Path(td)/'wrong.fixture';path.write_text(ZERO.read_text().replace('empirical_opu_entry source-VDQ4-IQ3-entry-MM-TK124-COMplus1-v3',''))
   with self.assertRaises(ValueError):self.apply(self.proposal(),path)
 def test_modified_CPU_cost_refuses(self):
  with tempfile.TemporaryDirectory()as td:
   path=Path(td)/'wrong.fixture';path.write_text(ZERO.read_text().replace('trap_cycles 4','trap_cycles 3'))
   with self.assertRaises(ValueError):self.apply(self.proposal(),path)
 def test_rowmove_slope_not_identified(self):self.assertEqual([c for c in fit.columns('Shuttle')if c[0]=='vme.row_move'],[('vme.row_move','instructions')])
if __name__=='__main__':unittest.main()
