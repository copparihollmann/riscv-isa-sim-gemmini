#!/usr/bin/env python3
"""Prepare three-way source merges; never touch either immutable parent."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);a=ap.parse_args();o=Path(a.output).resolve();o.mkdir(parents=True,exist_ok=False)
 warm=ROOT/'build/warm-load-phase-frozen-16184afc';opu=ROOT/'build/opu-entry-overlap-frozen-b6ee38ea-v2';base=ROOT/'build/empirical-read-overlap-response-frozen-7bd58b4f';w=json.load(open(warm/'manifest.json'));b=json.load(open(base/'manifest.json'));c=json.load(open(opu/'manifest.json'));prefix=b['native_source_relative'];warmtree=Path(w['source']);oputree=Path(c['source']);assert sha(warm/'manifest.json')=='016f0d37ae71b733b33acf9269ced3e247c737a0e20ef9ce2c2e1096f5ebc9ca';assert sha(opu/'manifest.json')=='60fa4abc207e9b9e12174b6d07e3898d57e078335e5598bfb7e1d0aac13d323c';wi=json.load(open(warm/'native-inventory.json'));ci=json.load(open(opu/'native-inventory.json'));rows=[]
 for name in c['native_changed_files']:
  before=base/'src'/prefix/name;ours=warmtree/name;theirs=oputree/name;assert sha(theirs)==ci[name];d=o/'staged'/name;d.parent.mkdir(parents=True,exist_ok=True)
  if name not in wi:
   assert not ours.exists();d.write_bytes(theirs.read_bytes());code=0
  else:
   assert sha(ours)==wi[name];assert before.is_file()
   result=subprocess.run(['git','merge-file','--diff3','-p','-L','warm161','-L','base7bd5','-L','OPUb6ee',str(ours),str(before),str(theirs)],capture_output=True);code=result.returncode;d.write_bytes(result.stdout)
   if code not in(0,1,2,3,4,5,6,7):raise RuntimeError(result.stderr.decode())
  rows.append({'file':name,'conflict_markers':code,'staged_sha256':sha(d),'warm_sha256':sha(ours)if ours.exists()else None,'base_sha256':sha(before)if before.exists()else None,'OPU_sha256':sha(theirs)})
 j={'schema':'iris.warm_OPU_threeway_preparation.v1','pass':True,'applied_to_native_tree':False,'parents':{str(warm/'manifest.json'):sha(warm/'manifest.json'),str(opu/'manifest.json'):sha(opu/'manifest.json'),str(base/'manifest.json'):sha(base/'manifest.json')},'files':rows,'conflicted_files':[x['file']for x in rows if x['conflict_markers']],'hardware_contacted':False};(o/'preparation.json').write_text(json.dumps(j,indent=2)+'\n');print(json.dumps({'pass':True,'conflicts':j['conflicted_files'],'files':len(rows)}))
if __name__=='__main__':main()
