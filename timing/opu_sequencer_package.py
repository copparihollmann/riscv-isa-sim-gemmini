#!/usr/bin/env python3
"""Freeze/verify source, SDK, semantic oracle and independent whole-SoC control proof."""
import argparse,hashlib,importlib,json,os,re,shutil,stat,subprocess,sys,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];FINAL=R/'build/opu-sequencer-component-v2-final'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def package(out):
 if out.exists():raise ValueError('Preserve previous frozen OPU controller capsule')
 directories=['opu-sequencer-native-v3','opu-sequencer-semantic-v3','opu-sequencer-sdk-v1','opu-sequencer-reference-v1','opu-sequencer-rtl-v1','opu-sequencer-guests-v1','opu-sequencer-replay-v1','opu-sequencer-audit-v2'];files={p for d in directories for p in(R/'build'/d).rglob('*')if p.is_file()and p.suffix!='.gch'};files.update(p for p in(R/'timing').glob('opu_sequencer*')if p.is_file());roots=[R/'build'/d/'build.json'for d in ['opu-sequencer-native-v3','opu-sequencer-sdk-v1','opu-sequencer-reference-v1','opu-sequencer-rtl-v1','opu-sequencer-guests-v1']]+[R/'build/opu-sequencer-semantic-v3/report.json',R/'build/opu-sequencer-replay-v1/report.json']
 for receipt in roots:
  j=json.loads(receipt.read_text())
  for key in ['input_sha256','source_sha256']:
   for name,digest in j.get(key,{}).items():
    assert Path(name).is_file()and sha(name)==digest,('Changed qualified input',name);files.add(Path(name))
 contract=json.loads((R/'build/opu-sequencer-audit-v2/source-contract.json').read_text())
 for fact in contract['facts']:
  for source in fact['source']:
   p=Path(source['path']);assert sha(p)==source['sha256'];lines=p.read_text().splitlines();assert all(source['literal']in lines[n-1]for n in source['lines']);files.add(p)
 hardware=R/'hardware/manifest.json';files.add(hardware);pins=json.loads(hardware.read_text())['repositories']
 for entry in pins.values():
  assert re.fullmatch('[0-9a-f]{40}',entry['commit'])
  if entry.get('tracked_diff')and(R/'hardware'/entry['tracked_diff']).is_file():files.add(R/'hardware'/entry['tracked_diff'])
 manifest=R/'build/rtl-verilator/manifest.json';files.add(manifest);j=json.loads(manifest.read_text())
 for key in ['source_fir','source_annotations']:
  p=Path(j[key]);assert sha(p)==j[key+'_sha256'];files.add(p)
 # Source support needed to rebuild the recorded explicit-preload host adapter.
 support=R/'build/noc-full-router-component-v1-final/build/rtl-memory-return-path-v1-final/board/rtl-loader';files.update(p for p in support.rglob('*')if p.is_file())
 runtime={}
 for label,p in [('controller',R/'build/opu-sequencer-native-v3/opu-sequencer'),('sdk',R/'build/opu-sequencer-sdk-v1/benchmark'),('wholeRTL',R/'build/opu-sequencer-rtl-v1/simulator-opu-boundary')]:
  q=subprocess.run(['ldd',str(p)],capture_output=True,text=True,check=True);paths=[]
  for line in q.stdout.splitlines():
   m=re.search(r'(?:=>\s*)?(/\S+)\s+\(',line)
   if m:paths.append(Path(m[1]));files.add(Path(m[1]))
  runtime[label]={'ldd':q.stdout,'libraries':{str(p):sha(p)for p in paths}}
 include=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include');files.update(p for p in include.rglob('*')if p.is_file());consumer=R/'build/combined-frozen-35901887/manifest.json';files.add(consumer);out.mkdir();index=[];dedup={}
 for p in sorted(files):
  relative=p.relative_to(R)if p.is_relative_to(R)else Path('external')/str(p).lstrip('/');target=out/relative;target.parent.mkdir(parents=True,exist_ok=True);digest=sha(p);mode=stat.S_IMODE(p.stat().st_mode);key=(digest,mode)
  if key in dedup:os.link(dedup[key],target)
  else:shutil.copy2(p,target);dedup[key]=target
  index.append({'path':str(relative),'source_path':str(p),'bytes':target.stat().st_size,'mode':mode,'sha256':digest})
 report={'schema':'iris.opu_sequencer_frozen_capsule.v1','pass':True,'native_sha256':sha(R/'build/opu-sequencer-native-v3/opu-sequencer'),'SDK_archive_sha256':sha(R/'build/opu-sequencer-sdk-v1/sdk/libiris_opu_sequencer.a'),'source_identity':json.loads((R/'build/opu-sequencer-native-v3/build.json').read_text())['source_identity'],'semantic_proof':'build/opu-sequencer-semantic-v3/report.json','whole_rtl_replay':'build/opu-sequencer-replay-v1/report.json','source_contract':'build/opu-sequencer-audit-v2/source-contract.json','source_context_repositories':pins,'consumer_Spike_base_commit':json.loads(consumer.read_text())['base_git_sha'],'component_derived_from_Spike':False,'runtime_libraries':runtime,'artifact_count':len(index),'logical_bytes':sum(x['bytes']for x in index),'unique_file_bytes':sum(p.stat().st_size for p in dedup.values()),'artifacts':index,'scope':'Exact saved OuterProductSequencer + PipeScheduler physical control boundary; dispatcher, VRF data/bank allocator, backend registers and array external','whole_SoC_or_FireSim_image_certified':False,'source_checkout_association_verified':False,'heldout_2percent_timing_certified':False,'primary_shared_engine_or_campaign_changed':False,'idle_skipping':False,'hardware_contacted':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'capsule':str(out),'sha256':sha(out/'report.json'),'artifacts':len(index),'logical_bytes':report['logical_bytes'],'unique_file_bytes':report['unique_file_bytes']}))
