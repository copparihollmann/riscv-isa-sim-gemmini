"""Archive and sequencing controls; all hardware calls are mocked."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

FIRESIM = Path(__file__).parents[1]
sys.path.insert(0, str(FIRESIM))
import analyze_campaign as analysis
import run_campaign as campaign
from capture_run import capture


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ArchiveAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name); self.job = self.root / 'job'; self.job.mkdir()
        self.validator = analysis.ROOT / 'benchmarks/campaign/validate.py'
        self.corpus = {'split_id':'iris-broad-fit-campaign-v1', 'trials':2,
                       'cases':[{'case_id':'x.trial.' + str(t), 'parent_case_id':'x', 'trial_id':t,
                                 'suite':'baseline', 'mask':1, 'expected_checksums':[73,0,0]} for t in range(2)]}
        self.rows = [{'case_id':'x.trial.' + str(t), 'parent_case_id':'x', 'trial_id':t, 'suite':'baseline',
                      'hart':0, 'start_cycle':100, 'end_cycle':110+t, 'instret_delta':4,
                      'checksum':73, 'expected_checksum':73, 'pass':True, 'region':'kernel'} for t in range(2)]

    def make(self, bad_guest=False, failed=False, cleanup_copy=False, conflict=False, second_guest=False, perturbed=False):
        (self.job / 'corpus.json').write_text(json.dumps(self.corpus))
        uart = self.job / 'manager/results-workload/private/uartlog'; uart.parent.mkdir(parents=True)
        rows = [dict(row) for row in self.rows]
        if bad_guest:
            rows[0]['checksum'] = 74
        lines = ['IRIS_REGION ' + json.dumps(row) for row in rows]
        lines += ['IRIS_CAMPAIGN_PHASE ' + json.dumps({'suite':s, 'trial_id':t, 'begin':b})
                  for s in ('baseline','distribution','memory') for t in range(2) for b in (True,False)]
        lines += ['IRIS_BATCH_DONE ' + json.dumps({'failed':0,'cases':2,'regions':2,'trials':2})]
        uart.write_text('\n'.join(lines) + '\n')
        if cleanup_copy:
            copied=self.job/'optional-observability/uartlog';copied.parent.mkdir()
            copied.write_bytes(uart.read_bytes()+(b'changed\n' if conflict else b''))
        if second_guest:
            copied=uart.parent.parent/'second/uartlog';copied.parent.mkdir()
            copied.write_bytes(uart.read_bytes())
        manifest = {'status':'failed' if failed else 'completed_uncertified', 'cleanup_status':'passed',
                    'commands':[], 'campaign_role':'fitting', 'corpus_sha256':sha(self.job / 'corpus.json'),
                    'input_sha256':{str(self.validator):sha(self.validator)}, 'capture':{'status':'attempting'}}
        if perturbed:
            manifest.update(timing_perturbed=True, baseline_timing_equivalent=False, diagnostic_variant='fenced_control')
        (self.job / 'run.json').write_text(json.dumps(manifest)); pre = sha(self.job / 'run.json')
        archive = self.root / 'run.tar.gz'; capture(self.job, archive)
        manifest['capture'] = {'status':'captured', 'archive':str(archive), 'archive_sha256':sha(archive),
                               'captured_run_manifest_sha256':pre}
        (self.job / 'run.json').write_text(json.dumps(manifest))
        return archive, manifest

    def test_analysis_reads_archived_guest_and_retains_every_trial(self):
        archive, manifest = self.make()
        # A later editable UART cannot influence the archived result.
        next((self.job / 'manager').rglob('uartlog')).write_text('IRIS_FATAL changed later\n')
        report = analysis.analyze(self.job, self.root / 'analysis')
        self.assertTrue(report['archive_verified']); self.assertTrue(report['managed_run_passed'])
        self.assertEqual([r['cycles'] for r in report['repetitions'][0]['raw_samples']], [10,11])
        self.assertFalse(report['calibration_usable'])

    def test_failed_runner_stays_failed_even_with_complete_guest_rows(self):
        self.make(failed=True)
        report = analysis.analyze(self.job, self.root / 'analysis')
        self.assertTrue(report['functional_checks_passed']); self.assertFalse(report['managed_run_passed'])

    def test_diagnostic_perturbation_survives_archive_analysis(self):
        self.make(perturbed=True)
        report=analysis.analyze(self.job,self.root/'analysis')
        self.assertTrue(report['managed_run_passed'])
        self.assertTrue(report['experiment']['timing_perturbed'])
        self.assertIs(report['experiment']['baseline_timing_equivalent'],False)
        self.assertFalse(report['calibration_usable'])

    def test_identical_owned_cleanup_copy_is_one_guest_not_duplicate_regions(self):
        self.make(cleanup_copy=True)
        report=analysis.analyze(self.job,self.root/'analysis')
        self.assertTrue(report['managed_run_passed'])
        self.assertEqual(len(report['repetitions'][0]['raw_samples']),2)
        self.assertEqual(len(report['guest_uart']['identical_cleanup_copies']),1)

    def test_conflicting_owned_cleanup_console_copy_refuses(self):
        self.make(cleanup_copy=True,conflict=True)
        report=analysis.analyze(self.job,self.root/'analysis')
        self.assertFalse(report['functional_checks_passed'])
        self.assertIn('copies disagree',report['error'])

    def test_two_managed_guest_paths_refuse_even_when_identical(self):
        self.make(second_guest=True)
        report=analysis.analyze(self.job,self.root/'analysis')
        self.assertFalse(report['functional_checks_passed'])
        self.assertIn('Multiple managed guest',report['error'])

    def test_current_manifest_cannot_promote_archived_failure(self):
        archive, manifest = self.make(failed=True)
        manifest['status'] = 'completed_uncertified'
        (self.job / 'run.json').write_text(json.dumps(manifest))
        report = analysis.analyze(self.job, self.root / 'analysis')
        self.assertFalse(report['managed_run_passed'])
        self.assertIn('differs from archived', report['error'])

    def test_independent_checksum_failure_is_not_timing_data(self):
        self.make(bad_guest=True)
        report = analysis.analyze(self.job, self.root / 'analysis')
        self.assertTrue(report['archive_verified']); self.assertFalse(report['functional_checks_passed'])
        self.assertIn('checksum', report['error'])

    def test_archive_tampering_and_uncertain_cleanup_are_explicit(self):
        archive, manifest = self.make(); archive.write_bytes(b'changed bytes')
        report = analysis.analyze(self.job, self.root / 'analysis')
        self.assertIn('SHA256', report['error']); self.assertFalse(report['archive_verified'])
        manifest['capture'] = {'status':'withheld'}; manifest['cleanup_status']='refused_or_failed'
        (self.job / 'run.json').write_text(json.dumps(manifest))
        report = analysis.analyze(self.job, self.root / 'analysis2')
        self.assertFalse(report['archive_verified']); self.assertIn('withheld', report['error'])

    def test_changing_analysis_location_cannot_mutate_frozen_job(self):
        self.make()
        with self.assertRaisesRegex(ValueError, 'outside job'):
            analysis.analyze(self.job, self.job / 'analysis')


class CampaignOrderTests(unittest.TestCase):
    def test_failed_or_unarchived_smoke_never_starts_broad(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); jobs = []
            for name in ('smoke','broad-fit'):
                job = root / name; job.mkdir(); (job / 'run.json').write_text('{}')
                jobs.append({'name':name,'job':str(job),'run_receipt_sha256':sha(job/'run.json'),'elf_sha256':'elf'})
            source = root / 'campaign.json'
            source.write_text(json.dumps({'schema':'iris.managed_batched_campaign.v1','order':['smoke','broad-fit'],'jobs':jobs}))
            def analyze(job, output):
                output.mkdir(); (output/'report.json').write_text('{}'); return {'managed_run_passed':False}
            with patch.object(campaign, 'verify', return_value={'elf_sha256':'elf'}), \
                 patch.object(campaign, 'execute_managed') as execute, patch.object(campaign, 'analyze', side_effect=analyze):
                report = campaign.run(source, root/'analysis', True, 'actual-test-fixture')
            self.assertEqual(execute.call_count, 1)
            self.assertEqual(report['status'], 'stopped_after_failure')
            self.assertEqual([j['name'] for j in report['jobs']], ['smoke'])

    def test_local_verification_never_calls_runner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); jobs=[]
            for name in ('smoke','broad-fit'):
                job=root/name; job.mkdir(); (job/'run.json').write_text('{}')
                jobs.append({'name':name,'job':str(job),'run_receipt_sha256':sha(job/'run.json'),'elf_sha256':'elf'})
            source=root/'campaign.json'; source.write_text(json.dumps({'schema':'iris.managed_batched_campaign.v1','order':['smoke','broad-fit'],'jobs':jobs}))
            with patch.object(campaign,'verify',return_value={'elf_sha256':'elf'}), patch.object(campaign,'execute_managed') as execute:
                report=campaign.run(source,None)
            execute.assert_not_called(); self.assertFalse(report['hardware_contacted'])


if __name__ == '__main__':
    unittest.main()
