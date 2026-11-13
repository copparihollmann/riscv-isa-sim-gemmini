import copy
import importlib.util
import json
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('v2_validation',HERE/'validate.py')
validation=importlib.util.module_from_spec(spec);spec.loader.exec_module(validation)


class V2ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.corpus={'schema_version':2,'cases':[
            {'case_id':'compute','mask':3,'expected_checksums':[17,18,0]},
            {'case_id':'dma','mask':4,'expected_checksums':[0,0,19]}]}
        self.rows=[{'case_id':name,'region':'kernel','hart':hart,'start_cycle':10,'end_cycle':20,
                    'instret_delta':7,'checksum':value,'expected_checksum':value,'pass':True}
                   for name,hart,value in [('compute',0,17),('compute',1,18),('dma',2,19)]]

    def text(self,rows=None,done=0):
        return '\n'.join('IRIS_REGION '+json.dumps(row) for row in (self.rows if rows is None else rows))+\
            '\nIRIS_BATCH_DONE '+json.dumps({'failed':done})+'\n'

    def test_ready_masks_include_compute_and_dma_roles(self):
        self.assertEqual(validation.validate(self.text(),self.corpus)['regions'],3)

    def test_guest_cannot_change_its_own_expected_checksum(self):
        rows=copy.deepcopy(self.rows);rows[0]['checksum']=rows[0]['expected_checksum']=99
        with self.assertRaisesRegex(ValueError,'golden checksum mismatch'):
            validation.validate(self.text(rows),self.corpus)

    def test_missing_or_duplicate_hart_is_rejected(self):
        for rows in (self.rows[:-1],self.rows+[self.rows[0]]):
            with self.subTest(rows=len(rows)),self.assertRaises(ValueError):
                validation.validate(self.text(rows),self.corpus)

    def test_counter_range_and_completion_are_checked(self):
        for field,value in [('hart',True),('start_cycle',-1),('end_cycle',1<<64),('instret_delta',False)]:
            rows=copy.deepcopy(self.rows);rows[0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                validation.validate(self.text(rows),self.corpus)
        with self.assertRaises(ValueError): validation.validate(self.text(done=1),self.corpus)

    def test_completed_functional_run_does_not_certify_timing(self):
        result=validation.validate(self.text(),self.corpus)
        self.assertTrue(result['functional_checks_passed']);self.assertFalse(result['timing_certified'])

    def test_complete_corpus_excludes_pending_and_heldout_cases(self):
        corpus=json.loads((HERE/'corpus.json').read_text())
        self.assertEqual(len(corpus['cases']),208)
        self.assertEqual(corpus['expected_region_count'],432)
        self.assertTrue(all(row['status']=='ready' for row in corpus['cases']))
        self.assertTrue(all(not row['case_id'].startswith(('miles','merlin')) for row in corpus['cases']))
        self.assertTrue(corpus['pending_cases'])

    def test_every_nonempty_subset_has_scalar_vector_and_memory_work(self):
        corpus=json.loads((HERE/'corpus.json').read_text())
        for kind in ('dependent','independent','vector_int','vector_fp','memory','atomic'):
            self.assertEqual({c['mask'] for c in corpus['cases'] if c['kind']==kind},set(range(1,8)),kind)

    def test_all_three_harts_execute_vector_pipeline_compute(self):
        corpus=json.loads((HERE/'corpus.json').read_text())
        pipelines=[c for c in corpus['cases'] if c['kind']=='pipeline']
        self.assertEqual({c['metadata']['compute_hart'] for c in pipelines},{0,1,2})
        for case in pipelines:
            self.assertEqual({j['role'] for j in case['jobs']},{'producer','compute','consumer'})
            self.assertEqual({j['hart'] for j in case['jobs']},{0,1,2})
            self.assertEqual(len(case['dependencies']['within_iteration']),2)

    def test_matrix_jobs_never_route_to_hart2_except_explicit_refusal(self):
        corpus=json.loads((HERE/'corpus.json').read_text())
        for case in corpus['cases']:
            for job in case['jobs']:
                self.assertEqual(job['expected_checksum'],case['expected_checksums'][job['hart']])
                if 'vme' in job['units'] and job['hart']==2:
                    self.assertEqual(case['kind'],'vme_refusal')
                    self.assertEqual(case['metadata']['expected_exception'],'illegal_instruction')
        matrices=[c for c in corpus['cases'] if c['kind']=='pipeline_vme']
        self.assertEqual({c['metadata']['compute_hart'] for c in matrices},{0,1})


if __name__=='__main__': unittest.main()
