#!/usr/bin/env python3
"""Close exact campaign inputs, all repetitions, compiled bodies and guards."""
import argparse,hashlib,importlib.util,json,re
from pathlib import Path
from validate import validate
R=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--runs',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();b=a.build.resolve();o=a.output.resolve()
 if o.exists():raise ValueError('Fresh closure directory required')
 o.mkdir();build=json.loads((b/'build.json').read_text());corpus=json.loads((b/'corpus.json').read_text());assert sha(b/'campaign.elf')==build['elf_sha256'];assert sha(b/'campaign.disassembly')==build['disassembly_sha256']
 for name,d in build['input_sha256'].items():assert sha(name)==sha(b/'inputs'/d)==d,('Changed build input',name)
 for name,d in corpus['parent_source_sha256'].items():assert sha(R/name)==d
 def load(name,path):
  spec=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
 baseline=json.loads((R/'benchmarks/calibration-corpus.json').read_text());load('campaign_closure_baseline_golden',R/'benchmarks/golden.py').verify(baseline)
 canonical={'baseline':baseline['cases'],'distribution':load('campaign_closure_distribution',R/'benchmarks/v2/cases.py').cases(),'memory':load('campaign_closure_memory',R/'benchmarks/memory_routes/cases.py').cases()};parent_rows={(suite,c['case_id']):c for suite,rows in canonical.items()for c in rows}
 groups={};kinds=set();masks=set();matrix={'vme_int','vme_fp8','row_read','row_write','tile_zero','vme_memory'}
 for c in corpus['cases']:
  parent=parent_rows[(c['suite'],c['parent_case_id'])]
  for key,value in parent.items():assert (c['parent_case_id']if key=='case_id'else c[key])==value,('Changed parent semantics',key,c['case_id'])
  groups.setdefault((c['suite'],c['parent_case_id']),[]).append(c['trial_id']);masks.add(c['mask']);kinds.add(c.get('kind',c.get('kernel')))
  if c.get('kind')in matrix or c.get('kernel')=='vme_mm':assert not(c['mask']&4)
  if c.get('kind')=='pipeline_vme':assert c['metadata']['producer_hart']==2 and c['metadata']['compute_hart']in [0,1]
  if c.get('kind')=='vme_refusal' or c.get('kernel')=='refuse_vme':assert c['mask']==4
  assert c['case_id']==c['parent_case_id']+'.trial.'+str(c['trial_id'])
 for values in groups.values():assert sorted(values)==list(range(corpus['trials']))
 proofs=[];inputs={str(b/'build.json'):sha(b/'build.json'),str(b/'corpus.json'):sha(b/'corpus.json'),str(b/'campaign.elf'):sha(b/'campaign.elf'),str(b/'campaign.disassembly'):sha(b/'campaign.disassembly')}
 for run in a.runs:
  run=run.resolve();j=json.loads((run/'run.json').read_text());assert j['exit_status']==0 and j['functional_checks_passed'];assert sha(run/'run.stdout')==j['stdout_sha256'] and sha(run/'run.stderr')==j['stderr_sha256'];text=(run/'run.stdout').read_text();proof=validate(text,corpus);proof.update(seed=j['seed'],host_seconds=j['host_seconds'],run_receipt_sha256=sha(run/'run.json'));proofs.append(proof)
  for name,d in j['input_sha256'].items():assert sha(name)==sha(run/'inputs'/d)==d;inputs[name]=d
  for name in ['run.json','run.stdout','run.stderr','repetition-summary.json']:
   if (run/name).is_file():inputs[str(run/name)]=sha(run/name)
 lines=text.splitlines();index=next(n for n,line in enumerate(lines)if line.startswith('IRIS_REGION '));row=json.loads(lines[index].split(' ',1)[1]);mutations=[]
 for label,change in [('checksum',lambda x:x.update(checksum=x['checksum']+1)),('parent',lambda x:x.update(parent_case_id='wrong-parent')),('trial',lambda x:x.update(trial_id=99))]:
  changed=dict(row);change(changed);copy=list(lines);copy[index]='IRIS_REGION '+json.dumps(changed);mutations.append((label,'\n'.join(copy)))
 mutations.extend([('missing-region','\n'.join(lines[:index]+lines[index+1:])),('duplicate-region',text+'\n'+lines[index]+'\n'),('missing-completion','\n'.join(x for x in lines if not x.startswith('IRIS_BATCH_DONE '))),('fatal',text+'\nIRIS_FATAL {"hart":2,"cause":2}\n')]);guards=[]
 for name,body in mutations:
  try:validate(body,corpus)
  except(ValueError,KeyError,TypeError)as error:guards.append({'mutation':name,'rejection':str(error)})
  else:raise AssertionError('Accepted corrupted campaign '+name)
 bodies=[];text=(b/'campaign.disassembly').read_text();headers=list(re.finditer(r'^([0-9a-f]+) <([^>]+)>:\n',text,re.M))
 for n,m in enumerate(headers):
  body=text[m.start():headers[n+1].start()if n+1<len(headers)else len(text)];bodies.append({'symbol':m[2],'address':int(m[1],16),'disassembly_sha256':hashlib.sha256(body.encode()).hexdigest()})
 hardware=json.loads((R/'hardware/manifest.json').read_text());pins={name:{k:v for k,v in values.items()if k in ['commit','tracked_modified','tracked_diff_sha256','chipyard_declared_commit']}for name,values in hardware['repositories'].items()};combined=R/'build/combined-frozen-35901887/manifest.json';combined_record=json.loads(combined.read_text());pins['spike_combined']={'base_commit':combined_record['base_git_sha'],'source_overlay_sha256':combined_record['source_overlay_sha256'],'manifest_sha256':sha(combined),'binary_sha256':combined_record['binary_sha256'],'uart_sha256':combined_record['uart_sha256']}
 for path in [R/'hardware/manifest.json',R/'hardware/dtypes.json',R/'hardware/memory-paths.json',R/'benchmarks/golden.py',combined,R/'build/combined-frozen-35901887/source-overlay.patch',Path(__file__),Path(__file__).with_name('README.md'),Path(__file__).with_name('summarize.py'),Path(__file__).with_name('capture-checklist.json')]:inputs[str(path)]=sha(path)
 (o/'inputs').mkdir()
 for name,d in inputs.items():
  target=o/'inputs'/d
  if not target.exists():target.write_bytes(Path(name).read_bytes())
 report={'schema':'iris.broad_campaign_closure.v1','pass':True,'build_sha256':sha(b/'build.json'),'elf_sha256':sha(b/'campaign.elf'),'corpus_sha256':sha(b/'corpus.json'),'parent_cases':len(groups),'trial_cases':len(corpus['cases']),'regions_per_run':corpus['expected_region_count'],'trials':corpus['trials'],'parent_sources_unchanged':True,'heldout_timing_consumed':False,'all_masks':sorted(masks),'source_preservation':build['source_preservation'],'compiled_function_bodies':bodies,'functional_runs':proofs,'negative_console_guards':guards,'source_repositories':pins,'input_sha256':inputs,'loaded_image_association_verified':False,'calibration_usable':False,'timing_certified':False,'hardware_contacted':False};(o/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'report_sha256':sha(o/'report.json'),'runs':len(proofs),'regions_per_run':corpus['expected_region_count'],'negative_guards':len(guards),'compiled_bodies':len(bodies)}))
if __name__=='__main__':main()
