"""Synthetic-only prefix controls; no model/reference run files are opened."""
import copy
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import analyze_heldout_prefix_v2 as diagnostic


class SyntheticPrefixControls(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.corpus={'phases':[{'phase':p,'op':'gemm'if p<4 else'conv2d','workers':1+(p%4)//2,'kind':'shipped'if p%2==0 else'twin'}for p in range(8)]}
  cls.goldens=[[{'accumulator_u32':[o+dataset+1]*4096,'w8a8_f32_words':[0x3f800000+o+dataset]*4096}for dataset in range(3)]for o in range(2)]
  cls.cases=[];cls.parts=[];cls.regions=[];cls.windows=[]
  dump=lambda prefix,value:prefix+' '+json.dumps(value,separators=(',',':'))+'\n'
  for p in cls.corpus['phases']:
   phase=p['phase'];stem='heldout.batch.%s.h%d.%s.'%(p['op'],p['workers'],p['kind']);parent='merlin.zephyr.%s.%dcompute'%(p['op'],p['workers'])
   case={'id':stem+'e2e','parent_case_id':parent,'region':'pipeline_end_to_end','active_harts':[2],'expected_checksums_by_hart':[0,0,123]};cls.cases.append(case)
   row={'case_id':case['id'],'parent_case_id':parent,'region':'pipeline_end_to_end','hart':2,'role':'pipeline.end_to_end','scope':'producer_entry_to_all_outputs_consumed','start_cycle':100000*phase+100,'end_cycle':100000*phase+10000,'instret_delta':500,'checksum':123,'pass':True};rows=[row];cls.regions.append(row)
   window={'phase':phase,'hart':2,'source':'CLINT.mtime.MMIO','start_mtime':100*phase+10,'end_mtime':100*phase+20,'timebase_hz':500000,'core_cycles_per_tick':1000,'scope':'producer_entry_to_all_outputs_consumed'};cls.windows.append(window)
   text=dump('IRIS_HELDOUT_PHASE',p)+dump('IRIS_REGION',row)+dump('IRIS_HELDOUT_ELAPSED',window)
   for job in range(15):
    g=cls.goldens[phase//4][job%3];acc=diagnostic.output_hash(g['accumulator_u32']);quant=diagnostic.output_hash(g['w8a8_f32_words'])
    text+=dump('IRIS_HELDOUT_RESULT',dict(phase=phase,job=job,encoding='checked-word-hashes-v1',word_count=4096,accumulator_checksum=acc,w8a8_checksum=quant,mismatching_int32_words=0,mismatching_w8a8_words=0))
    checks=[diagnostic.output_hash(g['accumulator_u32'][4096*h//p['workers']:4096*(h+1)//p['workers']])for h in range(p['workers'])]+[0]*(3-p['workers'])
    case={'id':stem+'job'+str(job),'parent_case_id':parent,'region':'job'+str(job),'active_harts':list(range(p['workers'])),'expected_checksums_by_hart':checks,'trial_id':job//3,'dataset_id':job%3};cls.cases.append(case)
    for hart in case['active_harts']:
     row={'case_id':case['id'],'parent_case_id':parent,'region':case['region'],'hart':hart,'trial_id':job//3,'dataset_id':job%3,'role':'scalar.compute'if p['kind']=='twin'else'vme.compute','hart_mask':(1<<p['workers'])-1,'start_cycle':100000*phase+100+job*100,'end_cycle':100000*phase+150+job*100,'instret_delta':40,'checksum':checks[hart],'pass':True};rows.append(row);cls.regions.append(row);text+=dump('IRIS_REGION',row)
   text+=dump('IRIS_HELDOUT_PRODUCER',dict(phase=phase,hart=2,jobs=15,overlap_masks=[1]*15,vector_checksum=diagnostic.producer_golden(5),vme_refused=True));cls.parts.append(text)
  cls.header=dump('IRIS_UART_PROFILE',{'requested_baud':3676470,'clock_hz':500000000,'divisor':135})
  cls.pred={'pass':True,'timing_kind':'experimental-empirical','ELF_sha256':diagnostic.ELF,'workload_manifest_sha256':diagnostic.V6,'fitting_allowed':False,'regions':cls.regions,'global_elapsed_windows':cls.windows}
  cls.one=cls.header+cls.parts[0]
 def validate(self,text):return diagnostic.validate_prefix(text,self.corpus,self.cases,self.goldens)
 def change(self,text,prefix,key,value):
  lines=text.splitlines()
  for i,line in enumerate(lines):
   if line.startswith(prefix):
    row=json.loads(line[len(prefix):]);row[key]=value;lines[i]=prefix+json.dumps(row);break
  else:raise AssertionError('Synthetic record missing')
  return '\n'.join(lines)+'\n'
 def test_one_complete(self):
  r=self.validate(self.one);self.assertEqual((r['complete_leading_phases'],len(r['regions'])),(1,16));self.assertEqual(r['excluded_suffix_bytes'],0)
 def test_announcement_after_complete_is_excluded(self):
  r=self.validate(self.one+self.parts[1].splitlines(keepends=True)[0]);self.assertEqual(r['complete_leading_phases'],1);self.assertTrue(r['excluded_incomplete_trailing_phase'])
 def test_partial_second_phase_is_disclosed(self):
  r=self.validate(self.one+''.join(self.parts[1].splitlines(keepends=True)[:12]));self.assertEqual(len(r['regions']),16);self.assertGreater(r['excluded_suffix_bytes'],0)
 def test_partial_footer_is_not_decoded(self):
  r=self.validate(self.one+self.parts[1].splitlines(keepends=True)[0]+'IRIS_HELDOUT_PRODUCER {"phase":');self.assertEqual(r['complete_leading_phases'],1)
 def test_malformed_complete_footer_rejected(self):
  with self.assertRaises(ValueError):self.validate(self.one+self.parts[1].splitlines(keepends=True)[0]+'IRIS_HELDOUT_PRODUCER {bad}\n')
 def test_seven_complete_plus_last_partial(self):
  r=self.validate(self.header+''.join(self.parts[:7])+self.parts[7].splitlines(keepends=True)[0]);self.assertEqual(r['complete_leading_phases'],7)
 def test_full_eight_is_not_partial(self):
  with self.assertRaises(ValueError):self.validate(self.header+''.join(self.parts))
 def test_incomplete_middle_is_rejected(self):
  with self.assertRaises(ValueError):self.validate(self.one+self.parts[1].splitlines(keepends=True)[0]+self.parts[2])
 def test_duplicate_announcement_rejected(self):
  with self.assertRaises(ValueError):self.validate(self.one+self.parts[0])
 def test_bool_mask_is_rejected(self):
  text=self.one.replace('"hart_mask":1','"hart_mask":true',1)
  with self.assertRaises(ValueError):self.validate(text)
 def test_bool_elapsed_is_rejected(self):
  with self.assertRaises(ValueError):self.validate(self.change(self.one,'IRIS_HELDOUT_ELAPSED ','phase',False))
 def test_bool_counter_is_rejected(self):
  with self.assertRaises(ValueError):self.validate(self.change(self.one,'IRIS_REGION ','start_cycle',False))
 def test_wrong_word_hash_is_rejected(self):
  with self.assertRaises(ValueError):self.validate(self.change(self.one,'IRIS_HELDOUT_RESULT ','accumulator_checksum',0))
 def test_complete_footer_does_not_hide_missing_result(self):
  lines=self.one.splitlines();del lines[next(i for i,l in enumerate(lines)if l.startswith('IRIS_HELDOUT_RESULT '))]
  with self.assertRaises(ValueError):self.validate('\n'.join(lines)+'\n')
 def test_fatal_in_excluded_suffix_is_rejected(self):
  with self.assertRaises(ValueError):self.validate(self.one+self.parts[1].splitlines(keepends=True)[0]+'IRIS_FATAL {}\n')
 def test_normal_batch_done_is_not_partial(self):
  with self.assertRaises(ValueError):self.validate(self.one+'IRIS_BATCH_DONE {"failed":0}\n')
 def test_pred_complete_structure(self):
  rows,windows=diagnostic.validate_prediction(copy.deepcopy(self.pred),self.corpus,self.cases);self.assertEqual((len(rows),len(windows)),(188,8))
 def test_missing_pred_windows_rejected(self):
  pred=copy.deepcopy(self.pred);pred['global_elapsed_windows']=[]
  with self.assertRaises(ValueError):diagnostic.validate_prediction(pred,self.corpus,self.cases)
 def test_duplicate_pred_windows_rejected(self):
  pred=copy.deepcopy(self.pred);pred['global_elapsed_windows'][1]=pred['global_elapsed_windows'][0]
  with self.assertRaises(ValueError):diagnostic.validate_prediction(pred,self.corpus,self.cases)
 def test_bool_pred_window_rejected(self):
  pred=copy.deepcopy(self.pred);pred['global_elapsed_windows'][0]['phase']=False
  with self.assertRaises(ValueError):diagnostic.validate_prediction(pred,self.corpus,self.cases)
 def test_missing_pred_region_rejected(self):
  pred=copy.deepcopy(self.pred);pred['regions'].pop()
  with self.assertRaises(ValueError):diagnostic.validate_prediction(pred,self.corpus,self.cases)
 def specs(self):return[(n,str(diagnostic.ROOT/p),h)for n,(p,h)in diagnostic.FROZEN_PREDICTIONS.items()]
 def test_four_declared_specs_without_file_reads(self):self.assertEqual(len(diagnostic.declared_predictions(self.specs())),4)
 def test_missing_prospective_model_rejected(self):
  with self.assertRaises(ValueError):diagnostic.declared_predictions(self.specs()[:-1])
 def test_wrong_prospective_digest_rejected(self):
  specs=self.specs();specs[0]=(specs[0][0],specs[0][1],'0'*64)
  with self.assertRaises(ValueError):diagnostic.declared_predictions(specs)
 def test_duplicate_prospective_model_rejected(self):
  specs=self.specs();specs[-1]=specs[0]
  with self.assertRaises(ValueError):diagnostic.declared_predictions(specs)
 def lifecycle(self):
  run={'status':'failed','cleanup_status':'passed','cleanup_error':None,'error':'synthetic watchdog','commands':[
    {'task':task,'status':'failed'if i==2 else'passed','returncode':124 if i==2 else 0,'timed_out':False,'host_elapsed_seconds':2.5,'cleanup_phase':i==3}
    for i,task in enumerate(('kill','infrasetup','runworkload','kill'))]}
  current={k:v for k,v in run.items()if k!='commands'};return current,run
 def test_failed_lifecycle_typed(self):
  self.assertEqual(len(diagnostic.failed_lifecycle(*self.lifecycle())),4)
 def test_archived_completed_current_failed_rejected(self):
  current,run=self.lifecycle();run['status']='completed_uncertified'
  with self.assertRaises(ValueError):diagnostic.failed_lifecycle(current,run)
 def test_bool_returncode_rejected(self):
  current,run=self.lifecycle();run['commands'][0]['returncode']=False
  with self.assertRaises(ValueError):diagnostic.failed_lifecycle(current,run)
 def test_fake_cleanup_flag_rejected(self):
  current,run=self.lifecycle();run['commands'][3]['cleanup_phase']=False
  with self.assertRaises(ValueError):diagnostic.failed_lifecycle(current,run)
 def test_nonfinite_host_time_rejected(self):
  current,run=self.lifecycle();run['commands'][0]['host_elapsed_seconds']=float('nan')
  with self.assertRaises(ValueError):diagnostic.failed_lifecycle(current,run)
 def identity(self):
  return {'campaign_role':'independent_heldout_zephyr_Merlin_batch_v6','fitting_allowed':False,'corpus_sha256':diagnostic.V6,'elf_sha256':diagnostic.ELF,'frozen_prediction_sha256':diagnostic.FROZEN_PREDICTIONS['9b2'][1]}, {'job/prediction.json':diagnostic.FROZEN_PREDICTIONS['9b2'][1],'job/manager/workloads/iris-batch/batch.elf':diagnostic.ELF}
 def test_exact_archived_primary_and_executed_elf(self):diagnostic.archived_identity(*self.identity())
 def test_unused_correct_elf_cannot_replace_actual_elf(self):
  run,ids=self.identity();ids['job/snapshot.elf']=ids.pop('job/manager/workloads/iris-batch/batch.elf')
  with self.assertRaises(ValueError):diagnostic.archived_identity(run,ids)
 def test_unanchored_primary_prediction_rejected(self):
  run,ids=self.identity();run['frozen_prediction_sha256']='0'*64
  with self.assertRaises(ValueError):diagnostic.archived_identity(run,ids)


if __name__=='__main__':unittest.main()
