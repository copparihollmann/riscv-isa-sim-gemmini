#!/usr/bin/env python3
"""Focused reference-identity mutation controls; no source/native mutations."""
import argparse,copy,importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def module():
 p=ROOT/'spike/empirical_provider_v4.py';spec=importlib.util.spec_from_file_location('reference_guard_v4_controls',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def check(manifest,output):
 output.mkdir(parents=True,exist_ok=False);api=module();m=api.document(manifest);binding=api.document(m['calibration']['runtime_binding']);positive=api.validate_reference_metadata(m,binding);controls=[]
 def reject(name,change):
  bad=copy.deepcopy(m);change(bad)
  try:api.validate_reference_metadata(bad,binding)
  except(KeyError,ValueError,TypeError)as e:controls.append(dict(name=name,rejected=True,reason=str(e)));return
  raise ValueError('Reference metadata corruption accepted: '+name)
 for key,value in [('driver_sha256','0'*64),('bitstream_sha256','0'*64),('image_archive_sha256','0'*64),('capture_archive_sha256','0'*64),('analysis_sha256','0'*64),('elf_sha256','0'*64),('independently_checked_regions',True),('independently_checked_regions',1007),('source_image_association_verified',True),('observability_report_sha256','0'*64)]:reject(key,lambda b,k=key,v=value:b['calibration']['reference'].__setitem__(k,v))
 reject('driver-bundle-is-not-executable',lambda b:b['calibration']['reference'].__setitem__('driver_sha256','5457de1e9c0dd1e3c52efbf5d083bdac7dfa5a5e3124c9887961c08159b03450'))
 reject('wrong-observation-document',lambda b:b['calibration']['reference'].__setitem__('observability_report',b['calibration']['reference']['analysis']))
 reject('unbound-observability-source',lambda b:b['input_sha256'].pop(b['calibration']['reference']['observability_report']))
 reject('missing-observation-policy',lambda b:b['calibration']['reference'].pop('observability_report'))
 wrong=output/'forged-observation.json';obs=api.document(m['calibration']['reference']['observability_report']);obs['complete_source_image_provenance']=True;wrong.write_text(json.dumps(obs)+'\n')
 def forged(b):
  b['input_sha256'][str(wrong)]=api.sha(wrong);b['calibration']['reference']['observability_report']=str(wrong);b['calibration']['reference']['observability_report_sha256']=api.sha(wrong)
 reject('forged-observation-source-association',forged)
 full=[]
 for key,value in [('driver_sha256','0'*64),('independently_checked_regions',True)]:
  bad=copy.deepcopy(m);bad['calibration']['reference'][key]=value;path=output/('full-provider-'+key+'.json');path.write_text(json.dumps(bad)+'\n');result=api.experimental_empirical_simulator(path)
  if result.get('available')is not False:raise ValueError('Actual full provider accepted '+key)
  full.append(dict(name=key,rejected=True,reason=result['reason'],manifest_sha256=api.sha(path)))
 if api.experimental_empirical_simulator(manifest).get('available')is not True:raise ValueError('Positive actual provider unavailable')
 report=dict(schema='iris.reference_guard_v4_controls.v1',**{'pass':True},manifest=str(manifest),manifest_sha256=api.sha(manifest),positive_reference=positive,helper_negative_controls=controls,actual_full_provider_negative_controls=full,old_provider_preserved=True,hardware_contacted=False,calibration_or_runtime_changed=False,input_sha256={str(p):api.sha(p)for p in[Path(__file__),ROOT/'spike/empirical_provider_v4.py',ROOT/'spike/empirical_provider_v3.py',manifest]});(output/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(**{'pass':True},helper_controls=len(controls),full_provider_controls=len(full),report_sha256=api.sha(output/'report.json'))));return report
if __name__=='__main__':
 p=argparse.ArgumentParser(__doc__);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();check(a.manifest.resolve(),a.output.resolve())