def verify(out):
 report=json.loads((out/'report.json').read_text())
 for x in report['artifacts']:
  p=Path(x['path']);assert not p.is_absolute()and'..'not in p.parts;assert(out/p).stat().st_size==x['bytes']and stat.S_IMODE((out/p).stat().st_mode)==x['mode']and sha(out/p)==x['sha256'],x['path']
 contract=json.loads((out/report['source_contract']).read_text())
 for fact in contract['facts']:
  for source in fact['source']:
   old=Path(source['path']);p=out/(old.relative_to(R)if old.is_relative_to(R)else Path('external')/str(old).lstrip('/'));assert sha(p)==source['sha256'];lines=p.read_text().splitlines();assert all(source['literal']in lines[n-1]for n in source['lines'])
 native=out/'build/opu-sequencer-native-v3/opu-sequencer';sdk=out/'build/opu-sequencer-sdk-v1';assert sha(native)==report['native_sha256'];assert sha(sdk/'sdk/libiris_opu_sequencer.a')==report['SDK_archive_sha256'];libs=[out/'external'/str(Path(p).parent).lstrip('/')for p in report['runtime_libraries']['controller']['libraries']];os.environ['LD_LIBRARY_PATH']=os.pathsep.join(map(str,libs));sys.path.insert(0,str(out/'timing'))
 for name in ['opu_sequencer_oracle','opu_sequencer_check','opu_sequencer_replay']:sys.modules.pop(name,None)
 check=importlib.import_module('opu_sequencer_check');check.R=out;replay=importlib.import_module('opu_sequencer_replay');replay.R=out
 with tempfile.TemporaryDirectory(prefix='iris-opu-sequencer-verify-')as temp:
  scratch=Path(temp);oldargv=sys.argv;sys.argv=['qualified-controller-check','--native',str(native),'--output',str(scratch/'semantic')]
  try:check.main()
  finally:sys.argv=oldargv
  fresh=json.loads((scratch/'semantic/report.json').read_text());old=json.loads((out/report['semantic_proof']).read_text());assert fresh['stats']==old['stats']and fresh['edges']==old['edges']and fresh['instruction_count']==old['instruction_count'];assert(scratch/'semantic/seed0.stdout').read_bytes()==(out/'build/opu-sequencer-semantic-v3/seed0.stdout').read_bytes()
  bench=subprocess.run([str(sdk/'benchmark'),str(scratch/'semantic/inputs.txt')],capture_output=True,text=True,timeout=120);assert bench.returncode==0;bj=json.loads(bench.stdout);mix=1469598103934665603;count=0
  for line in(scratch/'semantic/seed0.stdout').open():
   for word in line.split()[1:]:
    if word!='x':mix=((mix^int(word))*1099511628211)&((1<<64)-1);count+=1
  assert all(p['defined_field_mix']==mix and p['defined_words']==count for p in bj['runs']);assert bj['lifecycle_refusals']==9 and bj['ready_hazard_settle_edges']==fresh['edges']
  profile=json.loads((native.parent/'ports.json').read_text());rtl=out/'build/opu-sequencer-rtl-v1';harts=replay.mailbox(rtl/'all-harts-vme.signature');records,physical,tbs=replay.capture(rtl/'all-harts-vme.stderr',profile);actualchecks=[]
  Oracle=importlib.import_module('opu_sequencer_oracle').Oracle
  for h in range(2):
   payload=''.join('step '+str(e)+' '+' '.join(str(i[f['name']])for f in profile['input'])+'\n'for e,i in enumerate(records[h]));q=subprocess.run([str(native),'--seed','41'],input=payload,capture_output=True,text=True,timeout=120);assert q.returncode==0;lines=q.stdout.splitlines();assert q.stdout==(out/'build/opu-sequencer-replay-v1'/f'hart{h}.stdout').read_text();checks=replay.compare_physical(profile,lines,physical[h]);oracle=Oracle();oraclechecks=0
   for e,(i,goldrow,line)in enumerate(zip(records[h],physical[h],lines)):
    expected=oracle.evaluate(i)
    for f,gold,word in zip(profile['output'],goldrow,line.split()[1:]):
     if word!='x':assert expected[f['name']]==gold;oraclechecks+=1
    oracle.commit(i)
   assert checks==oraclechecks;actualchecks.append({'hart':h,'edges':len(lines),'defined_checks':checks,'dispatches':len(oracle.dispatches),'stats':dict(oracle.stats)})
  # Five real physical output mutations must enter the same full comparator.
  frozen=json.loads((out/report['whole_rtl_replay']).read_text())
  for mutation in frozen['checker_corruptions']:
   changed=[x[:]for x in physical[0]];f=next(f for f in profile['output']if f['name']==mutation['field']);changed[mutation['edge']][f['index']]=mutation['corrupted']
   try:replay.compare_physical(profile,(out/'build/opu-sequencer-replay-v1/hart0.stdout').read_text().splitlines(),changed)
   except ValueError:pass
   else:raise ValueError('Missed physical checker corruption')
 print(json.dumps({'pass':True,'capsule_sha256':sha(out/'report.json'),'artifacts_verified':len(report['artifacts']),'independent_semantic_edges':fresh['edges'],'independent_semantic_instructions':fresh['instruction_count'],'semantic_corruption_refusals':len(fresh['checker_corruptions']),'input_lifecycle_refusals':len(fresh['negative_controls'])+bj['lifecycle_refusals'],'whole_RTL_harts':actualchecks,'raw_guest_mailbox':harts,'physical_corruption_refusals':5,'independent_SDK_mix':mix,'hardware_contacted':False}))
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=FINAL);p.add_argument('--verify',action='store_true');a=p.parse_args();(verify if a.verify else package)(a.output.resolve())
if __name__=='__main__':main()
