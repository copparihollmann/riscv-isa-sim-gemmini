#!/usr/bin/env python3
"""Freeze and independently verify the full Saturn physical-runtime reference."""
import argparse,hashlib,importlib,json,os,re,shutil,stat,subprocess,sys,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[1];FINAL=R/'build/saturn-timing-component-v1-final'
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb')as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def rel(p):return p.relative_to(R)if p.is_relative_to(R)else Path('external')/str(p).lstrip('/')
def package(out):
 if out.exists():raise ValueError('Preserve earlier capsule')
 names=['source-v1','native-v1','sdk-v1','reference-v1','rtl-v1','guests-v1','fpu-guests-v1','replay-v2','active-bench-v1','boundary-smoke-v1','guards-v2','reset-scrub-v1','reset-writers-v1','reset-vme-v2','reset-reader-v1','contract-v3'];dirs=[R/'build'/('saturn-timing-'+n)for n in names];files={p for d in dirs for p in d.rglob('*')if p.is_file()and p.suffix!='.gch'};files.update(p for p in(R/'timing').glob('saturn_timing*')if p.is_file());digests={}
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
    if not p.is_file()or cached(p)!=digest:raise ValueError('Qualified input changed '+name+' in '+str(receipt))
    files.add(p)
 contract=json.loads((R/'build/saturn-timing-contract-v3/source-contract.json').read_text())
 for fact in contract['facts']:
  for src in fact['source']:
   p=Path(src['path']);assert cached(p)==src['sha256'];lines=p.read_text().splitlines();assert all(src['literal']in lines[n-1]for n in src['lines']);files.add(p)
 manifest=R/'hardware/manifest.json';files.add(manifest);pins=json.loads(manifest.read_text())['repositories']
 for e in pins.values():
  assert re.fullmatch('[0-9a-f]{40}',e['commit'])
  if e.get('tracked_diff')and(R/'hardware'/e['tracked_diff']).is_file():files.add(R/'hardware'/e['tracked_diff'])
 reference=R/'build/rtl-verilator/manifest.json';files.add(reference);m=json.loads(reference.read_text())
 for key in['source_fir','source_annotations']:
  p=Path(m[key]);assert cached(p)==m[key+'_sha256'];files.add(p)
 # Recorded explicit preload implementation and linker support are part of scope.
 support=R/'build/noc-full-router-component-v1-final/build/rtl-memory-return-path-v1-final/board/rtl-loader';files.update(p for p in support.rglob('*')if p.is_file())
 runtime={}
 for label,p in [('sdk',R/'build/saturn-timing-sdk-v1/saturn-timing'),('wholeRTL',R/'build/saturn-timing-rtl-v1/simulator-saturn-boundary')]:
  q=subprocess.run(['ldd',str(p)],capture_output=True,text=True,check=True);paths=[]
  for line in q.stdout.splitlines():
   match=re.search(r'(?:=>\s*)?(/\S+)\s+\(',line)
   if match:paths.append(Path(match[1]));files.add(Path(match[1]))
  runtime[label]={'ldd':q.stdout,'libraries':{str(p):cached(p)for p in paths}}
 include=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include');files.update(p for p in include.rglob('*')if p.is_file());out.mkdir();index=[];dedup={}
 for p in sorted(files):
  path=rel(p);target=out/path;target.parent.mkdir(parents=True,exist_ok=True);digest=cached(p);mode=stat.S_IMODE(p.stat().st_mode);key=(digest,mode)
  if key in dedup:os.link(dedup[key],target)
  else:shutil.copy2(p,target);dedup[key]=target
  index.append({'path':str(path),'source_path':str(p),'bytes':target.stat().st_size,'mode':mode,'sha256':digest})
 reports=[json.loads((R/'build/saturn-timing-replay-v2'/c/'report.json').read_text())for c in['vme','rvv','fpcomp','shared-fpu']];report={'schema':'iris.saturn_runtime_frozen_capsule.v1','pass':True,'source_context_repositories':pins,'source_fir_sha256':contract['reference_source_fir_sha256'],'sdk_native_sha256':cached(R/'build/saturn-timing-sdk-v1/saturn-timing'),'sdk_archive_sha256':cached(R/'build/saturn-timing-sdk-v1/sdk/libiris_saturn_timing.a'),'source_identity':json.loads((R/'build/saturn-timing-sdk-v1/build.json').read_text())['source_identity'],'whole_rtl_replays':['build/saturn-timing-replay-v2/'+c+'/report.json'for c in['vme','rvv','fpcomp','shared-fpu']],'source_contract':'build/saturn-timing-contract-v3/source-contract.json','reset_reader':'build/saturn-timing-reset-reader-v1/report.json','guards':'build/saturn-timing-guards-v2/report.json','actual_reset_core_edges':sum(h['edges']for r in reports for h in r['harts']),'qualified_output_word_checks':sum(h['qualified_output_word_checks']for r in reports for h in r['harts']),'artifact_count':len(index),'logical_bytes':sum(x['bytes']for x in index),'unique_file_bytes':sum(p.stat().st_size for p in dedup.values()),'runtime_libraries':runtime,'artifacts':index,'whole_SoC_or_Ethan_image_certified':False,'source_checkout_association_verified':False,'heldout_2percent_timing_certified':False,'universal_first_access_VRF_zero_proven':False,'tile_reset_zero_proven':False,'production_performance_architecture':False,'idle_skipping':False,'primary_shared_engine_or_campaign_changed':False,'hardware_contacted':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({**{k:report[k]for k in['artifact_count','logical_bytes','unique_file_bytes','actual_reset_core_edges','qualified_output_word_checks']},'report_sha256':sha(out/'report.json')}))
