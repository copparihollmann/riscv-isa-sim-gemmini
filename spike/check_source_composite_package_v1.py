#!/usr/bin/env python3
"""New dual-profile descriptor corruption/refusal controls; no native edits."""
import argparse,copy,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from spike import empirical_provider_source_composite_v1 as P

def main():
 a=argparse.ArgumentParser(__doc__);a.add_argument('--package',type=Path,required=True);a.add_argument('--output',type=Path,required=True);x=a.parse_args();pkg,out=x.package.resolve(),x.output.resolve();out.mkdir(exist_ok=False);rows=[]
 for profile in P.PROFILES:
  mpath=pkg/profile/'manifest.json';original=P.document(mpath);assert P.experimental_empirical_simulator(mpath)['available']is True
  def run(name,mutate=None,text=None):
   m=copy.deepcopy(original)
   if mutate:mutate(m)
   p=mpath.with_name('refusal-'+name+'.json');p.write_text(text if text is not None else json.dumps(m,indent=2)+'\n');result=P.experimental_empirical_simulator(p)
   if result['available']:raise ValueError('Corrupt descriptor admitted: '+name)
   rows.append(dict(profile=profile,name=name,refused=True,reason=result['reason'],manifest=str(p),sha256=P.sha(p)))
  run('wrong-kind',lambda m:m.update(package_kind='other'))
  run('missing-profile',lambda m:m.pop('profile'))
  other='source_os'if profile=='source_compute'else'source_compute'
  run('cross-profile-name',lambda m:m.update(profile=other))
  run('cross-profile-fixture',lambda m:m.update(fixture=str(P.PROFILES[other]['fixture'])))
  run('cross-profile-identity',lambda m:m.update(calibration_identity=P.PROFILES[other]['identity']))
  run('typed-profile-scope',lambda m:m['profile_scope'].update(source_OPU=int(m['profile_scope']['source_OPU'])))
  run('borrow-compute-timing',lambda m:m['profile_scope'].update(compute_timing_qualification_transferred=True))
  run('remove-root-QA',lambda m:m['input_sha256'].pop(str(P.ROOT_QA[0])))
  run('replace-root-QA-path',lambda m:m.update(root_QA_closure=str(pkg/'fake-root-QA.json')))
  run('remove-opaque-validation',lambda m:m['input_sha256'].pop(m['opaque_validation_report']['path']))
  run('opaque-validation-hash',lambda m:m['opaque_validation_report'].update(sha256='0'*64))
  run('remove-source-archive',lambda m:m['input_sha256'].pop(str(P.CAPSULE/'native-source.tar.gz')))
  run('fixture-digest',lambda m:m['input_sha256'].update({m['fixture']:'0'*64}))
  run('native-digest',lambda m:m.update(native_binary_sha256='0'*64))
  run('wrong-bootrom',lambda m:m.update(bootrom=str(pkg/'not-bootrom')))
  run('drop-fixture-launch-arg',lambda m:m.update(launch_args=[v for v in m['launch_args']if not v.startswith('--iris-timing-fixture=')]))
  run('accuracy-escalation',lambda m:m['qualification'].update(accuracy_2percent_certified=True))
  run('image-escalation',lambda m:m['qualification'].update(source_image_association_verified=True))
  run('unsafe-closure-path',lambda m:m.update(source_closure=str(pkg/'wrong-source-closure.json')))
  run('empty-input-closure',lambda m:m.update(input_sha256={}))
  raw=mpath.read_text();run('duplicate-profile',text=raw.replace('"profile": "'+profile+'",','"profile": "'+profile+'", "profile": "'+profile+'",',1))
  run('nonfinite-JSON',text=raw[:-2]+',"extra":NaN}\n')
  assert P.experimental_empirical_simulator(mpath)['available']is True
 inputs={str(p):P.sha(p)for p in[Path(__file__).resolve(),Path(P.__file__).resolve(),pkg/'source_compute/manifest.json',pkg/'source_os/manifest.json',P.ROOT_QA[0]]}
 report=dict(schema='iris.source_composite_optional_package_refusal_controls.v1',**{'pass':True},profiles=2,refusals=len(rows),actual_native_or_source_mutations=False,validation_bytes_only_hashed_not_parsed=True,existing_default_or_provider_changed=False,controls=rows,input_sha256=inputs)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(pass_=True,controls=len(rows),sha256=P.sha(out/'report.json'))))
if __name__=='__main__':main()
