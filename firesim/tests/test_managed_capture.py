"""Local transport/capture controls; no test opens SSH or an FPGA device."""
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import test_batch_runner as fixtures
batch = fixtures.batch


class ManagedEvidenceTests(unittest.TestCase):
    setUp = fixtures.BatchTests.setUp
    invoke = fixtures.BatchTests.invoke
    idle = staticmethod(fixtures.BatchTests.idle)

    def test_staging_refusal_withholds_workload_and_keeps_owned_cleanup(self):
        def refuse(*args):raise RuntimeError('staged ELF digest mismatch')
        with self.assertRaisesRegex(RuntimeError, 'ELF digest mismatch'):
            self.invoke([self.idle()], staging_hook=refuse)
        self.assertEqual(self.tasks, ['kill', 'infrasetup', 'kill'])
        self.assertEqual(self.manifest['cleanup_status'], 'passed')
        self.assertEqual(self.manifest['capture']['status'], 'captured')

    def test_successful_guest_capture_failure_retains_guest_outcome(self):
        def capture(output, manifest):
            self.assertEqual(self.tasks, ['kill', 'infrasetup', 'runworkload', 'kill'])
            self.assertEqual(self.locks, [True, False])
            manifest['capture']={'status':'failed','error':'archive refused'}
            return False
        with self.assertRaises(batch.EvidenceCaptureError):
            self.invoke([self.idle()], capture_hook=capture)
        self.assertEqual(self.manifest['status'], 'completed_uncertified')
        self.assertIn('capture_error', self.manifest)

    def test_archive_failure_does_not_mask_guest_failure(self):
        def task(name):
            if name=='runworkload':raise RuntimeError('guest failure evidence')
        def capture(output, manifest):
            manifest['capture']={'status':'failed','error':'archive failed'};return False
        with self.assertRaisesRegex(RuntimeError,'guest failure evidence'):
            self.invoke([self.idle()], task, capture_hook=capture)
        self.assertEqual(self.manifest['status'],'failed')
        self.assertEqual(self.manifest['capture']['status'],'failed')

    def test_uncertain_cleanup_withholds_capture(self):
        uncertain=dict(self.idle(),inspection_complete=False)
        def capture(*args):raise AssertionError('must not archive an uncertain running job')
        with self.assertRaisesRegex(RuntimeError,'Incomplete'):
            self.invoke([self.idle(),self.idle(),self.idle(),self.idle(),uncertain],capture_hook=capture)
        self.assertEqual(self.manifest['capture']['status'],'withheld')
        self.assertTrue(self.manifest['lock_retained_for_operator'])

    def test_lock_release_failure_withholds_capture_and_records_retained_lock(self):
        def release():raise RuntimeError('lost lock visibility')
        with self.assertRaisesRegex(RuntimeError,'lost lock visibility'):
            self.invoke([self.idle()],release_hook=release)
        self.assertTrue(self.manifest['lock_retained_for_operator'])
        self.assertEqual(self.manifest['capture']['status'],'withheld')

    def test_unfrozen_audit_refuses_before_any_remote_inspection(self):
        self.manifest['capture_checklist_frozen']=False
        with self.assertRaisesRegex(RuntimeError,'observability audit'):
            self.invoke([])
        self.assertEqual(self.tasks,[]);self.assertEqual(self.locks,[])

    def prepare_with_audit(self, **changes):
        image=batch.digest(self.base/'image.tar.gz');driver=batch.digest(self.driver)
        report={'schema':'iris.candidate_image_observability.v2','loaded_image_verified':False,
            'input_sha256':{'/candidate/firesim.tar.gz':image,'/candidate/driver-bundle.tar.gz':driver},
            'generated_bridge_constructors':['FASED'], 'fased':{'latency_histogram_data_available':False},
            'collateral_unavailable_instrumentation':['TracerV']}
        report.update(changes)
        path=self.base/'audit.json';path.write_text(json.dumps(report))
        out=self.base/'audited-job'
        return batch.prepare(self.deploy,out,self.elf,self.manifest['cases'],self.deploy/'config_runtime.yaml',
            self.deploy/'config_hwdb.yaml',self.driver,observability_report=path)

    def test_exact_audit_and_profile_override_are_bound_without_fabricating_widgets(self):
        manager,manifest=self.prepare_with_audit()
        self.assertTrue(manifest['capture_checklist_frozen'])
        self.assertFalse(manifest['observability_audit']['loaded_image_verified'])
        self.assertEqual(manifest['observability_override']['target_cycle_argument'],'+profile-interval=1000000')
        self.assertFalse(manifest['observability_override']['changes_clock_or_memory_parameters'])
        workload=json.loads((manager/'workloads/iris-batch.json').read_text())
        self.assertEqual(workload['workloads'],[{'name':'iris-batch0'}])
        self.assertEqual(workload['common_simulation_outputs'],['uartlog'])

    def test_wrong_candidate_image_or_driver_is_refused(self):
        with self.assertRaisesRegex(ValueError,'exact image/driver'):
            self.prepare_with_audit(input_sha256={'/candidate/firesim.tar.gz':'wrong','/candidate/driver-bundle.tar.gz':'wrong'})

    def test_new_inventory_v3_is_frozen_by_digest_without_hardcoded_candidate(self):
        manager,manifest=self.prepare_with_audit(schema='iris.candidate_image_observability.v3')
        self.assertEqual(manifest['observability_audit']['sha256'],batch.digest(self.base/'audit.json'))

    def test_unknown_audit_schema_is_refused(self):
        path=self.base/'unknown-audit.json';path.write_text('{}')
        with self.assertRaisesRegex(ValueError,'Unsupported instrumentation audit schema'):
            batch.prepare(self.deploy,self.base/'unknown-job',self.elf,self.manifest['cases'],
                self.deploy/'config_runtime.yaml',self.deploy/'config_hwdb.yaml',self.driver,observability_report=path)

    def test_invalid_or_ambiguous_profile_request_is_refused(self):
        for i,value in enumerate([0,-1,True]):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'Positive target-cycle'):
                batch.prepare(self.deploy,self.base/('profile'+str(i)),self.elf,self.manifest['cases'],
                    self.deploy/'config_runtime.yaml',self.deploy/'config_hwdb.yaml',self.driver,profile_interval=value)
        import yaml
        runtime=yaml.safe_load((self.deploy/'config_runtime.yaml').read_text())
        runtime['target_config']['plusarg_passthrough']='+profile-interval=9'
        (self.deploy/'config_runtime.yaml').write_text(yaml.safe_dump(runtime))
        with self.assertRaisesRegex(ValueError,'Ambiguous manual'):
            batch.prepare(self.deploy,self.base/'ambiguous',self.elf,self.manifest['cases'],
                self.deploy/'config_runtime.yaml',self.deploy/'config_hwdb.yaml',self.driver)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.owned='/scratch/agustin/firesim/'+'a'*32
        self.manifest={'image':{'sha256':'image'},'driver':{'sha256':'driver'},'elf_sha256':'elf','remote':{'uid':1003}}

    def stage(self, report=None, result=None):
        report=report or {'uid':1003,'base':self.owned+'/sim_slot_0','files':{
            'firesim.tar.gz':{'sha256':'image'},'driver-bundle.tar.gz':{'sha256':'driver'},'iris-batch0-batch.elf':{'sha256':'elf'}}}
        result=result or subprocess.CompletedProcess([],0,json.dumps(report).encode(),b'raw\xff warning')
        with patch.object(batch.subprocess,'run',return_value=result) as run:
            value=batch.verify_remote_staging('not-contacted',self.owned,self.manifest,self.root)
        return value,run

    def test_verified_staging_binds_both_raw_streams_and_fixed_readonly_probe(self):
        row,run=self.stage()
        self.assertEqual(row['status'],'verified')
        self.assertEqual((self.root/row['stderr_path']).read_bytes(),b'raw\xff warning')
        self.assertIn('os.O_NOFOLLOW',run.call_args.kwargs['input'].decode())
        self.assertEqual(run.call_args.args[0][-4:],['/usr/bin/python3','-I','-S','-'])

    def test_staging_digest_mismatch_is_recorded_before_exception(self):
        with self.assertRaisesRegex(RuntimeError,'digests do not match'):
            self.stage({'uid':1003,'base':self.owned+'/sim_slot_0','files':{}})
        row=self.manifest['transport_audits'][0]
        self.assertEqual(row['status'],'failed');self.assertTrue((self.root/row['stdout_path']).exists())
        self.assertEqual(json.loads((self.root/'run.json').read_text())['transport_audits'][0]['status'],'failed')

    def test_staging_probe_failure_keeps_original_stderr_bytes(self):
        with self.assertRaisesRegex(RuntimeError,'staging audit failed'):
            self.stage(result=subprocess.CompletedProcess([],1,b'',b'bad symlink\xff'))
        row=self.manifest['transport_audits'][0]
        self.assertEqual((self.root/row['stderr_path']).read_bytes(),b'bad symlink\xff')

    def transport(self, files=None, extra=None, uid=1003):
        files=files or {'memory_stats0.csv':b'header\n1,2\n','latency_histogram.csv':b''}
        data=io.BytesIO();rows=[]
        with tarfile.open(fileobj=data,mode='w') as tar:
            for name in ['memory_stats0.csv','latency_histogram.csv','heartbeat.csv','sim-run.sh','uartlog']:
                if name not in files:rows.append({'name':name,'status':'missing'});continue
                value=files[name];info=tarfile.TarInfo(name);info.size=len(value);tar.addfile(info,io.BytesIO(value))
                rows.append({'name':name,'status':'captured'if value else'empty','sha256':batch.hashlib.sha256(value).hexdigest(),'bytes':len(value)})
            if extra:
                info=tarfile.TarInfo(extra);info.size=1;tar.addfile(info,io.BytesIO(b'x'))
            value=json.dumps({'files':rows,'uid':uid,'base':self.owned+'/sim_slot_0'}).encode()
            info=tarfile.TarInfo('optional-manifest.json');info.size=len(value);tar.addfile(info,io.BytesIO(value))
        def run(*args,**kwargs):
            kwargs['stdout'].write(data.getvalue());kwargs['stderr'].write(b'copyback stderr\xff')
            return subprocess.CompletedProcess([],0)
        with patch.object(batch.subprocess,'run',side_effect=run):
            return batch.collect_optional_observability('not-contacted',self.owned,self.root,1003)

    def test_missing_and_empty_optional_counters_are_explicit_not_guest_failures(self):
        row=self.transport();self.assertEqual(row['status'],'collected')
        self.assertEqual([v['status']for v in row['files']],['captured','empty','missing','missing','missing'])
        self.assertEqual((self.root/'optional-observability/memory_stats0.csv').read_bytes(),b'header\n1,2\n')

    def test_heartbeat_and_failed_raw_uart_bytes_are_preserved(self):
        values={'heartbeat.csv':b'cycle,host\n123,4\n','uartlog':b'failure\x00\xff\n'}
        row=self.transport(files=values)
        self.assertEqual(row['status'],'collected')
        for name,content in values.items():
            self.assertEqual((self.root/'optional-observability'/name).read_bytes(),content)

    def test_optional_transport_traversal_and_identity_mismatch_are_unavailable(self):
        row=self.transport(extra='../escape');self.assertEqual(row['status'],'unavailable')
        self.assertFalse((self.root/'escape').exists())

    def test_optional_transport_wrong_uid_is_unavailable(self):
        self.assertEqual(self.transport(uid=0)['status'],'unavailable')

    def test_real_capture_cli_produces_archive_outside_job_after_preserving_raw_files(self):
        job=self.root/'job';job.mkdir();(job/'raw.stdout').write_bytes(b'raw\x00\xff')
        manifest={'status':'failed','error':'guest evidence','cleanup_status':'passed'}
        self.assertTrue(batch.capture_quiescent_run(job,manifest))
        self.assertEqual(manifest['status'],'failed')
        archive=Path(manifest['capture']['archive']);self.assertEqual(archive.parent,self.root)
        with tarfile.open(archive) as tar:
            self.assertTrue(any(m.name.endswith('raw.stdout') for m in tar.getmembers()))

    def test_capture_partial_and_errors_are_preserved_without_changing_guest_status(self):
        job=self.root/'job';job.mkdir();manifest={'status':'completed_uncertified'}
        def run(command,**kwargs):
            archive=Path(command[command.index('--output')+1]);Path(str(archive)+'.partial').write_bytes(b'partial')
            kwargs['stderr'].write(b'changed source\xff');return subprocess.CompletedProcess(command,1)
        with patch.object(batch.subprocess,'run',side_effect=run):self.assertFalse(batch.capture_quiescent_run(job,manifest))
        self.assertEqual(manifest['status'],'completed_uncertified')
        self.assertTrue(manifest['capture']['partial_archive_present'])
        self.assertEqual(Path(manifest['capture']['stderr_path']).read_bytes(),b'changed source\xff')

    def test_isolated_system_python_ignores_untrusted_pythonpath_and_cwd_imports(self):
        marker=self.root/'executed'
        (self.root/'json.py').write_text('open('+repr(str(marker))+',"w").write("unsafe")\n')
        result=subprocess.run(['/usr/bin/python3','-I','-S',str(batch.INSPECTOR_PATH)],cwd=self.root,
            env=dict(os.environ,PYTHONPATH=str(self.root)),stdin=subprocess.DEVNULL,capture_output=True)
        self.assertNotEqual(result.returncode,0);self.assertFalse(marker.exists())
        self.assertIn(b'iris-fpga-inspection-refused',result.stderr)


