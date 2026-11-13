import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('iris_fixed_inspector', str(HERE/'operator/firesim-iris-inspect'))
spec = importlib.util.spec_from_loader(loader.name, loader)
inspector = importlib.util.module_from_spec(spec)
loader.exec_module(inspector)
spec = importlib.util.spec_from_file_location('iris_batch_inspector_tests', HERE/'batch_runner.py')
batch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name in ['proc/sys/kernel/random', 'proc/self', 'sys/bus/pci/devices/0000:01:00.0',
                     'sys/class/xdma/xdma0_control', 'sys/devices/pci0000:00/0000:01:00.0',
                     'dev', 'scratch/firesim']:
            (self.root/name).mkdir(parents=True, exist_ok=True)
        (self.root/'proc/sys/kernel/random/boot_id').write_text('test-boot')
        (self.root/'proc/self/mountinfo').write_text('1 0 0:1 / /proc rw - proc proc rw\n')
        (self.root/'scratch/firesim/firesim-db.json').write_text('[{"bdf":"01:00.0"}]')
        (self.root/'dev/xdma0_control').touch()
        (self.root/'sys/class/xdma/xdma0_control/device').symlink_to('../../../devices/pci0000:00/0000:01:00.0')

    def process(self, pid=10, command=b'python\0job.py\0', comm='python', maps='', targets=()):
        p = self.root/'proc'/str(pid)
        p.mkdir()
        (p/'fd').mkdir()
        (p/'cmdline').write_bytes(command)
        (p/'comm').write_text(comm)
        (p/'maps').write_text(maps)
        (p/'stat').write_text(str(pid)+' (name with spaces) S '+' '.join(['0']*18+['123']+['0']*8))
        (p/'cwd').symlink_to('/scratch/agustin/owned-job')
        for index, target in enumerate(targets):
            (p/'fd'/str(index)).symlink_to(target)
        return p

    def collect(self):
        return inspector.collect(self.root, 1003, 'agustin', self_pid=999)

    def test_empty_command_still_checks_held_fd(self):
        self.process(command=b'', comm='', targets=['/dev/xdma0_control'])
        r = self.collect()
        self.assertTrue(r['inspection_complete'])
        self.assertEqual(r['empty_cmdline_processes'], 1)
        self.assertEqual(r['device_holders'][0]['device'], '/dev/xdma0_control')

    def test_empty_command_still_checks_memory_mapping(self):
        target='/sys/devices/pci0000:00/0000:00:01.0/0000:01:00.0/resource0'
        self.process(command=b'', maps='1000-2000 rw-s 0 00:00 0 '+target+'\n')
        r=self.collect()
        self.assertEqual(r['device_holders'][0]['reference']['bdfs'][-1], '0000:01:00.0')

    def test_all_programming_fd_classes_are_occupied(self):
        targets=['/dev/xvsec01000','/dev/vfio/17','/dev/vfio/vfio','/dev/uio0',
                 '/dev/mem','/dev/port','/dev/iommu','anon_inode:[vfio-device]',
                 '/sys/bus/pci/devices/0000:01:00.0/resource2_wc',
                 '/sys/devices/pci0000:80/0000:81:00.0/resource0 (deleted)']
        self.process(targets=targets)
        r=self.collect()
        self.assertEqual(len(r['device_holders']),len(targets))
        self.assertTrue(r['all_pci_holders_blocked_conservatively'])

    def test_unrelated_pci_resource_is_uncertain_not_silently_ignored(self):
        self.process(targets=['/sys/devices/pci0000:40/0000:41:00.1/resource5'])
        self.assertEqual(len(self.collect()['device_holders']),1)

    def test_non_device_files_do_not_claim_occupancy(self):
        self.process(targets=['/tmp/ordinary-file','/dev/null','socket:[42]'])
        r=self.collect()
        self.assertTrue(r['inspection_complete'])
        self.assertFalse(r['device_holders'])

    def test_programmer_variants_are_busy_without_an_open_device(self):
        for pid,comm,command in [(10,'xvsecctl-v2',b'xvsecctl\0program'),
                                 (11,'python3',b'python3\0/usr/local/bin/firesim-fpga-util.py\0'),
                                 (12,'python3',b'firesim\0-c\0runtime.yaml\0infrasetup'),
                                 (13,'hw_server',b'hw_server')]:
            self.process(pid,command,comm)
        self.assertEqual(len(self.collect()['busy_processes']),4)

    def test_maps_permission_failure_is_incomplete(self):
        p=self.process()
        original=Path.read_text
        def read(path,*args,**kwargs):
            if path==p/'maps':raise PermissionError('simulated other-user maps denial')
            return original(path,*args,**kwargs)
        with patch.object(Path,'read_text',read):r=self.collect()
        self.assertFalse(r['inspection_complete'])
        self.assertIn('maps denial',repr(r['inspection_errors']))

    def test_fd_link_permission_failure_is_incomplete(self):
        p=self.process(targets=['/dev/xdma0_control'])
        original=os.readlink
        def link(path,*args,**kwargs):
            if Path(path)==p/'fd/0':raise PermissionError('simulated fd denial')
            return original(path,*args,**kwargs)
        with patch.object(os,'readlink',link):r=self.collect()
        self.assertFalse(r['inspection_complete'])

    def test_disappearing_fd_is_not_a_hidden_pid(self):
        p=self.process(targets=['/dev/xdma0_control'])
        original=os.readlink
        def link(path,*args,**kwargs):
            if Path(path)==p/'fd/0':raise FileNotFoundError('closed fd')
            return original(path,*args,**kwargs)
        with patch.object(os,'readlink',link):r=self.collect()
        self.assertTrue(r['inspection_complete'])

    def test_pid_reuse_is_incomplete(self):
        self.process()
        with patch.object(inspector,'process_start',side_effect=[100,101]):r=self.collect()
        self.assertFalse(r['inspection_complete'])
        self.assertIn('PID reused',repr(r['inspection_errors']))

    def test_missing_maps_of_still_present_process_is_incomplete(self):
        p=self.process();(p/'maps').unlink()
        self.assertFalse(self.collect()['inspection_complete'])

    def test_empty_maps_and_fd_are_actually_scanned(self):
        self.process(command=b'',comm='kernel-task')
        r=self.collect()
        self.assertTrue(r['inspection_complete']);self.assertEqual(r['scanned_processes'],1)

    def test_hidepid_cannot_qualify_unprivileged_fallback(self):
        (self.root/'proc/self/mountinfo').write_text('1 0 0:1 / /proc rw - proc proc rw,hidepid=2\n')
        with patch.object(inspector.os,'geteuid',return_value=1003):r=self.collect()
        self.assertFalse(r['inspection_complete'])

    def test_kernel_bdf_source_is_recorded(self):
        r=self.collect()
        self.assertIn('kernel-xdma-class',r['fpga_bdf_sources']['0000:01:00.0'])

    def test_absent_or_malformed_database_is_incomplete(self):
        db=self.root/'scratch/firesim/firesim-db.json'
        for content in ['{}','[{"bdf":"unknown"}]','not json']:
            db.write_text(content);self.assertFalse(self.collect()['inspection_complete'])

    def test_allocation_symlink_is_untrusted(self):
        p=self.root/'scratch/firesim/iris-exclusive-allocation.json'
        p.symlink_to(self.root/'scratch/firesim/firesim-db.json')
        self.assertFalse(self.collect()['allocation_trusted'])

    def test_collector_only_reads_existing_files(self):
        self.process(targets=['/dev/xdma0_control'])
        before={str(p):p.read_bytes() for p in self.root.rglob('*')if p.is_file()and not p.is_symlink()}
        self.collect()
        after={str(p):p.read_bytes() for p in self.root.rglob('*')if p.is_file()and not p.is_symlink()}
        self.assertEqual(before,after)


