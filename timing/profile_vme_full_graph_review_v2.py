#!/usr/bin/env python3
"""Close the full-graph proof and distinguish cycle prefixes from graph CSR reads."""
import argparse,hashlib,json,mmap,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 old=ROOT/'build/full-graph-VME-profile-v1';r=json.loads((old/'report.json').read_text())
 for name,h in {**r['input_sha256'],**{str(old/k):v for k,v in r['artifact_sha256'].items()}}.items():
  if sha(name)!=h:raise ValueError('Full graph evidence changed')
 bounded=ROOT/'build/full-graph-VME-buffered-bounded-v4';full=ROOT/'build/full-graph-VME-buffered-full-v4'
 for name in('stdout','stderr','features.jsonl'):
  if(bounded/name).read_bytes()!=(full/name).read_bytes():raise ValueError('History changes program/readback/features')
 prefix=[json.loads(x)for x in(full/'features.jsonl').read_text().splitlines()]
 if len(prefix)!=12 or any(type(x.get('csr'))is not int or x['csr']!=0xb00 for x in prefix):raise ValueError('Expected twelve actual mcycle prefix endpoints')
 with(full/'graph.json').open('rb')as stream:
  with mmap.mmap(stream.fileno(),0,access=mmap.ACCESS_READ)as mm:
   token=b'"counter_read_observations":';pos=mm.find(token)
   if pos<0 or mm.find(token,pos+1)>=0:raise ValueError('Unique captured counter observation block required')
   capture,unused=json.JSONDecoder().raw_decode(mm[pos+len(token):pos+len(token)+65536].decode())
 if capture.get('complete')is not True or len(capture['reads'])!=24:raise ValueError('All24 actual mcycle/minstret observations required')
 if sum(x['csr']==0xb00 for x in capture['reads'])!=12 or sum(x['csr']==0xb02 for x in capture['reads'])!=12:raise ValueError('Counter type coverage mismatch')
 observed={(x['hart'],x['sequence']):x for x in capture['reads']}
 for x in prefix:
  y=observed[x['hart'],x['sequence']]
  if any(x[k]!=y[k]for k in('value','pc','raw','csr','destination','read_cycle')):raise ValueError('Feature prefix differs from full graph CSR observation')
 timeout=ROOT/'build/full-graph-VME-timeout-control-v1/run.json';t=json.loads(timeout.read_text())
 if t.get('pass')is not False or t.get('timed_out')is not True or t.get('owned_process_cleanup_complete')is not True or t.get('exit_status')!=-15:raise ValueError('Actual owned timeout refusal/cleanup control missing')
 summary=json.loads((old/'summary.json').read_text());summary['execution_provenance'].update(cycle_feature_prefix_records=12,graph_counter_read_observations=24,graph_minstret_reads=12,bounded_full_cycle_prefix_bytes_identical=True)
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');(out/'trace.json').symlink_to(old/'trace.json')
 r.pop('bounded_full_all24_feature_prefixes_byteequal',None)
 r.update(schema='iris.actual_ELF_full_graph_profile_workflow.v2',bounded_full_all_cycle_feature_prefixes_byteequal=True,cycle_feature_prefix_records=12,captured_graph_counter_read_observations=24,captured_graph_minstret_reads=12,actual_owned_timeout_control=True,
  metadata_correction={'original_report':str(old/'report.json'),'original_report_sha256':sha(old/'report.json'),'note':'Original helper mislabeled24graphCSR observations as24featurestream records. Featurestream intentionally emits only12mcycle reads; all24graphCSR observations and6minstret pairs were independently validated. Native bytes/results/counters/traces are unchanged.'},
  trace_storage='Exact original immutable trace referenced by symlink; no event trimming or resampling.')
 r['input_sha256'].update({str(Path(__file__).resolve()):sha(__file__),str(old/'report.json'):sha(old/'report.json'),str(timeout):sha(timeout),str(full/'features.jsonl'):sha(full/'features.jsonl')})
 r['artifact_sha256']={x.name:sha(x)for x in out.iterdir()if x.is_file()};(out/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'pass':True,'counter_prefixes':12,'graph_CSR_observations':24,'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
