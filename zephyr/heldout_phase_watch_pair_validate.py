"""Normal numeric validation for the controlled one-byte watchdog pair."""
import json
from batch_runner import parse_regions
from freeze_heldouts import output_hash
from compiler_pipeline import producer_golden
from uart_profiles import check_report
def validate(text,m,cases,goldens,watch_enabled):
 lines=text.splitlines();get=lambda tag:[json.loads(x.split(' ',1)[1])for x in lines if x.startswith(tag+' ')]
 if get('IRIS_DIAG_TIMEOUT')or 'IRIS_HELDOUT_FATAL 'in text:raise ValueError('Diagnostic timeout/fatal is not normal completion')
 if get('IRIS_DIAG_WATCHDOG')!=([dict(hart=1,no_progress_ms=5000)]if watch_enabled else[])or get('IRIS_DIAG_DONE')!=[dict(phases=2,failed=0)]or get('IRIS_BATCH_DONE')!=[dict(failed=0,cases=32,regions=32,trials=5)]:raise ValueError('Actual watchdog/hart/terminal geometry')
 phases=[{k:v for k,v in p.items()if k in ['phase','op','workers','kind']}for p in m['phases']]
 if get('IRIS_HELDOUT_PHASE')!=phases:raise ValueError('Two real shipped/twin phases required')
 rows=parse_regions(text,cases,m['ELF_sha256'],None,True,True)
 if len(rows)!=32:raise ValueError('Complete32 regions')
 outputs=get('IRIS_HELDOUT_RESULT')
 if len(outputs)!=30:raise ValueError('All30 compact numerical results')
 for index,result in enumerate(outputs):
  phase,job=divmod(index,15);g=goldens[0][job%3];want=dict(phase=phase,job=job,encoding='checked-word-hashes-v1',word_count=4096,accumulator_checksum=output_hash(g['accumulator_u32']),w8a8_checksum=output_hash(g['w8a8_f32_words']),mismatching_int32_words=0,mismatching_w8a8_words=0)
  if result!=want:raise ValueError('Independent full-output hash mismatch')
 producers=get('IRIS_HELDOUT_PRODUCER')
 if len(producers)!=2:raise ValueError('Both real hart2 producers')
 for phase,p in enumerate(producers):
  if p['phase']!=phase or p['hart']!=2 or p['jobs']!=15 or p['vector_checksum']!=producer_golden(5)or p['vme_refused']is not True or len(p['overlap_masks'])!=15 or not any(p['overlap_masks'][:2]):raise ValueError('Producer RVV/refusal/overlap')
 for row in rows:
  if row['cycles']<=0 or row['instret_delta']<=0:raise ValueError('Counter progress')
 return dict(phases=2,regions=32,jobs=30,embedded_full_int32_words=122880,embedded_full_W8A8_words=122880,all_compact_word_hashes_independently_match=True,harts=[0,1,2],watchdog_hart=1 if watch_enabled else None,watchdog_no_progress_ms=5000 if watch_enabled else None,watchdog_enabled=watch_enabled,uart_readback=check_report(lines,'ethan-firesim'))
