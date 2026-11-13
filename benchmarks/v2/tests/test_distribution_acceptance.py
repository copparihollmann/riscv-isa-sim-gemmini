import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('distribution_acceptance_tested',HERE/'distribution_acceptance.py')
acceptance=importlib.util.module_from_spec(spec);spec.loader.exec_module(acceptance)


def console(corpus,drop_hart=None,assertions=False):
    lines=[]
    for case in corpus['cases']:
        for hart in range(3):
            if not case['mask']&(1<<hart) or hart==drop_hart: continue
            value=case['expected_checksums'][hart]
            lines.append('IRIS_REGION '+json.dumps({'case_id':case['case_id'],'region':'kernel','hart':hart,
                'start_cycle':10,'end_cycle':20,'instret_delta':3,'checksum':value,'expected_checksum':value,'pass':True}))
        if assertions and 'shared_counter_golden' in case:
            value=case['shared_counter_golden']
            lines.append('IRIS_SYNC_ASSERT '+json.dumps({'case_id':case['case_id'],'name':'shared_counter',
                'actual':value,'expected':value,'pass':True}))
    return '\n'.join(lines)+'\nIRIS_BATCH_DONE {"failed":0}\n'


class DistributionAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus=json.loads((HERE/'corpus.json').read_text())
        cls.console=console(cls.corpus)

    def test_all_three_harts_have_positive_work_and_refusal_is_separate(self):
        result=acceptance.audit_distribution(self.console,self.corpus)
        self.assertTrue(all(n>0 for n in result['positive_work_regions_per_hart']))
        self.assertEqual(sum(result['positive_work_regions_per_hart'])+len(result['negative_legality_probes']),result['regions'])
        self.assertEqual(result['negative_legality_probes'][0]['hart'],2)
        self.assertFalse(result['timing_certified'])

    def test_missing_rocket_output_cannot_pass(self):
        with self.assertRaises(ValueError): acceptance.audit_distribution(console(self.corpus,drop_hart=2),self.corpus)

    def test_wrong_hart_output_cannot_pass(self):
        rows=self.console.splitlines()
        for index,line in enumerate(rows):
            if line.startswith('IRIS_REGION ') and '"hart": 2' in line:
                row=json.loads(line.split(' ',1)[1]);row['hart']=0
                rows[index]='IRIS_REGION '+json.dumps(row);break
        with self.assertRaises(ValueError): acceptance.audit_distribution('\n'.join(rows),self.corpus)

    def test_missing_hart2_job_ledger_fails_even_with_complete_console(self):
        data=copy.deepcopy(self.corpus)
        case=next(c for c in data['cases'] if any(j['hart']==2 for j in c['jobs']))
        case['jobs']=[j for j in case['jobs'] if j['hart']!=2]
        with self.assertRaisesRegex(ValueError,'job ledger'): acceptance.audit_distribution(self.console,data)

    def test_missing_dependency_is_not_inferred_from_good_checksums(self):
        data=copy.deepcopy(self.corpus)
        case=next(c for c in data['cases'] if c['kind']=='pipeline')
        case['dependencies']['within_iteration']=[]
        with self.assertRaisesRegex(ValueError,'dependency contract'): acceptance.audit_distribution(self.console,data)

    def test_coherently_relabelled_roles_still_must_match_compiled_route(self):
        data=copy.deepcopy(self.corpus)
        case=next(c for c in data['cases'] if c['kind']=='pipeline')
        jobs={j['role']:j for j in case['jobs']}
        jobs['compute']['role']='consumer';jobs['consumer']['role']='compute'
        case['metadata']['compute_hart'],case['metadata']['consumer_hart']=case['metadata']['consumer_hart'],case['metadata']['compute_hart']
        by_role={j['role']:j['job_id'] for j in case['jobs']}
        case['dependencies']['within_iteration']=[[by_role['producer'],by_role['compute']],[by_role['compute'],by_role['consumer']]]
        case['dependencies']['between_iterations']=[[by_role['consumer'],by_role['producer']]]
        with self.assertRaisesRegex(ValueError,'role/hart mismatch'): acceptance.audit_distribution(self.console,data)

    def test_compiled_case_table_prevents_changed_placement_declarations(self):
        data={'cases':[{'case_id':'case','kind':'dependent','n':64,'mask':1,'sew':32,'lmul':1,'mode':0,'bytes':4096,
                        'protocol':0,'edge':32,'tk':1,'tiles':1,'expected_checksums':[513,513,513]}]}
        table='static const case_t experiments[] = {\n{"case",K_dependent,64,1,32,1,0,4096,0,32,1,1,{513ULL,513ULL,513ULL}}\n};\n'
        acceptance.verify_case_table(data,table)
        data['cases'][0]['mask']=4
        with self.assertRaisesRegex(ValueError,'differs from compiled'): acceptance.verify_case_table(data,table)

    def test_synchronization_covers_all_subsets_and_forced_peer_invalidation(self):
        corpus=acceptance.sync_corpus()
        result=acceptance.validate_sync(console(corpus,assertions=True),corpus)
        self.assertEqual(result['cases'],25);self.assertEqual(result['regions'],45)
        self.assertEqual(result['global_counter_assertions'],11)
        for family in ('lrsc','ipi','fence_messages'):
            self.assertEqual(set(result['families'][family]),set(range(1,8)))
        self.assertEqual(set(result['families']['lrsc_invalidated']),{3,5,6,7})

    def test_missing_global_lrsc_assertions_fail_even_when_local_counts_pass(self):
        corpus=acceptance.sync_corpus()
        with self.assertRaisesRegex(ValueError,'missing global'): acceptance.validate_sync(console(corpus),corpus)

    def test_wrong_global_lrsc_total_is_not_hidden_by_guest_pass(self):
        corpus=acceptance.sync_corpus();lines=console(corpus,assertions=True).splitlines()
        for index,line in enumerate(lines):
            if line.startswith('IRIS_SYNC_ASSERT '):
                row=json.loads(line.split(' ',1)[1]);row['actual']=row['expected']=0
                lines[index]='IRIS_SYNC_ASSERT '+json.dumps(row);break
        with self.assertRaisesRegex(ValueError,'counter mismatch'): acceptance.validate_sync('\n'.join(lines),corpus)

    def test_zephyr_source_review_never_claims_execution(self):
        review=acceptance.zephyr_audit()
        self.assertFalse(review['built']);self.assertFalse(review['executed'])
        self.assertFalse(review['all_three_hart_zephyr_acceptance_passed'])
        self.assertTrue(review['source_sha256'])

    def test_failed_rerun_cannot_leave_a_stale_acceptance_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)
            report=output/'acceptance.json'
            report.write_text('{"acceptance_passed":true}\n')
            with mock.patch('sys.argv',['distribution_acceptance.py','--output',str(output),
                                        '--build',str(output/'missing-build')]):
                with self.assertRaises(FileNotFoundError): acceptance.main()
            result=json.loads(report.read_text())
            self.assertFalse(result['acceptance_passed'])
            self.assertFalse(result['timing_certified'])
            self.assertEqual(result['status'],'in_progress')


if __name__=='__main__': unittest.main()