class ProbeTests(unittest.TestCase):
    def idle(self):
        return {'schema':batch.INSPECTOR_VERSION,'uid':1003,'user':'agustin','boot_id':'boot',
                'inspection_complete':False,'inspection_errors':[{'pid':10,'error':'denied'}],
                'busy_processes':[],'device_holders':[],'sessions':[]}

    def elevated(self):
        return dict(self.idle(),inspection_complete=True,inspection_errors=[],inspection_uid=0,inspection_euid=0,
                    privileged_helper={'path':batch.INSPECTOR_INSTALL_PATH,'version':batch.INSPECTOR_VERSION,
                        'sha256':'expected','uid':0,'gid':0,'mode':0o755,'bytes':100,'isolated':True,'no_site':True,'stdin':'devnull'})

    def execute(self,exists=True,metadata=None,result=None,base=None):
        value=base or self.idle();helper_path=Mock()
        if not exists:helper_path.lstat.side_effect=FileNotFoundError()
        metadata=metadata or {'sha256':'expected','uid':0,'gid':0,'mode':0o755,'bytes':100}
        output=io.StringIO();run=Mock(return_value=result or subprocess.CompletedProcess([],0,json.dumps(self.elevated()),''))
        namespace={'collect':lambda:value,'protected_regular':Mock(return_value=metadata),'sha':inspector.sha}
        with patch.object(subprocess,'run',run),patch.object(subprocess,'check_output',return_value='agustin pts/1\n'),contextlib.redirect_stdout(output):
            exec(batch.REMOTE_INSPECTION,{'namespace':namespace,'Path':lambda p:helper_path,'EXPECTED_SHA':'expected',
                 'HELPER':batch.INSPECTOR_INSTALL_PATH,'VERSION':batch.INSPECTOR_VERSION,'subprocess':subprocess,'json':json})
        return json.loads(output.getvalue()),run,namespace

    def test_expected_helper_is_fixed_no_args_no_stdin(self):
        r,run,_=self.execute()
        self.assertTrue(r['inspection_complete']);self.assertEqual(r['uid'],1003);self.assertEqual(r['inspection_euid'],0)
        self.assertEqual(run.call_args.args[0],['/usr/bin/sudo','-n','--',batch.INSPECTOR_INSTALL_PATH])
        self.assertEqual(run.call_args.kwargs['stdin'],subprocess.DEVNULL)

    def test_absent_helper_retains_incomplete_refusal(self):
        r,run,_=self.execute(exists=False)
        self.assertFalse(r['inspection_complete']);run.assert_not_called()

    def test_absent_helper_can_use_genuinely_complete_unprivileged_view(self):
        r,run,_=self.execute(exists=False,base=dict(self.idle(),inspection_complete=True,inspection_errors=[]))
        self.assertTrue(r['inspection_complete']);self.assertEqual(r['inspection_method'],'complete-unprivileged');run.assert_not_called()

    def test_unknown_helper_is_not_invoked_even_if_unprivileged_view_complete(self):
        r,run,_=self.execute(metadata={'sha256':'wrong'},base=dict(self.idle(),inspection_complete=True,inspection_errors=[]))
        self.assertFalse(r['inspection_complete']);run.assert_not_called()

    def test_password_or_privilege_failure_never_becomes_complete(self):
        r,_,_=self.execute(result=subprocess.CompletedProcess([],1,'','sudo: a password is required'))
        self.assertFalse(r['inspection_complete']);self.assertIn('privilege/execution failed',r['privilege_probe']['error'])

    def test_caller_boot_euid_version_and_source_mismatches_are_refused(self):
        for key,value in [('uid',0),('user','root'),('boot_id','different'),('inspection_euid',1003),('schema','wrong')]:
            item=self.elevated();item[key]=value
            with self.subTest(key=key):
                r,_,_=self.execute(result=subprocess.CompletedProcess([],0,json.dumps(item),''));self.assertFalse(r['inspection_complete'])
        for key,value in [('sha256','wrong'),('version','wrong'),('isolated',False),('no_site',False),('stdin','pipe')]:
            item=self.elevated();item['privileged_helper'][key]=value
            with self.subTest(helper_key=key):
                r,_,_=self.execute(result=subprocess.CompletedProcess([],0,json.dumps(item),''));self.assertFalse(r['inspection_complete'])

    def test_incomplete_privileged_scan_remains_incomplete(self):
        item=self.elevated();item.update(inspection_complete=False,inspection_errors=[{'pid':42,'error':'permission denied'}])
        r,_,_=self.execute(result=subprocess.CompletedProcess([],0,json.dumps(item),''));self.assertFalse(r['inspection_complete'])

    def test_bad_json_refuses(self):
        r,_,_=self.execute(result=subprocess.CompletedProcess([],0,'malformed',''));self.assertFalse(r['inspection_complete'])

    def test_remote_program_binds_local_source_digest(self):
        source=batch.remote_inspection_program()
        self.assertIn(batch.digest(batch.INSPECTOR_PATH),source)
        self.assertIn('fixed-root-helper',source)


