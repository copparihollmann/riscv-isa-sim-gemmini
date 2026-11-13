import copy
import unittest
from archive_operator_integrity_v2 import lifecycle

def fixture():
    return dict(status='completed_uncertified',campaign_role='bounded_campaign_memory_roofline',
        campaign_kind='memory_roofline',cases=[{}]*432,primary_measurement_eligible=False,
        cleanup_error=None,cleanup_status='passed',require_regions=True,require_goldens=True,
        strict_postgate=dict(path='/reviewed/reader',sha256='a'*64),
        lifecycle_policy='kill -> infrasetup -> runworkload -> kill',
        commands=[dict(task=task,status='passed',returncode=0,timed_out=False,phase_index=i+1,cleanup_phase=i==3)
                  for i,task in enumerate(['kill','infrasetup','runworkload','kill'])],
        shared_lock=dict(kind='exclusive_atomic_directory',path='/scratch/firesim/iris-locks/fpga0',uid=1003,boot_id='known-boot'),
        private_directory=dict(uid=1003,path='/scratch/agustin/firesim/owned-token'),lock_token='owned-token',
        remote_simulation_dir='/scratch/agustin/firesim/owned-token',
        safety_inspections=[dict(stage=phase,report=dict(inspection_complete=True,inspection_errors=[],
            launch_authorization_verified=True,boot_id='known-boot',uid=1003))
            for phase in ['kill','infrasetup','runworkload','cleanup']])

class OperatorArchiveScope(unittest.TestCase):
    def test_explicit_supported_families(self):
        r=fixture();lifecycle(r)
        r.update(campaign_role='bounded_campaign_panel_b_ab',campaign_kind='panel_b_ab',cases=[{}]*54);lifecycle(r)
    def test_foreign_kind_wrong_count_and_missing_goldens_reject(self):
        for key,value in [('campaign_role','bounded_campaign_conv'),('campaign_kind','panel_b_ab'),('cases',[{}]*431),('require_goldens',False),('strict_postgate',None)]:
            r=fixture();r[key]=value
            with self.assertRaises(ValueError):lifecycle(r)
    def test_ownership_and_cleanup_failures_still_reject(self):
        r=fixture();r['cleanup_error']='uncertain'
        with self.assertRaises(ValueError):lifecycle(r)
        r=fixture();r['safety_inspections'][2]['report']['inspection_complete']=False
        with self.assertRaises(ValueError):lifecycle(r)
        r=fixture();r['private_directory']['uid']=1004
        with self.assertRaises(ValueError):lifecycle(r)
    def test_wrong_lifecycle_refuses(self):
        r=fixture();r['commands'][0],r['commands'][1]=r['commands'][1],r['commands'][0]
        with self.assertRaises(ValueError):lifecycle(r)

if __name__=='__main__':unittest.main()
