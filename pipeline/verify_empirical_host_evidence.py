#!/usr/bin/env python3
"""Independently check the archived host-only optimization evidence bytes."""
import argparse,hashlib,json,tarfile
from pathlib import Path,PurePosixPath
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--directory',type=Path,required=True);p.add_argument('--native',type=Path,required=True);p.add_argument('--uart',type=Path,required=True);a=p.parse_args();o=a.directory.resolve();r=json.loads((o/'report.json').read_text());inventory=json.loads((o/'inventory.json').read_text())
 assert r['pass']is True and r['binary_sha256']==sha(a.native)and r['uart_sha256']==sha(a.uart)
 for path,digest in r['input_sha256'].items():assert sha(path)==digest,path
 observed={}
 with tarfile.open(o/'evidence.tar.gz')as tar:
  for m in tar:
   q=PurePosixPath(m.name);assert m.isfile()and not q.is_absolute()and '..'not in q.parts and m.name not in observed,m.name
   s=tar.extractfile(m);h=hashlib.sha256()
   while True:
    block=s.read(1048576)
    if not block:break
    h.update(block)
   observed[m.name]=h.hexdigest()
 assert observed==inventory
 result={'schema':'iris.empirical.host_evidence_verification.v1','pass':True,'binary_sha256':sha(a.native),'uart_sha256':sha(a.uart),'archived_evidence_files_verified':len(inventory),'input_sha256':{str(p):sha(p)for p in[o/'report.json',o/'inventory.json',o/'evidence.tar.gz',Path(__file__).resolve()]},'full_binary_rebuild_performed':False,'timing_or_image_certified':False};(o/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
