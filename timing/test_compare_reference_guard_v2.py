#!/usr/bin/env python3
"""Synthetic-only counterfactuals for archive rederivation admission."""
from pathlib import Path
import hashlib,importlib.util,json,shutil,tempfile,types
from unittest.mock import patch
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 spec=importlib.util.spec_from_file_location('reference_adapter',R/'timing/compare_pow2_verified_reference_v2.py');v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v);checks=[]
 with tempfile.TemporaryDirectory()as t:
  d=Path(t);job=d/'job';hw=d/'hardware';canonical=d/'canonical';job.mkdir();hw.mkdir();canonical.mkdir();(job/'run.json').write_text('{"synthetic":true}\n');archive=d/'not-a-real-hardware-archive';archive.write_bytes(b'SYNTHETIC ONLY; NO ACTUAL LABELS');identity=sha(archive)
  for name,body in [('corpus.json',b'{"cases":["synthetic"]}\n'),('regions.jsonl',b'{"cycles":100}\n'),('observed.elf',b'not-a-real-ELF')]:
   (hw/name).write_bytes(body);(canonical/name).write_bytes(body)
  hr=dict(input_sha256={str(job/'run.json'):sha(job/'run.json'),str(archive):identity},archive_sha256=identity);(hw/'report.json').write_text(json.dumps(hr))
  state=dict(rc=0,verified=True,archive=identity)
  def fake(argv,**kwargs):
   fresh=Path(argv[argv.index('--output')+1]);fresh.mkdir()
   for f in canonical.iterdir():shutil.copy2(f,fresh/f.name)
   (fresh/'report.json').write_text(json.dumps(dict(archive_verified=state['verified'],archive_sha256=state['archive'])))
   return types.SimpleNamespace(returncode=state['rc'],stdout=b'synthetic analyzer boundary',stderr=b'')
  def refused(name):
   try:v.verify_reference('private_scalar',hw)
   except (ValueError,KeyError):checks.append(dict(name=name,rejected=True));return
   raise ValueError('Unexpected acceptance: '+name)
  with patch.object(v.subprocess,'run',side_effect=fake):
   assert v.verify_reference('private_scalar',hw)['archive_rederivation_verified']is True
   for name in ['regions.jsonl','corpus.json','observed.elf']:
    original=(hw/name).read_bytes();(hw/name).write_bytes(original+b'changed');refused('changed-derived-'+name);(hw/name).write_bytes(original)
   state['archive']='0'*64;refused('different-rederived-archive');state['archive']=identity
   state['verified']=1;refused('boolean-archive-verification-required');state['verified']=True
   state['rc']=1;refused('failed-strict-analyzer');state['rc']=0
   original=(job/'run.json').read_bytes();(job/'run.json').write_bytes(original+b' ');refused('changed-inventory-bound-job')
 o=R/'build/verified-reference-wrapper-review-v2';o.mkdir(exist_ok=False);r=dict(schema='iris.verified_reference_wrapper_synthetic_audit.v1',pass_=True,positive_synthetic_rederivation=True,negative_controls=checks,real_hardware_labels_read=False,strict_analyzer_mocked_only_in_this_unit_test=True,scope='Adapter rejects changed derived counters/corpus/ELF and changed exactarchive/job; actual analyzer correctness remains its separate frozen proof.',input_sha256={str(Path(__file__).resolve()):sha(__file__),str(R/'timing/compare_pow2_verified_reference_v2.py'):sha(R/'timing/compare_pow2_verified_reference_v2.py')});r['pass']=r.pop('pass_');(o/'report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(pass_=True,controls=len(checks),report_sha256=sha(o/'report.json'))))
if __name__=='__main__':main()
