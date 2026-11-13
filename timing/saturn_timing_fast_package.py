#!/usr/bin/env python3
"""Freeze the smallest numeric substitution with an explicit immutable dependency."""
import argparse,hashlib,importlib,json,os,shutil,stat,subprocess,sys,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];REFERENCE=R/'build/saturn-timing-component-v1-final';FINAL=R/'build/saturn-timing-fast-component-v1-final'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def rel(p):return p.relative_to(R)if p.is_relative_to(R)else Path('external')/str(p).lstrip('/')
def check_inventory(folder,report):
 for x in report['artifacts']:
  p=Path(x['path']);assert not p.is_absolute()and'..'not in p.parts;target=folder/p;assert target.stat().st_size==x['bytes']and stat.S_IMODE(target.stat().st_mode)==x['mode']and sha(target)==x['sha256'],str(target)
def package(out):
 if out.exists():raise ValueError('Preserve previous candidate closure')
 reference=json.loads((REFERENCE/'report.json').read_text());refmap={x['source_path']:REFERENCE/x['path']for x in reference['artifacts']};files=set();names=['saturn-timing-fast-v1','saturn-timing-fast-numeric-proof-v1','saturn-timing-fast-replay-v1','saturn-timing-fast-active-v2','saturn-timing-fast-guards-v1']
 for name in names:files.update(p for p in(R/'build'/name).rglob('*')if p.is_file()and p.suffix!='.gch')
 files.update(p for p in(R/'timing').glob('saturn_timing_fast*')if p.is_file());inputs={};deps={};digests={}
 def cached(p):
  if p not in digests:digests[p]=sha(p)
  return digests[p]
 for receipt in list(files):
  if receipt.suffix!='.json':continue
  try:j=json.loads(receipt.read_text())
  except ValueError:continue
  if not isinstance(j,dict):continue
  for key in['input_sha256','source_sha256']:
   for name,digest in j.get(key,{}).items():
    p=Path(name)
    if not p.is_absolute():continue
    if p.is_relative_to(REFERENCE):
     assert cached(p)==digest;deps[name]={'path':str(p.relative_to(REFERENCE)),'sha256':digest};continue
    if name in refmap:
     q=refmap[name];assert cached(q)==digest;deps[name]={'path':str(q.relative_to(REFERENCE)),'sha256':digest};continue
    assert p.is_file()and cached(p)==digest,('Changed candidate input',name);files.add(p);inputs[name]=digest
 # The compiled helper archive originated in the separately frozen359 package.
 base=R/'build/combined-frozen-35901887/manifest.json';files.add(base);out.mkdir();index=[];dedup={}
 for p in sorted(files):
  path=rel(p);target=out/path;target.parent.mkdir(parents=True,exist_ok=True);digest=cached(p);mode=stat.S_IMODE(p.stat().st_mode);key=(digest,mode)
  if key in dedup:os.link(dedup[key],target)
  else:shutil.copy2(p,target);dedup[key]=target
  index.append({'path':str(path),'source_path':str(p),'bytes':target.stat().st_size,'mode':mode,'sha256':digest})
 native=json.loads((R/'build/saturn-timing-fast-v1/build.json').read_text());replays=[json.loads((R/'build/saturn-timing-fast-replay-v1'/c/'report.json').read_text())for c in['vme','rvv','fpcomp','shared-fpu']];report={'schema':'iris.saturn_numeric_substitution_frozen_capsule.v1','pass':True,'reference_dependency':{'path':str(REFERENCE),'report_sha256':sha(REFERENCE/'report.json'),'artifact_count':reference['artifact_count'],'input_mapping':deps},'source_identity':native['source_identity'],'native_sha256':native['native_sha256'],'library_sha256':native['library_sha256'],'numeric_proof':'build/saturn-timing-fast-numeric-proof-v1/report.json','speed_proof':'build/saturn-timing-fast-active-v2/report.json','guard_proof':'build/saturn-timing-fast-guards-v1/report.json','actual_reset_core_edges':sum(h['edges']for r in replays for h in r['harts']),'qualified_output_word_checks':sum(h['qualified_output_word_checks']for r in replays for h in r['harts']),'artifact_count':len(index),'logical_bytes':sum(x['bytes']for x in index),'unique_file_bytes':sum(p.stat().st_size for p in dedup.values()),'artifacts':index,'source_control_and_surrounding_datapath_preserved':True,'changed_RTL_modules':['OuterProductCell'],'unreset_tile_state_preserved':True,'whole_SoC_or_Ethan_image_certified':False,'heldout_2percent_timing_certified':False,'production_performance_target_met':False,'idle_skipping':False,'hardware_contacted':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({**{k:report[k]for k in['artifact_count','logical_bytes','unique_file_bytes','actual_reset_core_edges','qualified_output_word_checks']},'report_sha256':sha(out/'report.json')}))
