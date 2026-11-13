"""Compare every newly archived TRAIN978 region/phase, never reserved labels."""
import argparse,collections,hashlib,json,math,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def rows(p):return [json.loads(l)for l in Path(p).read_text().splitlines()]
def stats(values):
 a=sorted(abs(v)for v in values)
 return dict(count=len(a),median_signed_percent=statistics.median(values),median_absolute_percent=statistics.median(a),p90_absolute_percent=a[math.ceil(.9*len(a))-1],maximum_absolute_percent=max(a),within2=sum(v<=2 for v in a),quantile='nearest-rank-ceil')
def main(a):
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);train=a.train.resolve();model=a.model.resolve();build=a.build.resolve();packet=json.loads((train/'report.json').read_text());run=json.loads((model/'run.json').read_text());corpus=json.loads((build/'corpus.json').read_text());want=[r for r in corpus['cases']if r['internal_split']=='train'];hw=rows(train/'regions.jsonl');native=rows(model/'regions.jsonl')
 need(packet['status']=='passed'and packet['regions']==978 and packet['reserved_timing_labels_excluded']is True and packet['ELF_sha256']==sha(build/'guest.elf')and packet['regions_sha256']==sha(train/'regions.jsonl'),'Exact new TRAIN export')
 need(run['intentional_postmeasurement_debugger_stop']is True and run['normal_guest_exit_verified']is False,'Explicit controlledstop scope')
 need([n['case_id']for n in native]==[c['case_id']for c in corpus['cases']],'Exactall1320nativeIDs/order, no omitted rows')
 need(run['pass']is True and run['regions']==1320 and run['actual_CSR_ELF_endpoint_joins']==3960 and len(native)==1320,'Actual complete native1320/CSR readback')
 for p,h in {**run['input_sha256'],**run['output_sha256']}.items():need(sha(p)==h,'Actual native bound inputs/outputs')
 need([r['case_id']for r in hw]==[r['case_id']for r in want]and len(hw)==978,'Every TRAIN row/repetition canonicalorder');nm={r['case_id']:r for r in native};results=[];groups=collections.defaultdict(lambda:collections.defaultdict(list))
 for c,h in zip(want,hw):
  n=nm[c['case_id']];need(h['hart']==n['hart']==c['hart']and h['trial_id']==n['trial_id']==c['trial_id']and h['pass']is True and n['pass']is True and h['checksum']==n['checksum']==c['expected_checksum']and h['checked_words']==n['checked_words'],'Same compiledrole and independentwords')
  actual=[h['cycles'],h['issue_cycles'],h['drain_cycles']];pred=[n['end_cycle']-n['start_cycle'],n['issue_cycle']-n['start_cycle'],n['end_cycle']-n['issue_cycle']];need(all(type(v)is int and v>=0 for v in actual+pred)and actual[0]==sum(actual[1:]),'Typed actualhardwarephases')
  r=dict(case_id=c['case_id'],hart=c['hart'],kind=c['kind'],sew=c['sew'],lmul=c['lmul'],mode=c['mode'],n=c['n'],bytes=c['bytes'],trial_id=c['trial_id'],instret_mismatch=n['instret_delta']!=h['instret_delta'])
  for phase,y,p in zip(('total','issue','drain'),actual,pred):
   r[phase]=dict(hardware_cycles=y,native_cycles=p,signed_error_percent=(p-y)/y*100 if y else None)
   if y:
    for key in('all','hart'+str(c['hart']),'kind:'+c['kind'],'hart'+str(c['hart'])+':'+c['kind'],'sew:'+str(c['sew']),'lmul:'+str(c['lmul']),'n:'+str(c['n']),'mode:'+str(c['mode']),'trial:'+str(c['trial_id'])):groups[key][phase].append(r[phase]['signed_error_percent'])
  results.append(r)
 (out/'regions.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n'for r in results));report=dict(schema='iris.rvv_compute_asm_C12_TRAIN_comparison.v1',**{'pass':True},regions=978,all_TRAIN_rows_and_repetitions_retained=True,reserved_or_protected_labels_consumed=False,source_image_association_verified=False,timing_accuracy_certified=False,instret_mismatches=sum(r['instret_mismatch']for r in results),zero_duration_phase_errors_reported_as_null=True,groups={k:{phase:stats(v)for phase,v in ps.items()}for k,ps in sorted(groups.items())},input_sha256={str(p):sha(p)for p in[Path(__file__).resolve(),train/'report.json',train/'regions.jsonl',model/'run.json',model/'regions.jsonl',build/'ready.json',build/'corpus.json']},output_regions_sha256=sha(out/'regions.jsonl'))
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(pass_=True,regions=978,all=report['groups']['all'],report_sha256=sha(out/'report.json'))))
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__)
 for k in('train','model','build','output'):p.add_argument('--'+k,type=Path,required=True)
 main(p.parse_args())
