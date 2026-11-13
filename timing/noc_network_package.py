#!/usr/bin/env python3
"""Freeze and independently verify complete-NoC source, SDK and RTL evidence."""
import argparse,hashlib,importlib,json,os,re,shutil,subprocess,sys,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];FINAL=R/'build/noc-network-component-v1-final'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for part in iter(lambda:f.read(1024*1024),b''):h.update(part)
 return h.hexdigest()
def profile_header(root):
 j=json.loads((root/'build/noc-network-source-v2/extraction.json').read_text());inputs=[x for x in j['physical_ports']if x['direction']=='input'];outputs=[x for x in j['physical_ports']if x['direction']=='output'];text='#pragma once\n#include <cstddef>\nnamespace iris::noc {\ninline constexpr std::size_t network_input_count='+str(len(inputs))+';\ninline constexpr std::size_t network_output_count='+str(len(outputs))+';\n'
 for name,fields in [('InputField',inputs),('OutputField',outputs)]:text+='enum class Network'+name+' : std::size_t {\n'+',\n'.join(x['name'].lstrip('_')+'='+str(x['index'])for x in fields)+'\n};\n'
 text+='}\n';assert text==(root/'timing/noc_network_schema.hpp').read_text(),'Physical source and compiled API schema mismatch'
def package(out):
 if out.exists():raise ValueError('Refuse to overwrite complete-NoC capsule')
 profile_header(R);files=set();directories=[R/'build'/n for n in ['noc-network-source-v1','noc-network-source-v2','noc-network-native-v3','noc-network-sdk-v1','noc-network-reference-v1','noc-network-replay-v3','noc-network-rtl-v1','noc-network-accept-v1','noc-network-guests-v1','noc-network-graph-v2','noc-network-observer-build-attempt1','rtl-memory-return-path-v1-final','noc-full-router-component-v1-final','noc-router-component-v1-final']]
 for directory in directories:files.update(p for p in directory.rglob('*')if p.is_file()and p.suffix!='.gch')
 files.update(p for pattern in ['noc_network*','noc_router*','noc_arbiter*']for p in(R/'timing').glob(pattern)if p.is_file());roots=[R/'build'/n/'build.json'for n in ['noc-network-native-v3','noc-network-sdk-v1','noc-network-reference-v1','noc-network-rtl-v1','noc-network-guests-v1']]
 for p in roots:
  j=json.loads(p.read_text())
  for key in ['input_sha256','source_sha256']:
   for name,d in j.get(key,{}).items():assert Path(name).is_file()and sha(name)==d,('Changed build input',name);files.add(Path(name))
 contract=json.loads((R/'build/noc-network-source-v2/routing-contract.json').read_text())
 for obj in [contract['annotation'],contract['FIR_decoder_input_mapping'],*contract['edgeprops'].values()]:assert sha(obj['path'])==obj['sha256'];files.add(Path(obj['path']))
 hardware=R/'hardware/manifest.json';files.add(hardware);pins=json.loads(hardware.read_text())['repositories']
 for entry in pins.values():
  if entry.get('tracked_diff')and(R/'hardware'/entry['tracked_diff']).is_file():files.add(R/'hardware'/entry['tracked_diff'])
 consumer=R/'build/combined-frozen-35901887/manifest.json';files.add(consumer);c=json.loads(consumer.read_text());libraries={}
 for label,binary in [('network',R/'build/noc-network-native-v3/noc-network'),('benchmark',R/'build/noc-network-sdk-v1/benchmark'),('wholeRTL',R/'build/noc-network-rtl-v1/simulator-network-boundary')]:
  q=subprocess.run(['ldd',str(binary)],capture_output=True,text=True,check=True);paths=[]
  for line in q.stdout.splitlines():
   m=re.search(r'(?:=>\s*)?(/\S+)\s+\(',line)
   if m:paths.append(Path(m[1]));files.add(Path(m[1]))
  libraries[label]={'ldd':q.stdout,'libraries':{str(p):sha(p)for p in paths}}
 # Preserve the matching Verilator runtime headers/implementation, including
 # non-system dependencies of generated native and observer sources.
 include=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include');files.update(p for p in include.rglob('*')if p.is_file())
 out.mkdir();index=[]
 for p in sorted(files):
  relative=p.relative_to(R)if p.is_relative_to(R)else Path('external')/str(p).lstrip('/');target=out/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target);index.append({'path':str(relative),'source_path':str(p),'bytes':target.stat().st_size,'sha256':sha(target)})
 acceptance=R/'build/noc-network-accept-v1/report.json';graph=R/'build/noc-network-graph-v2/graph.json';report={'schema':'iris.complete_noc_frozen_capsule.v1','pass':True,'source_identity':json.loads((R/'build/noc-network-native-v3/build.json').read_text())['source_identity'],'native_sha256':sha(R/'build/noc-network-native-v3/noc-network'),'SDK_archive_sha256':sha(R/'build/noc-network-sdk-v1/sdk/libiris_noc.a'),'acceptance':str(acceptance.relative_to(R)),'acceptance_sha256':sha(acceptance),'source_graph':str(graph.relative_to(R)),'source_graph_sha256':sha(graph),'source_context_repositories':pins,'spike_consumer_context':{'base_commit':c['base_git_sha'],'manifest_sha256':sha(consumer),'NoC_component_derived_from_Spike':False},'runtime_libraries':libraries,'artifact_count':len(index),'total_bytes':sum(x['bytes']for x in index),'artifacts':index,'scope':'Complete saved configured A/C/D+B/E NoC and26adaptors; external physical TL/cache/memory/serial/CDC boundaries','source_checkout_or_Ethan_image_association':False,'full_SoC_or_heldout_2percent_certification':False,'primary_shared_engine_or_frozen_campaign_changed':False,'idle_skipping':False,'hardware_contacted':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'capsule':str(out),'sha256':sha(out/'report.json'),'artifacts':len(index),'bytes':report['total_bytes']}))
