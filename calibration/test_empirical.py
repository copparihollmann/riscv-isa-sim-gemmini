import copy, importlib.util, json, pathlib, sys, unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'timing'))
import empirical_fit as fit
import empirical_stream_fit as stream

class EmpiricalTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.rows=[json.loads(s) for s in (ROOT/'calibration/empirical-v1/observations.jsonl').read_text().splitlines()]
  cls.params=json.loads((ROOT/'calibration/empirical-v1/parameters.json').read_text())
 def row(self,suite,family):return copy.deepcopy(next(r for r in self.rows if r['suite']==suite and r['family']==family))
 def test_validation_labels_cannot_change_fit(self):
  rows=copy.deepcopy(self.rows)
  for r in rows:
   if r['partition']!='train':r['cycles']=10**30;r['instret_delta']=10**30
  self.assertEqual(fit.fit(rows),self.params['region_models'])
 def test_names_and_trials_are_not_features(self):
  r=self.row('distribution','vector_int');before=fit.model_features(r)
  r.update(case_id='arbitrary',parent_case_id='anything',trial_id=999,start_cycle=10**50,end_cycle=10**50+100)
  self.assertEqual(before,fit.model_features(r))
 def test_hart_clock_origins_not_used(self):
  r=self.row('memory','route_read');before=fit.model_features(r)
  r['start_cycle']+=100000000000;r['end_cycle']+=100000000000
  self.assertEqual(before,fit.model_features(r))
 def test_local_tcm_route_is_per_hart(self):
  r=self.row('memory','route_chase');r['metadata']['target_region']='tcm0';r['hart']=0
  self.assertIn('/local_tcm/',fit.model_features(r)[0]);r['hart']=1
  self.assertIn('/remote_tcm/',fit.model_features(r)[0]);r['hart']=2
  self.assertIn('/remote_tcm/',fit.model_features(r)[0])
 def test_vector_beats_follow_dlen_not_sew(self):
  r=self.row('distribution','vector_int');r['metadata'].update(n=8,lmul=4,mode=0);r['hart']=0
  self.assertEqual(fit.model_features(r)[2]['dlen_beats'],64);r['hart']=2
  self.assertEqual(fit.model_features(r)[2]['dlen_beats'],32)
 def test_two_streams_not_two_chains(self):
  r=self.row('distribution','vector_int');r['metadata'].update(n=8,lmul=1,mode=1)
  x=fit.model_features(r)[2];self.assertEqual(x['operations'],16);self.assertEqual(x['dependent_operations'],0)
 def test_vme_work_includes_k_and_tiles(self):
  r=self.row('distribution','vme_int');r['metadata'].update(n=7,tk=4,tiles=4)
  x=fit.model_features(r)[2];self.assertEqual(x['operations'],28);self.assertEqual(x['k_steps'],112);self.assertEqual(x['drain_tiles'],4)
 def test_functional_refusal_not_timing_fit(self):
  self.assertIsNone(fit.model_features(self.row('distribution','vme_refusal')))
 def test_unsupported_family_not_silently_predicted(self):
  self.assertIsNone(fit.predict(self.row('distribution','pipeline'),self.params['region_models']))
 def test_unknown_precision_not_defaulted(self):
  r=self.row('distribution','scalar_fp');r['metadata']['sew']=128
  self.assertIsNone(fit.predict(r,self.params['region_models']))
 def test_rank_deficient_policy_explicit(self):
  m=self.params['region_models']['vector/rocket/fp16'];self.assertLess(m['feature_rank'],m['feature_columns']);self.assertFalse(m['individual_coefficients_identifiable'])
 def test_runtime_not_physical_miss_claim(self):
  x=self.params['runtime_parameters']['memory']['shuttle']['dram']['chase']['physical_miss_latency_cycles'];self.assertIsNone(x['value']);self.assertEqual(x['status'],'not_identifiable')
 def test_parameter_guesses_do_not_set_certification(self):
  for k in ('full_2pct_certified','source_image_association_verified','rtl_certified','empirical_quality_accepted'):self.assertFalse(self.params[k])
 def test_stream_proxy_rejects_writer_and_other_kernels(self):
  r=self.row('distribution','memory');r['metadata']['mode']=4;self.assertIsNone(stream.features(r));self.assertIsNone(stream.features(self.row('memory','route_read')))
 def test_stream_no_trial_feature(self):
  r=self.row('distribution','memory');r['metadata']['mode']=0;x=stream.features(r);r['trial_id']=999;self.assertEqual(x,stream.features(r))
 def test_stream_warm_history_is_only_proxy(self):
  r=self.row('distribution','memory');r['metadata'].update(mode=0,n=2,bytes=4096,protocol=1);self.assertEqual(stream.features(r)[1]['outer_miss_lines'],0)
  r['metadata']['protocol']=2;self.assertEqual(stream.features(r)[1]['outer_miss_lines'],64)

if __name__=='__main__':unittest.main()
