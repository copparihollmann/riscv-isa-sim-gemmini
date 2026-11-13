#!/usr/bin/env python3
"""Freeze raw source-unit capacity evidence and independently replay its reader."""
import argparse,hashlib,importlib.util,json,os,shutil,stat,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1];REFERENCE=R/'build/saturn-timing-component-v1-final';FINAL=R/'build/saturn-timing-load-burst-component-v1-final'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rel(p):return p.relative_to(R)if p.is_relative_to(R)else Path('external')/str(p).lstrip('/')
def package(out):
 if out.exists():raise ValueError('Preserve previous burst capsule')
 ref=json.loads((REFERENCE/'report.json').read_text());mapping={x['source_path']:x['path']for x in ref['artifacts']};dirs=[R/'build/saturn-timing-load-burst-v3',R/'build/saturn-timing-load-burst-reader-v1'];files={p for d in dirs for p in d.rglob('*')if p.is_file()};files.update(p for p in(R/'timing').glob('saturn_timing_load_burst*')if p.is_file());depinputs={}
 for receipt in list(files):
  if receipt.suffix!='.json':continue
  j=json.loads(receipt.read_text())
  if not isinstance(j,dict):continue
  for name,digest in j.get('input_sha256',{}).items():
   p=Path(name)
   if p.is_relative_to(REFERENCE):assert sha(p)==digest;depinputs[name]={'path':str(p.relative_to(REFERENCE)),'sha256':digest}
   elif name in mapping:assert sha(REFERENCE/mapping[name])==digest;depinputs[name]={'path':mapping[name],'sha256':digest}
   else:assert p.is_file()and sha(p)==digest;files.add(p)
 out.mkdir();index=[];dedup={}
 for p in sorted(files):
  target=out/rel(p);target.parent.mkdir(parents=True,exist_ok=True);digest=sha(p);mode=stat.S_IMODE(p.stat().st_mode);key=(digest,mode)
  if key in dedup:os.link(dedup[key],target)
  else:shutil.copy2(p,target);dedup[key]=target
  index.append({'path':str(rel(p)),'source_path':str(p),'bytes':target.stat().st_size,'mode':mode,'sha256':digest})
 report={'schema':'iris.saturn_restore_burst_frozen_capsule.v1','pass':True,'reference_dependency':{'path':str(REFERENCE),'report_sha256':sha(REFERENCE/'report.json'),'input_mapping':depinputs},'probe':'build/saturn-timing-load-burst-v3/report.json','reader':'build/saturn-timing-load-burst-reader-v1/report.json','artifact_count':len(index),'artifacts':index,'source_RTL_or_model_objects_modified':False,'internal_state_injection':False,'full_scalar_CSR_execution_claimed':False,'physical_FPGA_fault_or_cause_identified':False,'hardware_contacted':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'artifacts':len(index),'report_sha256':sha(out/'report.json')}))
def verify(out):
 report=json.loads((out/'report.json').read_text());ref=Path(report['reference_dependency']['path']);assert sha(ref/'report.json')==report['reference_dependency']['report_sha256']
 for x in report['artifacts']:
  path=out/x['path'];assert path.is_relative_to(out)and path.stat().st_size==x['bytes']and stat.S_IMODE(path.stat().st_mode)==x['mode']and sha(path)==x['sha256'],x['path']
 for x in report['reference_dependency']['input_mapping'].values():assert sha(ref/x['path'])==x['sha256']
 helper=out/'timing/saturn_timing_load_burst_read.py';spec=importlib.util.spec_from_file_location('frozen_independent_burst_reader',helper);reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader);base=out/'build/saturn-timing-load-burst-v3';probe=json.loads((out/report['probe']).read_text());independent=json.loads((out/report['reader']).read_text());results=[]
 for citation in[probe['reader_source_map_citation'],probe['core_CSR_gate_citation']]:
  path=ref/Path(citation['path']).relative_to(ref);assert sha(path)==citation['sha256']and citation['literal']in path.read_text()
 for row in probe['results']:
  command=[str(base/'load-burst'),str(row['lmul'].bit_length()-1),str(row['seed'])];q=subprocess.run(command,capture_output=True,text=True,timeout=30);assert q.returncode==0,q.stderr;label='m'+str(row['lmul'])+'-seed'+str(row['seed']);assert q.stdout==(base/(label+'.stdout')).read_text();actual=reader.inspect(q.stdout);assert actual==next(x for x in independent['results']if x['lmul']==row['lmul']and x['seed']==row['seed']);results.append(actual)
 for mutation in independent['corruption_refusals']:
  text=(out/'build/saturn-timing-load-burst-reader-v1'/(mutation['name']+'.stdout')).read_text()
  try:reader.inspect(text)
  except ValueError as error:assert str(error)==mutation['reason']
  else:raise ValueError('Missed frozen burst corruption')
 print(json.dumps({'pass':True,'capsule_sha256':sha(out/'report.json'),'artifacts_verified':len(report['artifacts']),'source_cases':len(results),'guarded_capacity_edges':sum(x['hold_edges']for x in results),'physical_VRF_word_checks':sum(x['VRF_word_checks']for x in results),'reader_corruption_refusals':len(independent['corruption_refusals']),'FPGA_fault_cause_identified':False,'hardware_contacted':False}))
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=FINAL);p.add_argument('--verify',action='store_true');a=p.parse_args();(verify if a.verify else package)(a.output.resolve())
if __name__=='__main__':main()
