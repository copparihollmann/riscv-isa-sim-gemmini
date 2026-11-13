#!/usr/bin/env python3
"""Postcapture reader adapter for frozen POW2 v1 analyzers; no job/source mutation.

The inventory reader retains selected records only. Retain already hash-verified
ready.json here and bind immutable top-level admission files to the archived
preparation identities. Guest/ELF/runtime/validator sources remain unchanged.
"""
import argparse,hashlib,json,tarfile
from pathlib import Path
from analyze_campaign import read_archive as original_read_archive
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read_archive(archive,expected_manifest_hash):
 data,identities=original_read_archive(archive,expected_manifest_hash);m=json.loads(data['job/run.json'])
 # Exact frozen files; runtime manager logs/config mutations are not inferred immutable.
 names=['ready.json','corpus.json','qualification.json','build.json']
 if m.get('campaign_role')=='pow2_single_memory_train_reserved_v1':names+=['layout.json','review.json']
 elif m.get('campaign_role')=='pow2_single_matrix_train_reserved_v1':names+=['golden-words.bin']
 else:raise ValueError('Unknown POW2 experiment role')
 with tarfile.open(archive,'r:gz')as t:
  for name in names:
   member='job/'+name;want=m['prepared_file_sha256'][name]
   if identities.get(member)!=want:raise ValueError('Frozen prepared record mismatch '+name)
   raw=t.extractfile(member).read()
   if hashlib.sha256(raw).hexdigest()!=want:raise ValueError('Retained immutable record changed '+name)
   if name=='ready.json':data[member]=raw
 ready=json.loads(data['job/ready.json'])
 if identities['job/ready.json']!=m['reviewed_ready_sha256']:raise ValueError('Frozen ready packet changed')
 if 'artifact_sha256'in ready:
  for name,want in ready['artifact_sha256'].items():
   if name in names and identities.get('job/'+name)!=want:raise ValueError('Ready artifact mismatch '+name)
 else:
  for name,key in [('build.json','build_sha256'),('qualification.json','qualification_sha256'),('corpus.json','corpus_sha256'),('layout.json','layout_sha256'),('review.json','review_sha256')]:
   if identities.get('job/'+name)!=ready[key]:raise ValueError('Ready artifact mismatch '+name)
 return data,identities

def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--kind',choices=['memory','matrix'],required=True);p.add_argument('job',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--training-export',type=Path);a=p.parse_args()
 if a.kind=='memory':import analyze_pow2_memory as target
 else:import analyze_pow2_matrix as target
 # Only adapt retention. The archived v1 proof, validator, numerical checks,
 # role/ELF/handshake/cleanup checks and TRAIN redaction execute unchanged.
 target.read_archive=read_archive;code=target.analyze(a.job.resolve(),a.output.resolve(),a.training_export)
 report=a.output/'report.json';r=json.loads(report.read_text());r['postcapture_reader_adapter']=dict(schema='iris.pow2_postcapture_reader_adapter.v2',source=str(Path(__file__).resolve()),sha256=sha(__file__),original_analyzer=str(Path(target.__file__).resolve()),original_analyzer_sha256=sha(target.__file__),original_analyzer_archived_inputs_preserved=True,change_scope='Retain inventory-hashed ready.json and verify immutable prepared admission record identities; no guest/source/runtime/fit changes',hardware_contacted=False);r['input_sha256'][str(Path(__file__).resolve())]=sha(__file__);report.write_text(json.dumps(r,indent=2)+'\n')
 if a.training_export and(a.training_export/'report.json').exists():
  q=a.training_export/'report.json';v=json.loads(q.read_text());v['postcapture_reader_adapter_sha256']=sha(__file__);v['original_analyzer_sha256']=sha(target.__file__);q.write_text(json.dumps(v,indent=2)+'\n');r['TRAIN_export']['report_sha256']=sha(q);report.write_text(json.dumps(r,indent=2)+'\n')
 return code
if __name__=='__main__':raise SystemExit(main())