class EntryPointTests(unittest.TestCase):
    def call(self, *, argv=None, uid=0, euid=0, isolated=True, no_site=True,
             filename=None, stdin_mode=stat.S_IFCHR, sudo_uid='1003', sudo_user='agustin', sudo_command=None):
        metadata={'uid':0,'gid':0,'mode':0o755,'bytes':10,'sha256':'pinned'}
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(inspector.sys,'argv',argv or [inspector.INSTALL_PATH]))
            stack.enter_context(patch.object(inspector.sys,'flags',types.SimpleNamespace(isolated=isolated,no_site=no_site)))
            stack.enter_context(patch.object(inspector,'__file__',filename or inspector.INSTALL_PATH))
            stack.enter_context(patch.object(inspector.os,'getuid',return_value=uid))
            stack.enter_context(patch.object(inspector.os,'geteuid',return_value=euid))
            stack.enter_context(patch.object(inspector.os,'fstat',return_value=types.SimpleNamespace(st_mode=stdin_mode,st_rdev=7)))
            stack.enter_context(patch.object(inspector.os,'stat',return_value=types.SimpleNamespace(st_rdev=7)))
            stack.enter_context(patch.object(inspector,'protected_regular',return_value=metadata))
            stack.enter_context(patch.object(inspector.pwd,'getpwuid',return_value=types.SimpleNamespace(pw_uid=1003,pw_name='agustin')))
            stack.enter_context(patch.dict(os.environ,{'SUDO_UID':sudo_uid,'SUDO_USER':sudo_user,'SUDO_COMMAND':sudo_command or inspector.INSTALL_PATH}))
            collect=stack.enter_context(patch.object(inspector,'collect',return_value={'inspection_complete':True}))
            output=io.StringIO()
            with contextlib.redirect_stdout(output):inspector.main()
        return json.loads(output.getvalue()),collect

    def test_entrypoint_passes_only_trusted_caller_identity(self):
        record,collect=self.call()
        collect.assert_called_once_with(caller_uid=1003,caller_user='agustin')
        self.assertEqual(record['privileged_helper']['version'],inspector.VERSION)

    def test_any_argument_is_refused(self):
        with self.assertRaisesRegex(ValueError,'no arguments'):self.call(argv=[inspector.INSTALL_PATH,'--version'])

    def test_nonisolated_or_site_enabled_python_is_refused(self):
        for change in[{'isolated':False},{'no_site':False}]:
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'isolated'):self.call(**change)

    def test_nonroot_real_or_effective_identity_is_refused(self):
        for change in[{'uid':1003},{'euid':1003}]:
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'uid0'):self.call(**change)

    def test_noninstalled_payload_is_refused(self):
        with self.assertRaisesRegex(ValueError,'install path'):self.call(filename='/tmp/user-supplied-code')

    def test_stdin_pipe_is_refused(self):
        with self.assertRaisesRegex(ValueError,'no stdin'):self.call(stdin_mode=stat.S_IFIFO)

    def test_sudo_caller_cannot_be_root_missing_or_malformed(self):
        for value in['0','','-1','1003 trailing']:
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'SUDO_UID'):self.call(sudo_uid=value)

    def test_sudo_name_or_command_mismatch_is_refused(self):
        for change in[{'sudo_user':'other'},{'sudo_command':'/usr/bin/python3 -'}]:
            with self.subTest(change=change),self.assertRaisesRegex(ValueError,'identity mismatch'):self.call(**change)


class PhaseStreamTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.manager=self.root/'manager';self.manager.mkdir()
        for name in['config_runtime.yaml','config_hwdb.yaml']:(self.manager/name).write_text('{}\n')
        self.manifest={'commands':[]}

    def script(self,source):
        (self.manager/'firesim').write_text(source)

    def run(self, *args, **kwargs):
        # Preserve unittest.TestCase.run; task execution has a separate name.
        return super().run(*args,**kwargs)

    def task(self,timeout=2):
        batch.run_task(self.manager,self.root,'kill',dict(os.environ),timeout,self.manifest)

    def test_stdout_and_stderr_are_raw_distinct_streams(self):
        self.script('import os\nos.write(1,b"OUT\\x00\\n");os.write(2,b"ERR\\xff\\n")\n')
        self.task();record=self.manifest['commands'][0]
        self.assertEqual((self.root/record['stdout_path']).read_bytes(),b'OUT\x00\n')
        self.assertEqual((self.root/record['stderr_path']).read_bytes(),b'ERR\xff\n')
        self.assertFalse(record['streams_merged']);self.assertGreaterEqual(record['host_elapsed_seconds'],0)
        self.assertEqual(record['actual_input_sha256']['runtime_sha256'],batch.digest(self.manager/'config_runtime.yaml'))

    def test_nonzero_phase_preserves_both_streams_and_exit(self):
        self.script('import sys\nprint("before");print("failure",file=sys.stderr);sys.exit(17)\n')
        with self.assertRaisesRegex(RuntimeError,'exit 17'):self.task()
        self.assertEqual(self.manifest['commands'][0]['returncode'],17)
        self.assertEqual(self.manifest['commands'][0]['status'],'failed')

    def test_timeout_retains_partial_streams_and_local_process_exit(self):
        self.script('import os,time\nos.write(1,b"started\\n");os.write(2,b"waiting\\n");time.sleep(30)\n')
        with self.assertRaises(subprocess.TimeoutExpired):self.task(timeout=0.1)
        r=self.manifest['commands'][0]
        self.assertTrue(r['timed_out']);self.assertEqual(r['status'],'timed_out')
        self.assertEqual((self.root/r['stdout_path']).read_bytes(),b'started\n')
        self.assertEqual((self.root/r['stderr_path']).read_bytes(),b'waiting\n')

    def test_changed_runtime_refuses_before_process_spawn(self):
        self.script('raise Exception("must not run")')
        self.manifest['execution_runtime_sha256']='wrong'
        with self.assertRaisesRegex(RuntimeError,'input changed'):self.task()
        self.assertEqual(self.manifest['commands'],[])

    def test_spawn_failure_is_recorded(self):
        self.script('print("not executed")')
        with patch.object(batch.subprocess,'Popen',side_effect=OSError('spawn refused')):
            with self.assertRaisesRegex(OSError,'spawn refused'):self.task()
        self.assertEqual(self.manifest['commands'][0]['status'],'spawn_failed')

    def test_shared_manager_dependency_change_refuses_before_spawn(self):
        self.script('raise Exception("must not run")')
        dependency=self.root/'shared_dependency.py';dependency.write_text('changed')
        self.manifest['input_sha256']={str(dependency):'prior-digest'}
        with self.assertRaisesRegex(RuntimeError,'source input changed'):self.task()
        self.assertEqual(self.manifest['commands'],[])

    def test_cleanup_phase_is_explicit(self):
        self.script('pass');self.manifest['active_phase']='cleanup';self.task()
        self.assertTrue(self.manifest['commands'][0]['cleanup_phase'])


if __name__=='__main__':unittest.main()
