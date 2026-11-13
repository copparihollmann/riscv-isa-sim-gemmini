#!/usr/bin/env python3
"""Close the finite configured StoreSequencer SDK against exact saved RTL."""
from pathlib import Path
import hashlib,json,shutil,subprocess,tarfile
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(argv,out):
 with(out/'build.stdout').open('w')as so,(out/'build.stderr').open('w')as se:subprocess.run(argv,check=True,stdout=so,stderr=se)
 with(out/'stdout').open('w')as so,(out/'stderr').open('w')as se:r=subprocess.run([str(out/'check')],stdout=so,stderr=se)
 return r.returncode

def main():
 out=R/'build/rvv-store-sequence-component-v1';out.mkdir(exist_ok=False);sdk=out/'sdk';sdk.mkdir()
 source=(R/'timing/rvv_store_sequence.cpp').read_text();base=json.loads((R/'build/rvv-store-sequence-final-check-v1/argv.json').read_text())
 mutations=[('drop-RAW','!(bit&i.older_writes)&&i.vrf_read_ready','i.vrf_read_ready'),('early-tail','const bool last=next==c.vl','const bool last=true'),('no-tail-replace','output_.dispatch_ready=last&&output_.data_fire','output_.dispatch_ready=false'),('keep-read-intent','rintent_&=~(1ULL<<p.eg)','rintent_|=(1ULL<<p.eg)'),('wrong-byte-mask','const uint64_t mask=(all<<head)&(tail?((1ULL<<tail)-1):all)&all','const uint64_t mask=all')]
 controls=[]
 for name,old,new in mutations:
  d=out/name;d.mkdir();p=d/'mutant.cpp';assert source.count(old)==1;p.write_text(source.replace(old,new));argv=[str(p)if x==str(R/'timing/rvv_store_sequence.cpp')else x for x in base];argv[-1]=str(d/'check');(d/'argv.json').write_text(json.dumps(argv,indent=2)+'\n');status=run(argv,d)
  if status==0:raise ValueError('Mutation accepted '+name)
  controls.append(dict(name=name,rejected=True,exit_status=status))
 for n in ['rvv_store_sequence.hpp','rvv_store_sequence.cpp']:shutil.copy2(R/'timing'/n,sdk/n)
 argv=['/usr/bin/g++','-std=c++20','-O3','-c',str(sdk/'rvv_store_sequence.cpp'),'-I'+str(sdk),'-o',str(sdk/'rvv_store_sequence.o')];subprocess.run(argv,check=True);subprocess.run(['/usr/bin/ar','rcs',str(sdk/'libiris_rvv_store_sequence.a'),str(sdk/'rvv_store_sequence.o')],check=True)
 positives=[]
 for line in(R/'build/rvv-store-sequence-final-check-v1/stdout').read_text().splitlines():
  if line.startswith('CASE '):positives.append(json.loads(line[5:]))
 if len(positives)!=6 or sum(x['edges']for x in positives)!=600000:raise ValueError('Exact final positive corpus')
 speed=json.loads((R/'build/rvv-store-sequence-final-speed-v1/stdout').read_text());assert speed['pass']is True and speed['geometry_checks']==10 and speed['guard_refusals']==14
 paths=[Path(__file__),R/'timing/rvv_store_sequence.hpp',R/'timing/rvv_store_sequence.cpp',R/'timing/rvv_store_sequence_check.cpp',R/'timing/rvv_store_sequence_guards.cpp',R/'timing/rvv_store_sequence_build.py',R/'timing/rvv_source_store_verify_v2.py',R/'build/rvv-source-store-proof-v2/report.json']
 for b in['rvv-store-sequence-final-check-v1','rvv-store-sequence-final-speed-v1']:
  paths +=[p for p in(R/'build'/b).rglob('*')if p.is_file()]
 paths +=[p for p in(R/'build/rvv-store-sequence-source-v1').rglob('*')if p.is_file()]
 paths +=[p for p in out.rglob('*')if p.is_file()]
 sourcefacts={}
 for n,lines in [('backend/StoreSequencer.scala','18-55,57-107'),('mem/Mem.scala','370-406,433'),('mem/TLInterface.scala','33-37'),('rocket/Integration.scala','59'),('shuttle/Integration.scala','62')]:
  p=R/'third_party/saturn/src/main/scala'/n;paths.append(p);sourcefacts[str(p)]={'sha256':sha(p),'lines':lines}
 proof=json.loads((R/'build/rvv-source-store-proof-v2/report.json').read_text());assert proof['pass']is True
 paths +=[Path(x)for x in proof['input_sha256']]
 inputs={str(p.resolve()):sha(p)for p in paths};rep=dict(schema='iris.rvv_configured_store_sequence_component.v1',status='passed',continuous_source_edges=600000,qualified_field_comparisons=sum(x['qualified_field_checks']for x in positives),source_cases=positives,implementation_mutations=controls,guard_and_active_speed=speed,whole_unit_A_D_geometry_proof_sha256=sha(R/'build/rvv-source-store-proof-v2/report.json'),SDK={'header':str(sdk/'rvv_store_sequence.hpp'),'library':str(sdk/'libiris_rvv_store_sequence.a')},source_facts=sourcefacts,boundary='Configured saved StoreSequencer: actual reset; computeDLEN128 or RocketDLEN256; unmasked unitstride nf1; peer VRF/data readiness and older-write mask; no observed state reinjection. Configured saved specialization removes dis_stall port (constant false).',reset_knownness='only reset valid/control is qualified; inactive unreset payload is absent',throughput_scope='Component active source edges/s ONLY; no SoC MIPS, full-unit/NoC/CPU timing or 2% certification',integration_gap='Native CPU acceptance, memory queue/VRF-bank arbitration, per-TL-request ACK visibility and IRQ/shared-memory ordering remain separate. Geometry helper never invents memory latency.',hardware_contacted=False,reserved_hardware_timings_consumed=False,input_sha256=inputs)
 (out/'report.json').write_text(json.dumps(rep,indent=2)+'\n')
 with tarfile.open(out/'source-and-evidence.tar.gz','w:gz')as t:
  for p in sorted(inputs):t.add(p,arcname=str(Path(p).relative_to(R))if Path(p).is_relative_to(R)else'external/'+p.lstrip('/'),recursive=False)
 print(json.dumps({'status':'passed','report_sha256':sha(out/'report.json'),'source_archive_sha256':sha(out/'source-and-evidence.tar.gz')}))
if __name__=='__main__':main()