def verify(out,reference):
 report=json.loads((out/'report.json').read_text());assert sha(reference/'report.json')==report['reference_dependency']['report_sha256'];ref=json.loads((reference/'report.json').read_text());check_inventory(reference,ref);check_inventory(out,report)
 for source,x in report['reference_dependency']['input_mapping'].items():assert sha(reference/x['path'])==x['sha256'],source
 candidate=out/'build/saturn-timing-fast-v1';assert sha(candidate/'sdk/saturn-timing')==report['native_sha256']and sha(candidate/'sdk/sdk/libiris_saturn_timing.a')==report['library_sha256'];rtl=candidate/'source/compute/rtl'
 for p in rtl.iterdir():
  if p.name!='OuterProductCell.sv':assert sha(p)==sha(reference/'build/saturn-timing-source-v1/compute/rtl'/p.name)
 libs=[reference/'external'/str(Path(p).parent).lstrip('/')for p in ref['runtime_libraries']['sdk']['libraries']];os.environ['LD_LIBRARY_PATH']=os.pathsep.join(map(str,libs));sys.path.insert(0,str(reference/'timing'));sys.modules.pop('saturn_timing_check',None);check=importlib.import_module('saturn_timing_check');check.R=reference;profiles={k:json.loads((reference/'build/saturn-timing-source-v1'/k/'ports.json').read_text())for k in['compute','rocket']};results=[]
 numeric=json.loads((out/report['numeric_proof']).read_text())
 for row in numeric['runs']:
  folder=out/'build/saturn-timing-fast-numeric-proof-v1'/row['kind'];binary=folder/'model'/('VOuterArray'if row['kind']=='array'else'VOuterCell');corpus=folder/('fp8-cases.txt'if row['kind']=='array'else'fp8-exhaustive.bin');q=subprocess.run([str(binary),str(corpus)],capture_output=True,text=True,timeout=120)
  if row['kind']=='timing-mutant':assert q.returncode!=0 and q.stderr==row['diagnostic']
  else:assert q.returncode==0 and json.loads(q.stdout)==row['checks']
 scope=out/'build/saturn-timing-fast-guards-v1/numeric-scope';q=subprocess.run([str(scope)],capture_output=True,text=True,timeout=30);assert q.returncode==0;assert json.loads(q.stdout)==json.loads((out/report['guard_proof']).read_text())['numeric_context']
 with tempfile.TemporaryDirectory(prefix='iris-saturn-fast-verify-')as temp:
  scratch=Path(temp)
  for case in['vme','rvv','fpcomp','shared-fpu']:
   frozen=json.loads((out/'build/saturn-timing-fast-replay-v1'/case/'report.json').read_text());base=reference/'build/saturn-timing-rtl-v1';rows,physical,times=check.capture(base/(case+'.stderr'),profiles);assert check.mailbox(base/(case+'.signature'),case)==frozen['guest_mailbox']
   for h in range(3):
    profile='rocket'if h==2 else'compute';command=[str(candidate/'sdk/saturn-timing'),'--reference-two-state','--profile',profile,'--hart',str(h),'--seed','91'];source=out/'build/saturn-timing-fast-replay-v1'/case/f'hart{h}.input';stdout=scratch/f'{case}-{h}.stdout'
    with source.open()as ins,stdout.open('w')as output,(scratch/f'{case}-{h}.stderr').open('w')as stderr:q=subprocess.run(command,stdin=ins,stdout=output,stderr=stderr,timeout=180)
    assert q.returncode==0;proof,ledger,masks=check.compare(profile,profiles[profile],rows[h],physical[h],times[h],stdout.read_text().splitlines());old=frozen['harts'][h]
    for key in['edges','qualified_output_word_checks','source_events','pending_TL_sources_at_end']:assert proof[key]==old[key],key
    results.append({'case':case,'hart':h,**proof})
   del rows,physical,times
 print(json.dumps({'pass':True,'capsule_sha256':sha(out/'report.json'),'reference_dependency_sha256':sha(reference/'report.json'),'artifacts_verified':len(report['artifacts']),'reference_artifacts_verified':len(ref['artifacts']),'actual_reset_core_edges':sum(x['edges']for x in results),'qualified_output_word_checks':sum(x['qualified_output_word_checks']for x in results),'independent_numeric_cell_array_and_timing_mutant_verified':True,'concurrent_numeric_context_verified':True,'hardware_contacted':False}))
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=FINAL);p.add_argument('--reference',type=Path,default=REFERENCE);p.add_argument('--verify',action='store_true');a=p.parse_args();verify(a.output.resolve(),a.reference.resolve())if a.verify else package(a.output.resolve())
if __name__=='__main__':main()