def verify(out):
 report=json.loads((out/'report.json').read_text())
 for x in report['artifacts']:
  p=Path(x['path']);assert not p.is_absolute()and'..'not in p.parts;target=out/p;assert target.stat().st_size==x['bytes']and stat.S_IMODE(target.stat().st_mode)==x['mode']and sha(target)==x['sha256'],x['path']
 contract=json.loads((out/report['source_contract']).read_text())
 for fact in contract['facts']:
  for src in fact['source']:
   p=out/rel(Path(src['path']));assert sha(p)==src['sha256'];lines=p.read_text().splitlines();assert all(src['literal']in lines[n-1]for n in src['lines'])
 libs=[out/'external'/str(Path(p).parent).lstrip('/')for p in report['runtime_libraries']['sdk']['libraries']];os.environ['LD_LIBRARY_PATH']=os.pathsep.join(map(str,libs));sys.path.insert(0,str(out/'timing'))
 for name in['saturn_timing_check','saturn_timing_reset_read']:sys.modules.pop(name,None)
 check=importlib.import_module('saturn_timing_check');check.R=out;reader=importlib.import_module('saturn_timing_reset_read');reader.R=out;profiles={k:json.loads((out/'build/saturn-timing-source-v1'/k/'ports.json').read_text())for k in['compute','rocket']};results=[]
 with tempfile.TemporaryDirectory(prefix='iris-saturn-reference-verify-')as temp:
  scratch=Path(temp);oldargv=sys.argv;sys.argv=['reset-reader','--output',str(scratch/'reset')]
  try:reader.main()
  finally:sys.argv=oldargv
  fresh=json.loads((scratch/'reset/report.json').read_text());old=json.loads((out/report['reset_reader']).read_text());assert fresh['writer_cases']==old['writer_cases']and fresh['actual_guest_boot_margins']==old['actual_guest_boot_margins']
  for receipt in report['whole_rtl_replays']:
   frozen=json.loads((out/receipt).read_text());case=frozen['case'];base=out/'build/saturn-timing-rtl-v1';raw=base/(case+'.stderr');rows,physical,times=check.capture(raw,profiles);assert check.mailbox(base/(case+'.signature'),case)==frozen['guest_mailbox']
   for h in range(3):
    profile='rocket'if h==2 else'compute';command=[str(out/'build/saturn-timing-sdk-v1/saturn-timing'),'--reference-two-state','--profile',profile,'--hart',str(h),'--seed','91'];source=out/'build/saturn-timing-replay-v2'/case/f'hart{h}.input';stdout=scratch/f'{case}-{h}.stdout'
    with source.open()as ins,stdout.open('w')as output,(scratch/f'{case}-{h}.stderr').open('w')as stderr:q=subprocess.run(command,stdin=ins,stdout=output,stderr=stderr,timeout=180)
    assert q.returncode==0;proof,ledger,masks=check.compare(profile,profiles[profile],rows[h],physical[h],times[h],stdout.read_text().splitlines());oldhart=frozen['harts'][h]
    for key in['edges','qualified_output_word_checks','source_events','pending_TL_sources_at_end']:assert proof[key]==oldhart[key],key
    results.append({'case':case,'hart':h,**proof})
   del rows,physical,times
 print(json.dumps({'pass':True,'capsule_sha256':sha(out/'report.json'),'artifacts_verified':len(report['artifacts']),'actual_reset_core_edges':sum(x['edges']for x in results),'qualified_output_word_checks':sum(x['qualified_output_word_checks']for x in results),'reset_writer_cases':len(fresh['writer_cases']),'whole_rtl_harts':results,'hardware_contacted':False}))
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,default=FINAL);p.add_argument('--verify',action='store_true');a=p.parse_args();(verify if a.verify else package)(a.output.resolve())
if __name__=='__main__':main()
