#!/usr/bin/env python3
"""Freeze the two-Shuttle + Rocket source component and precise qualification."""
import argparse,hashlib,json,os,shutil,stat
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for c in iter(lambda:f.read(1048576),b''):h.update(c)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve()
 if out.exists():raise ValueError('fresh capsule required')
 paths=R/'build/shuttle-memory-paths-native-v6';system=R/'build/shuttle-memory-system-native-v6';parent=R/'build/shuttle-memory-parent-sdk-v1';source=R/'build/shuttle-memory-source-v4';graph=R/'build/shuttle-memory-graph-v3';cases={n:R/('build/shuttle-memory-system-'+stem+'-final-v1')for n,stem in [('functional','check'),('context','context'),('guards','guards')]};rows={}
 for name,d in cases.items():
  j=read(d/'report.json');assert j['exit_status']==0 and j['case']==name
  rows[name]=[json.loads(x)for x in(d/'check.stdout').read_text().splitlines()];assert rows[name][-1]['status']=='passed'
 assert rows['functional'][-1]['checks']==104802 and rows['context'][-1]['constructor_bad_alloc_injections']==3447 and rows['guards'][-1]['unknown_field_controls']==316
 assert all(x['passed']for x in read(cases['functional']/'report.json')['negative_controls'])
 files={};checked={};metadata=[]
 def add(p,expected=None):
  p=Path(p).absolute();h=sha(p)
  if expected is not None and h!=expected:raise ValueError('input changed '+str(p))
  files[str(p)]={'sha256':h,'bytes':p.stat().st_size,'mode':stat.S_IMODE(p.stat().st_mode)}
 def tree(p):
  for q in sorted(Path(p).rglob('*')):
   if q.is_file():add(q)
 def meta(p):
  j=read(p);add(p);metadata.append(str(p))
  for k in ['input_sha256','compiled_dependency_sha256','source_sha256','source_files']:
   for n,h in j.get(k,{}).items():
    if isinstance(h,str)and len(h)==64:
     q=Path(n);q=q if q.is_absolute()else R/q;add(q,h);checked[str(q)]=h
  return j
 for q in(R/'timing').glob('shuttle_memory_system*'):
  if q.is_file():add(q)
 for d in [source,graph,paths,system,parent,*cases.values()]:tree(d)
 for p in [source/'extraction.json',graph/'graph.json',paths/'build.json',system/'build.json',parent/'report.json',parent/'cache/build.json',parent/'adapters/build.json',parent/'fabric/build.json',parent/'system/build.json',*[d/'report.json'for d in cases.values()]]:meta(p)
 sy=read(system/'build.json')
 for p in sy['required_static_libraries_in_link_order']:add(p)
 for d in sy['required_include_directories']:
  for p in Path(d).glob('*.hpp'):add(p)
 lp=R/'build/serial-memory-context-sdk-v2/fased/sdk';add(lp/'libiris_fased_service.a');meta(lp.parent/'build.json')
 for q in lp.glob('*.hpp'):add(q)
 parents=[]
 cap=R/'build/serial-memory-system-component-v1';j=read(cap/'report.json');add(cap/'report.json','4f644f1866fc9579c69e541f8467afcd73abfece97c099886cd5ec56f4c09b07')
 for item in j['artifacts']:assert sha(cap/item['snapshot'])==item['sha256']
 parents.append({'capsule':str(cap),'report_sha256':sha(cap/'report.json'),'artifacts_verified':len(j['artifacts'])})
 for item in j['hash_bound_child_source_closures']:
  child=Path(item['capsule']);cj=read(child/'report.json');add(child/'report.json',item['report_sha256'])
  for artifact in cj['artifacts']:assert sha(child/artifact['snapshot'])==artifact['sha256']
  parents.append({**item,'artifacts_verified':len(cj['artifacts'])})
 # Retain failed fixtures and constructor pool observation, without promoting
 # them to passing controls or changing their historical input associations.
 for d in ['shuttle-memory-system-check-v5','shuttle-memory-system-check-v6','shuttle-memory-system-check-v9','shuttle-memory-system-context-v2']:
  for q in(R/'build'/d).glob('*'):
   if q.is_file()and q.suffix in ['.json','.stdout','.stderr']:add(q)
 out.mkdir();(out/'cas').mkdir();artifacts=[]
 for n,item in sorted(files.items()):
  q=Path(n);blob=out/'cas'/(item['sha256']+'-'+format(item['mode'],'o'));target=out/'snapshot'/n.lstrip('/');target.parent.mkdir(parents=True,exist_ok=True)
  if not blob.exists():shutil.copyfile(q,blob);blob.chmod(item['mode']);assert sha(blob)==item['sha256']
  os.link(blob,target);artifacts.append({'original':n,'snapshot':str(target.relative_to(out)),**item})
 result={'schema':'iris.three_hart_source_memory_system_capsule.v1','status':'passed_source_physical_component','SDK_path':str(system/'sdk'),'source_identity':sy['source_identity'],'library_sha256':sy['library_sha256'],'required_include_directories':sy['required_include_directories'],'required_static_libraries_in_link_order':sy['required_static_libraries_in_link_order'],'FASED_SDK_path':str(lp),'physical_fields':{'inputs':sy['input_count'],'outputs':sy['output_count']},'source_relative_periods':{'both_shuttle_memory':2,'rocket':2,'uncore':2,'bringup':1,'serial':10},'source_checks':rows,'negative_controls':read(cases['functional']/'report.json')['negative_controls'],'parent_closures':parents,'checked_input_sha256':checked,'metadata_checked':metadata,'scope_limits':['Physical clients only; actual three CPU pipelines/Zephyr integration remains separate.','Strict unreset RPQ refusal remains default; fixture accepted-load warmup is not a hardware boot guarantee.','TCM byte definedness derives accepted source Put masks; full internal four-state knownness and CPU LSU trap/PMA/PMP fidelity are not claimed.','Explicit ideal-host backing, reset-only diagnostic suppression and LP30/30/16/16 are fixture inputs, never admitted defaults.','Original source FIFO/credit/NoC/coherence/clock logic retained, but multi-elaboration whole-image equivalence and loaded image association remain unqualified.'],'artifacts':artifacts,'artifact_count':len(artifacts),'bytes_before_CAS_dedup':sum(x['bytes']for x in artifacts),'hardware_contacted':False,'primary_or_frozen_epochs_changed':False,'source_image_association_verified':False,'timing_certified':False,'calibration_usable':False,'full_model_available':False}
 (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'report_sha256':sha(out/'report.json'),'artifacts':len(artifacts),'checked_inputs':len(checked),'verified_parent_artifacts':sum(x['artifacts_verified']for x in parents)}))
if __name__=='__main__':main()
