#!/usr/bin/env python3
"""Compare active source-edge cost with identical independent whole-RTL outputs."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();candidate=a.candidate.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);sdk=candidate/'sdk';qualified=json.loads((sdk/'build.json').read_text());assert sha(sdk/'benchmark')==qualified['benchmark_sha256'];runs=[];inputs=[Path(__file__),sdk/'benchmark',sdk/'build.json']
 for case,h in[('vme',0),('rvv',0),('rvv',2),('shared-fpu',2),('fpcomp',0)]:
  replay=R/'build/saturn-timing-replay-v2'/case;ports=replay/f'hart{h}.input';masks=replay/f'hart{h}.masks.bin';window=replay/f'hart{h}.benchmark-window.json';j=json.loads(window.read_text());command=[str(sdk/'benchmark'),'rocket'if h==2 else'compute',str(h),str(ports),str(masks),'3'];start=time.monotonic();q=subprocess.run(command,capture_output=True,text=True,timeout=180);label=case+'-h'+str(h);(out/(label+'.stdout')).write_text(q.stdout);(out/(label+'.stderr')).write_text(q.stderr)
  if q.returncode:raise ValueError('Direct active stepping failed '+label+' '+q.stderr)
  result=json.loads(q.stdout)
  for r in result['runs']:
   assert r['qualified_field_mix64']==j['qualified_field_mix64']and r['qualified_words']==j['qualified_words']
  assert result['executed_prefix_edges']==j['first_EX_candidate_edge']and result['timed_active_guest_edges']==j['end_edge_exclusive']-j['first_EX_candidate_edge'];inputs.extend([ports,masks,window,replay/'report.json']);baseline=R/'build/saturn-timing-active-bench-v1'/(label+'.json');comparison=None
  if baseline.is_file():
   old=json.loads(baseline.read_text());comparison={'frozen_full_reference_receipt':str(baseline),'sha256':sha(baseline),'full_reference_edges_per_second':[r['edges_per_second']for r in old['result']['runs']]};inputs.append(baseline)
  runs.append({'case':case,'hart':h,'argv':command,'host_seconds_total':time.monotonic()-start,'result':result,'comparison':comparison})
 report={'schema':'iris.saturn_numeric_substitution_active_speed.v1','pass':True,'candidate_source_identity':qualified['source_identity'],'runs':runs,'input_sha256':{str(p):sha(p)for p in inputs},'in_process_stepping':True,'all_reset_boot_prefix_edges_executed':True,'all_active_guest_edges_executed':True,'idle_skipping':False,'text_IO_outside_timed_interval':True,'source_debug_formatting_included':True,'independent_whole_RTL_qualified_field_mix_verified':True,'SoC_MIPS_or_heldout_timing_claimed':False,'hardware_contacted':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'runs':[{'case':r['case'],'hart':r['hart'],'result':r['result']}for r in runs],'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
