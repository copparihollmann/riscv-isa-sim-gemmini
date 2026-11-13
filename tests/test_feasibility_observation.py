import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from iris_model.feasibility import scalar_observation, frozen_scoped_report


class ScalarObservationGateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.path=self.root/'report.json'
        table=[]
        ref_words=[0x495249535343414c,1,0,1,1,1,0,0];model_words=list(ref_words)
        for h in range(3):
            for k in range(2):
                rc=(263 if k==0 else 136) if h<2 else 259
                mc=(267 if k==0 else 140) if h<2 else 777
                ri=256 if h<2 else 257
                ref_words.extend([100,100+rc,1000,1000+ri,257 if k==0 else 292,256,0,0])
                model_words.extend([100,100+mc,1000,1257,257 if k==0 else 292,256,0,0])
                table.append({'hart':h,'kernel':'dependent256' if k==0 else 'independent256',
                              'rtl_cycles':rc,'model_cycles':mc,'signed_error_percent':100*(mc-rc)/rc,
                              'within_2_percent':abs(mc-rc)*100<=2*rc,'rtl_instret_delta':ri,
                              'model_instret_delta':257,'counter_contract_matches':ri==257})
        artifacts={}
        for tag,words in [('reference',ref_words),('model',model_words)]:
            directory=self.root/tag;directory.mkdir()
            run={'exit_status':0,'timed_out':False,'argv':['/same.elf'],'input_sha256':{'/same.elf':'e'*64},
                 'status':'failed' if tag=='reference' else 'passed_scalar_reference_regions'}
            if tag=='reference':run['error']='counter/checksum mismatch'
            (directory/'results.json').write_text(json.dumps(run))
            (directory/'signature').write_text(''.join(f'{word:016x}\n' for word in words))
            for path in directory.iterdir():artifacts[str(path.relative_to(self.root))]=hashlib.sha256(path.read_bytes()).hexdigest()
        self.report={'schema':'iris.scalar_rtl_observation.v1','qualified_accuracy':False,'held_out_validation':False,
                     'timing_calibrated':False,'ethan_image_association_verified':False,'strict_counter_check_passed':False,
                     'artifact_sha256':artifacts,'same_elf_sha256':'e'*64,'source_fir_sha256':'f'*64,'table':table}
        self.write()

    def write(self):self.path.write_text(json.dumps(self.report))

    def test_real_discrepancy_stays_unqualified(self):
        result=scalar_observation(self.path)
        self.assertFalse(result['admitted_for_calibration'])
        self.assertFalse(result['table'][1]['within_2_percent'])
        self.assertEqual(result['table'][4]['signed_error_percent'],200)

    def test_changing_cycle_table_cannot_hide_raw_result(self):
        self.report['table'][1]['model_cycles']=136;self.write()
        with self.assertRaisesRegex(ValueError,'raw counter'):scalar_observation(self.path)

    def test_claiming_qualification_is_rejected(self):
        self.report['qualified_accuracy']=True;self.write()
        with self.assertRaisesRegex(ValueError,'unqualified'):scalar_observation(self.path)

    def test_modified_signature_is_rejected(self):
        with (self.root/'reference/signature').open('a') as stream:stream.write('0\n')
        with self.assertRaisesRegex(ValueError,'changed scalar'):scalar_observation(self.path)

    def test_path_escape_is_rejected(self):
        self.report['artifact_sha256']['../foreign']='0'*64;self.write()
        with self.assertRaisesRegex(ValueError,'changed scalar'):scalar_observation(self.path)

    def scoped_report(self):
        self.report={'schema':'synthetic.scope.v1','hardware_contacted':False,'timing_calibrated':False,
                     'matches_ethan_firesim_image':False,'artifact_sha256':self.report['artifact_sha256']}
        self.write()

    def test_frozen_scope_identity_does_not_promote_calibration(self):
        self.scoped_report()
        _,identity=frozen_scoped_report(self.path,'synthetic.scope.v1')
        self.assertFalse(identity['qualified_timing']);self.assertFalse(identity['deployed_image_equivalence'])

    def test_qualified_or_unbound_scoped_report_is_refused(self):
        self.scoped_report()
        for key,value in [('timing_calibrated',True),('hardware_contacted',True),
                          ('matches_ethan_firesim_image',True),('artifact_sha256',{})]:
            old=self.report[key];self.report[key]=value;self.write()
            with self.subTest(key=key),self.assertRaises(ValueError):frozen_scoped_report(self.path,'synthetic.scope.v1')
            self.report[key]=old


if __name__=='__main__':unittest.main()