def verify(out):
 j=json.loads((out/'report.json').read_text())
 for x in j['artifacts']:
  p=Path(x['path']);assert not p.is_absolute()and'..'not in p.parts;assert(out/p).stat().st_size==x['bytes']and sha(out/p)==x['sha256'],x['path']
 profile_header(out);assert sha(out/j['acceptance'])==j['acceptance_sha256']and sha(out/j['source_graph'])==j['source_graph_sha256'];sys.path.insert(0,str(out/'timing'))
 for name in ['noc_network_check','noc_network_accept','noc_router_check']:sys.modules.pop(name,None)
 check=importlib.import_module('noc_network_check');accept=importlib.import_module('noc_network_accept');accept.R=out;accept.REPLAY=out/'build/noc-network-replay-v3';accept.NATIVE=out/'build/noc-network-native-v3/noc-network';accept.SDK=out/'build/noc-network-sdk-v1';accept.LOCAL=out/'build/noc-router-component-v1-final';accept.CAP=out/'build/rtl-memory-return-path-v1-final';check.R=out;check.RTL=out/'build/noc-network-rtl-v1';assert sha(accept.NATIVE)==j['native_sha256'];libs=[out/'external'/str(Path(p).parent).lstrip('/')for p in j['runtime_libraries']['network']['libraries']];os.environ['LD_LIBRARY_PATH']=os.pathsep.join(map(str,libs));cases=[];frozen=json.loads((out/j['acceptance']).read_text())
 with tempfile.TemporaryDirectory(prefix='iris-complete-noc-verify-')as temp:
  scratch=Path(temp)
  for case in ['original9','control8','fenced9','peer','coherent']:
   body=(accept.REPLAY/(case+'-step.input')).read_text();q=accept.run([accept.NATIVE,'--seed','1'],body,scratch,case);assert q.returncode==0 and q.stdout==(accept.REPLAY/(case+'-step.stdout')).read_text();proof=check.compare(case,scratch/(case+'.stdout'));accept.architecture(case)
   if case in ['original9','control8','fenced9']:accept.subset(case,scratch)
   if case in ['control8','coherent']:
    expected=next(x['independent_whole_RTL_mix64']for x in frozen['readiness_revision_and_speed']if x['case']==case);q=accept.run([accept.SDK/'benchmark',accept.REPLAY/(case+'-step.input'),'2','1','step'],'',scratch,'benchmark-'+case);assert q.returncode==0 and all(x['defined_field_mix64']==expected for x in json.loads(q.stdout)['passes']);q=accept.run([accept.SDK/'benchmark',accept.REPLAY/(case+'-step.input'),'1','1','revised'],'',scratch,'revised-'+case);assert q.returncode==0 and json.loads(q.stdout)['passes'][0]['defined_field_mix64']==expected
   if case=='original9':assert accept.snapshot(scratch,j['source_identity'])['exact_continuation_edges']==19999
   cases.append({'case':case,**proof});print(json.dumps({'verified_case':case,'edges':proof['edges']}),flush=True)
  q=accept.run([accept.SDK/'benchmark','selftest',accept.REPLAY/'control8-step.input',scratch/'lifecycle.snapshot'],'',scratch,'lifecycle');assert q.returncode==0 and json.loads(q.stdout)['lifecycle_rejections']==8;assert len(accept.corruptions(scratch))==5
 print(json.dumps({'pass':True,'capsule_sha256':sha(out/'report.json'),'artifacts_verified':len(j['artifacts']),'actual_reset_replays':cases,'active_snapshot_continuation_edges':19999,'handwritten_subset_edges':52806,'invalid_lifecycle_rejections':8,'output_corruptions':5,'hardware_contacted':False}))
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=FINAL);p.add_argument('--verify',action='store_true');a=p.parse_args();(verify if a.verify else package)(a.output.resolve())
if __name__=='__main__':main()
