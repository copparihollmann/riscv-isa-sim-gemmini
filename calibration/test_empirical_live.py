import copy,pathlib,sys,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'timing'))
from empirical_live_features import join
class JoinTests(unittest.TestCase):
 def inputs(self):
  ref=[{'case_id':'a','parent_case_id':'p','hart':0,'partition':'train','family':'dependent','cycles':120,'instret_delta':11,'checksum':'4'}]
  native=[{'case_id':'a','hart':0,'start_cycle':10,'end_cycle':110,'instret_delta':11,'checksum':4,'pass':True}]
  def prefix(seq,val,ret,n):return {'schema':'iris.empirical.prefix.v1','hart':0,'sequence':seq,'value':val,'read_cycle':val+1000,'baseline_cycles':val+1000,'endpoint':'get_csr_before_current_instruction_retirement','retired':ret,'features':{'scalar.integer':{'instructions':n,'work':0,'bytes':0,'macs':0}},'completed_resource_busy_cycles':{'scalar0':n},'memory':{}}
  return ref,native,[prefix(1,10,9,9),prefix(5,110,20,20)]
 def test_exact_boundary_delta(self):
  rows,report=join(*self.inputs());self.assertEqual(rows[0]['native_cycles'],100);self.assertEqual(rows[0]['baseline_cycles'],100);self.assertEqual(rows[0]['features']['scalar.integer']['instructions'],11);self.assertFalse(report['partial'])
 def test_fitted_cost_does_not_claim_baseline(self):
  ref,n,p=self.inputs()
  for x in p:x['baseline_cycles']=None
  rows,_=join(ref,n,p);self.assertIsNone(rows[0]['baseline_cycles']);self.assertEqual(rows[0]['read_cycle_span'],100)
 def test_ambiguous_counter_refuses(self):
  ref,n,p=self.inputs();p.insert(1,copy.deepcopy(p[0]));p[1]['sequence']=2
  with self.assertRaises(ValueError):join(ref,n,p)
 def test_sequence_must_increase(self):
  ref,n,p=self.inputs();p[1]['sequence']=0
  with self.assertRaises(ValueError):join(ref,n,p)
 def test_checksum_refuses(self):
  ref,n,p=self.inputs();n[0]['checksum']=5
  with self.assertRaises(ValueError):join(ref,n,p)
 def test_guest_failure_refuses(self):
  ref,n,p=self.inputs();n[0]['pass']=False
  with self.assertRaises(ValueError):join(ref,n,p)
 def test_cross_hart_boundary_cannot_join(self):
  ref,n,p=self.inputs();p[1]['hart']=1
  with self.assertRaises(ValueError):join(ref,n,p)
 def test_partial_is_explicit(self):
  ref,n,p=self.inputs();rows,r=join(ref,n,p[:1],True);self.assertEqual(rows,[]);self.assertTrue(r['partial']);self.assertEqual(len(r['missing_or_ambiguous_boundaries']),1)
 def test_counter_reversal_refuses(self):
  ref,n,p=self.inputs();p[1]['features']['scalar.integer']['instructions']=1
  with self.assertRaises(ValueError):join(ref,n,p)
 def test_boolean_is_not_an_integer_receipt(self):
  ref,n,p=self.inputs();p[1]['features']['scalar.integer']['instructions']=True
  with self.assertRaises(ValueError):join(ref,n,p)
 def test_boolean_sequence_refuses(self):
  ref,n,p=self.inputs();p[0]['sequence']=True
  with self.assertRaises(ValueError):join(ref,n,p)
 def test_case_id_not_a_runtime_feature_family(self):
  ref,n,p=self.inputs();p[1]['features']['benchmark.case.a']={'instructions':7,'work':0,'bytes':0,'macs':0}
  with self.assertRaises(ValueError):join(ref,n,p)
 def test_golden_cycle_feature_refuses(self):
  ref,n,p=self.inputs();p[1]['features']['scalar.integer']['golden_cycles']=120
  with self.assertRaises(ValueError):join(ref,n,p)
 def test_duplicate_region_refuses(self):
  ref,n,p=self.inputs();n.append(copy.deepcopy(n[0]))
  with self.assertRaises(ValueError):join(ref,n,p)
 def test_repeated_absolute_counter_origins_only_join_evidence(self):
  ref,n,p=self.inputs();original,_=join(ref,n,p)
  for x in p:x['value']+=999000;x['read_cycle']+=123000;x['baseline_cycles']+=123000
  n[0]['start_cycle']+=999000;n[0]['end_cycle']+=999000
  shifted,_=join(ref,n,p);self.assertEqual(original[0]['features'],shifted[0]['features']);self.assertEqual(original[0]['native_cycles'],shifted[0]['native_cycles'])
if __name__=='__main__':unittest.main()
