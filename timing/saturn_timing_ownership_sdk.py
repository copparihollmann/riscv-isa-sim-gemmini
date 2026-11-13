#!/usr/bin/env python3
"""Host-only ownership sidecar on immutable source model/runtime objects."""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
BASE=R/'build/saturn-timing-activity-component-v1-final'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def expression(member,width,lo):
 base='root.'+member
 if width<=64:return 'std::uint64_t('+base+')'
 value='std::uint64_t('+base+'['+str(lo//32)+'])'
 if min(64,width-lo)>32:value+='|(std::uint64_t('+base+'['+str(lo//32+1)+'])<<32)'
 return '('+value+')'
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--schema',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copy2(Path(__file__),out/'builder.py');schema_path=a.schema.resolve();schema=json.loads(schema_path.read_text());base=BASE/'build/saturn-timing-activity-sdk-v4';local=out/'source';local.mkdir()
 if any(p['required_unresolved']for p in schema['profiles'].values()):raise ValueError('Unresolved required source ownership state')
 for name in ['saturn_timing.hpp','saturn_timing.cpp','saturn_timing_driver.cpp']:shutil.copy2(base/'source'/name,local/name)
 api=local/'saturn_timing.hpp';text=api.read_text();text=text.replace(' static std::span<const Field> activity_fields(Profile);',' static std::span<const Field> activity_fields(Profile);\n // Read-only supplementary metadata; no automatic payload knownness.\n ActivitySnapshot sample_ownership(std::optional<std::uint64_t> uncore_tick={})const;\n static std::span<const Field> ownership_fields(Profile);');api.write_text(text)
 extension='''ActivitySnapshot SaturnTimingCut::sample_ownership(std::optional<std::uint64_t> tick)const{
 SaturnContextScope owner(impl_->context.get());
 if(!impl_->evaluated)throw std::logic_error("Ownership snapshot requires fresh pre-edge evaluate");
 ActivitySnapshot out{impl_->hart,impl_->edge_count,source_clock_id(impl_->profile,impl_->hart),tick,{}};
 out.words.resize(ownership_fields(impl_->profile).size());
'''
 for key,p in schema['profiles'].items():
  extension+='if(impl_->profile==Profile::'+('Compute128'if key=='compute'else'Rocket256')+'){const auto&root=*impl_->'+key+'->rootp;\n'
  for field in p['fields']:
   for word in field['words']:extension+='out.words['+str(word['index'])+']='+expression(field['member'],field['width'],word['lo'])+';\n'
  extension+='}\n'
 extension+='return out;}\nstd::span<const Field> SaturnTimingCut::ownership_fields(Profile p){\n'
 for key,p in schema['profiles'].items():extension+='static constexpr Field '+key+'[]={'+','.join('{'+json.dumps(f['name']+('@'+str(w['lo'])if f['width']>64 else''))+','+str(f['width'])+','+str(w['lo'])+','+str(w['width'])+'}'for f in p['fields']for w in f['words'])+'};\n'
 extension+='if(p==Profile::Compute128)return compute;if(p==Profile::Rocket256)return rocket;throw std::invalid_argument("Unknown ownership profile");}\n';source=local/'saturn_timing.cpp';text=source.read_text();at=text.rfind('\n}');source.write_text(text[:at]+'\n'+extension+text[at:]);inputs=[Path(__file__),schema_path,BASE/'report.json',base/'build.json',base/'sdk/libiris_saturn_timing.a',api,source,Path('/usr/bin/g++'),Path('/usr/bin/ar')];identity=hashlib.sha256(json.dumps({str(p):sha(p)for p in inputs},sort_keys=True).encode()).hexdigest();identity_header=local/'saturn_timing_identity.hpp';identity_header.write_text('#pragma once\n#define IRIS_SATURN_TIMING_SOURCE_ID "'+identity+'"\n');inputs.append(identity_header)
 sdk=out/'sdk';sdk.mkdir();lib=sdk/'libiris_saturn_timing.a';shutil.copy2(base/'sdk/libiris_saturn_timing.a',lib);compute=BASE/'build/saturn-timing-activity-native-fast-v4/model';rocket=BASE/'build/saturn-timing-activity-native-rocket-v2/model';tool=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include');common=['/usr/bin/g++','-O3','-std=c++20','-pthread','-I'+str(local),'-I'+str(compute),'-I'+str(rocket),'-I'+str(tool),'-I'+str(tool/'vltstd')];commands=[common+['-c',str(source),'-o',str(out/'saturn_timing.o')],['/usr/bin/ar','rcs',str(lib),str(out/'saturn_timing.o')],common+[str(local/'saturn_timing_driver.cpp'),str(lib),'-latomic','-o',str(out/'saturn-timing')]]
 with(out/'build.log').open('w')as log:
  for command in commands:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
 members=subprocess.check_output(['/usr/bin/ar','t',str(lib)],text=True).splitlines();old_members=subprocess.check_output(['/usr/bin/ar','t',str(base/'sdk/libiris_saturn_timing.a')],text=True).splitlines()
 if members!=old_members:raise ValueError('Ownership host derivative changed archive member set')
 identical={}
 for member in members:
  if member=='saturn_timing.o':continue
  old=subprocess.check_output(['/usr/bin/ar','p',str(base/'sdk/libiris_saturn_timing.a'),member]);new=subprocess.check_output(['/usr/bin/ar','p',str(lib),member]);assert old==new,member;identical[member]=hashlib.sha256(new).hexdigest()
 shutil.copy2(api,sdk/api.name);shutil.copy2(schema_path,sdk/'ownership-schema.json');result={'schema':'iris.saturn_ownership_host_only_sdk.v1','source_identity':identity,'argv':commands,'input_sha256':{str(p):sha(p)for p in inputs},'unchanged_model_runtime_numeric_archive_members':identical,'native_sha256':sha(out/'saturn-timing'),'library_sha256':sha(lib),'source_RTL_model_runtime_numeric_objects_modified':False,'metadata_drives_model_state':False,'knownness_inferred_from_raw_values':False,'hardware_contacted':False};(out/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'source_identity':identity,'native_sha256':result['native_sha256'],'unchanged_nonhost_objects':len(identical)}))
if __name__=='__main__':main()
