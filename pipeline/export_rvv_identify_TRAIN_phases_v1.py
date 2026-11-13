#!/usr/bin/env python3
"""ROOT data owner only: lossless TRAIN phase deltas from strict combined analysis.

This new postcapture consumer changes no frozen job/analyzer or validity gate.
Fitters should receive its output only, never the combined input directory.
"""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'firesim'))
from rvv_identify_tk_review import validator,ELF
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def select_training(rows,corpus):
 expected=validator().canonical(corpus);need(len(rows)==len(expected)==1920,'All1920 rawrows')
 result=[]
 for r,w,c in zip(rows,expected,corpus['cases']):
  need(all(type(r.get(k))is type(v)and r[k]==v for k,v in w.items()),'Independent row/order/golden')
  for key in('start_cycle','issue_cycle','end_cycle'):need(type(r[key])is int and 0<=r[key]<2**64,'Actual integerphasecounter')
  need(r['start_cycle']<r['issue_cycle']<=r['end_cycle'],'Raw phaseorder')
  need(r['internal_split']==c['internal_split'],'Sourcegrouped partition')
  if c['internal_split']!='train':continue
  v=dict(r);v.update(cycles=r['end_cycle']-r['start_cycle'],issue_cycles=r['issue_cycle']-r['start_cycle'],drain_cycles=r['end_cycle']-r['issue_cycle'])
  need(v['cycles']==v['issue_cycles']+v['drain_cycles'],'Exact additivecyclephases')
  need(v['instret_delta']==v['issue_instret_delta']+v['drain_instret_delta'],'Actual additiveinstretphases')
  for key in('start_cycle','issue_cycle','end_cycle','mtime_before','mtime_after'):v.pop(key,None)
  v['phase_derivation']='Exact rawprogramcounter differences; no overhead/counter substitution'
  result.append(v)
 need(len(result)==1422,'Exactly1422TRAINrows; no errorfiltering')
 return result
def main(a):
 analysis,out=a.analysis.resolve(),a.output.resolve();need(not out.exists(),'New TRAINexport directory')
 p=analysis/'report.json';report=json.loads(p.read_text())
 need(report['schema']=='iris.rvv_identify_archive_analysis.v1'and report['pass']is True and report['archive_verified']is True and report['regions']==1920,'Strict successful fullarchive analyzer required')
 need([(r['task'],r['status'])for r in report['lifecycle']]==[('kill','passed'),('infrasetup','passed'),('runworkload','passed'),('kill','passed')],'Owned completefourphase lifecycle')
 for name,want in report['output_sha256'].items():need(sha(analysis/name)==want,'Changed strictanalysis output '+name)
 for source,want in report['input_sha256'].items():need(sha(source)==want,'Changed strictanalyzer source '+source)
 need(sha(analysis/'observed.elf')==ELF,'Exact1920ELF')
 corpus=json.loads((analysis/'corpus.json').read_text());validator().validate((analysis/'uartlog').read_text(),corpus)
 rows=[json.loads(x)for x in(analysis/'regions.jsonl').read_text().splitlines()];selected=select_training(rows,corpus)
 out.mkdir(parents=True);target=out/'regions.jsonl';target.write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in selected))
 result=dict(schema='iris.rvv_identify_TRAIN_phase_export.v2',status='passed',regions=1422,reserved_regions_excluded=498,reserved_timing_labels_excluded=True,absolute_timestamps_removed=True,issue_drain_and_total_deltas_preserved=True,no_validity_gate_relaxed=True,no_frozen_job_or_analyzer_modified=True,postcapture_consumer_change='Compute missingissue/drain deltas beforeabsolute timestampredaction; original fullstrictanalysis remains authoritative.',ELF_sha256=ELF,archive_sha256=report['archive_sha256'],frozen_split_sha256=corpus['frozen_split_sha256'],regions_sha256=sha(target),original_strict_analysis_report_sha256=sha(p),postcapture_exporter_sha256=sha(__file__),source_image_association_verified=False,physical_traffic_or_2percent_claimed=False)
 (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'status':'passed','TRAIN_rows':1422,'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--analysis',type=Path,required=True);p.add_argument('--output',type=Path,required=True);main(p.parse_args())
