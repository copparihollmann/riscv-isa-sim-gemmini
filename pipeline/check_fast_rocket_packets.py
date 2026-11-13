#!/usr/bin/env python3
"""Build and check the actual-word producer against the pinned IBuf oracle."""
import argparse,hashlib,json,shutil,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 include=Path('/scratch/eygao/iris-cy/.conda-env/share/verilator/include');oracle=ROOT/'build/fast-rocket-ibuf-source-v1/obj';cases=ROOT/'build/fast-rocket-packet-cases-v1';commands=[]
 def run(name,argv,expected=0):
  t=time.monotonic();r=subprocess.run(list(map(str,argv)),capture_output=True,timeout=120);(out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr);commands.append({'name':name,'argv':list(map(str,argv)),'exit_status':r.returncode,'host_seconds':time.monotonic()-t});assert (r.returncode==0)==(expected==0),(name,r.returncode,r.stderr.decode());return r
 inputs=[Path(__file__).resolve(),ROOT/'pipeline/fast_rocket_packets.hpp',ROOT/'pipeline/fast_rocket_packets.cpp',ROOT/'pipeline/fast_rocket_ibuf.hpp',ROOT/'pipeline/fast_rocket_ibuf.cpp',ROOT/'pipeline/fast_rocket_rvc_fields.hpp',ROOT/'pipeline/fast_source_rvc_table.hpp',ROOT/'pipeline/test_fast_rocket_packet_guards.cpp',ROOT/'pipeline/test_fast_rocket_packet_stream.cpp',cases/'cases.hpp',cases/'report.json',oracle/'VIBuf.h',oracle/'VIBuf__ALL.a',ROOT/'build/fast-rocket-ibuf-source-v1/report.json',ROOT/'build/fast-rocket-ibuf-component-v1/report.json',include/'verilated.cpp',include/'verilated_threads.cpp',Path('/usr/bin/g++')]
 before={str(x):sha(x)for x in inputs};base=['/usr/bin/g++','-std=c++20','-O2','-I'+str(ROOT/'pipeline')];production=ROOT/'pipeline/fast_rocket_packets.cpp';ibuf=ROOT/'pipeline/fast_rocket_ibuf.cpp';guard=ROOT/'pipeline/test_fast_rocket_packet_guards.cpp';stream=ROOT/'pipeline/test_fast_rocket_packet_stream.cpp'
 for suffix,flags in [('optimized',[]),('checked',['-D_GLIBCXX_ASSERTIONS','-D_GLIBCXX_DEBUG'])]:
  binary=out/('guards-'+suffix);run('build-guards-'+suffix,base+flags+[guard,production,ibuf,'-o',binary]);r=run('guards-'+suffix,[binary]);assert r.stdout==b'PASS checks=65 refusals=17\n'
 binary=out/'stream';run('build-stream',base+['-I'+str(cases),'-I'+str(oracle),'-I'+str(include),stream,production,ibuf,oracle/'VIBuf__ALL.a',include/'verilated.cpp',include/'verilated_threads.cpp','-pthread','-o',binary]);r=run('stream',[binary]);assert r.stdout.endswith(b'PASS cases=64 checks=229376\n')
 mutants={'partial-bits':('uint16_t(raw)}','uint16_t(raw^4)}'),'word-owner':('owners.insert(owners.begin(),partial_->word);','owners.insert(owners.begin(),w.value.id);')}
 for name,(old,new)in mutants.items():
  text=production.read_text();assert text.count(old)==1;source=out/('mutant-'+name+'.cpp');source.write_text(text.replace(old,new));binary=out/('mutant-'+name);run('build-mutant-'+name,base+[guard,source,ibuf,'-o',binary]);r=run('mutant-'+name,[binary],expected=1);assert r.returncode!=0
 assert all(sha(path)==digest for path,digest in before.items())
 report={'schema':'iris.fast_rocket_packet.source_flow_check.v1','pass':True,'source_scope':'saved Rocket IBuf plus explicit demand-four-byte-word producer; full Rocket predictor/frontend NOT translated','stream_cases':64,'source_port_and_owner_checks':229376,'guard_checks_per_build':65,'guard_refusals_per_build':17,'build_variants':['optimized','checked-libstdc++'],'mutants_rejected':list(mutants),'packet_prediction_fixture':'explicit warm correctly predicted backward branches derived from actual opcode immediates','timing_labels_used_in_producer':False,'input_sha256':before,'commands':commands,'artifact_sha256':{str(q.relative_to(out)):sha(q)for q in out.iterdir()if q.is_file()},'timing_certified':False,'image_source_association':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