class ActualLocalProbeTests(unittest.TestCase):
    """Execute the real remote probe body against local ordinary fixtures only."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.private=self.root/'private';self.private.mkdir(mode=0o700)
        self.slot=self.private/'sim_slot_0';self.slot.mkdir()
        self.output=self.root/'output';self.output.mkdir()
        self.owned='/scratch/agustin/firesim/'+'b'*32
        values={'firesim.tar.gz':b'image','driver-bundle.tar.gz':b'driver','iris-batch0-batch.elf':b'elf'}
        for name,data in values.items():(self.slot/name).write_bytes(data)
        self.manifest={'image':{'sha256':batch.digest(self.slot/'firesim.tar.gz')},
            'driver':{'sha256':batch.digest(self.slot/'driver-bundle.tar.gz')},
            'elf_sha256':batch.digest(self.slot/'iris-batch0-batch.elf'),'remote':{'uid':os.getuid()}}
        self.real_run=subprocess.run

    def local_probe(self, command, **kwargs):
        self.assertEqual(command[0],'ssh')
        code=kwargs['input'].replace(('BASE='+repr(self.owned)).encode(),('BASE='+repr(str(self.private))).encode(),1)
        result=self.real_run(['/usr/bin/python3','-I','-S','-'],input=code,capture_output=True,timeout=5)
        # Translate only the reporting base to its expected remote spelling.
        return subprocess.CompletedProcess(command,result.returncode,
            result.stdout.replace(str(self.private).encode(),self.owned.encode()),result.stderr)

    def stage(self):
        with patch.object(batch.subprocess,'run',side_effect=self.local_probe):
            return batch.verify_remote_staging('never-contacted',self.owned,self.manifest,self.output)

    def test_actual_probe_hashes_the_three_staged_regular_files(self):
        self.assertEqual(self.stage()['status'],'verified')

    def test_actual_probe_refuses_staged_symlink(self):
        p=self.slot/'iris-batch0-batch.elf';p.unlink();p.symlink_to(self.slot/'firesim.tar.gz')
        with self.assertRaisesRegex(RuntimeError,'not a regular file'):self.stage()
        self.assertEqual(self.manifest['transport_audits'][0]['status'],'failed')

    def test_actual_probe_refuses_fifo_without_blocking_or_opening_it(self):
        p=self.slot/'iris-batch0-batch.elf';p.unlink();os.mkfifo(p)
        with self.assertRaisesRegex(RuntimeError,'not a regular file'):self.stage()

    def test_actual_probe_refuses_missing_elf(self):
        (self.slot/'iris-batch0-batch.elf').unlink()
        with self.assertRaisesRegex(RuntimeError,'No such file'):self.stage()

    def test_actual_probe_refuses_nonprivate_staging_parent(self):
        self.private.chmod(0o755)
        with self.assertRaisesRegex(RuntimeError,'untrusted private'):self.stage()


if __name__=='__main__':unittest.main()
