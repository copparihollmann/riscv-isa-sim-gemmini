#!/usr/bin/env python3
"""Source-only conditional liveness/numerical probe; no FPGA results consumed."""
import argparse,hashlib,itertools,json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output).resolve();out.mkdir(parents=True,exist_ok=False)
 sdk=ROOT/'build/saturn-timing-ownership-sdk-v7/sdk';source=ROOT/'timing/rvv_rocket_repeated_load_source_v2.cpp';cc=Path('/scratch/eygao/iris-cy/.conda-env/bin/x86_64-conda-linux-gnu-c++')
 argv=[str(cc),'-O2','-std=c++20','-no-pie','-I'+str(sdk),str(source),str(sdk/'libiris_saturn_timing.a'),'-pthread','-latomic','-o',str(out/'probe')]
 r=subprocess.run(argv,capture_output=True);(out/'compile.stdout').write_bytes(r.stdout);(out/'compile.stderr').write_bytes(r.stderr);assert r.returncode==0
 (out/'source.cpp').write_bytes(source.read_bytes());cases=[]
 services=[(2,1,0,0),(20,1,0,0),(200,3,5,0),(20,2,3,1)]
 for lm,n,(delay,gap,astall,reverse),seed,init in itertools.product((4,8),(16,64),services,(0,17),(0,1)):
  name=f'm{lm}.n{n}.delay{delay}.gap{gap}.A{astall}.reverse{reverse}.seed{seed}.init{init}';cmd=[str(out/'probe'),*[str(x)for x in(lm,n,delay,gap,astall,reverse,seed,init)]];t=time.monotonic();r=subprocess.run(cmd,capture_output=True,timeout=45)
  (out/(name+'.stdout')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr)
  lines=[x for x in r.stderr.decode().splitlines()if x.startswith('{')]
  if r.returncode or len(lines)!=1:raise ValueError(name+' '+r.stderr.decode()[-3000:])
  row=json.loads(lines[0]);assert row['pass'] and row['retired']==n+1+3*init and row['Gets']==n*lm and row['D_data_beats']==4*n*lm and row['checked_store_bytes']==32*lm
  cases.append(dict(name=name,elapsed_seconds=time.monotonic()-t,argv=cmd,**row))
 # Corrupt every returned data beat, retaining legal ownership/latency. The
 # independent complete destination check must fail, not merely a checksum.
 mutant=out/'bad_data';mutant.mkdir();text=source.read_text();old='responseword(r.address+8*r.beat)';assert text.count(old)==1;(mutant/'source.cpp').write_text(text.replace(old,'(responseword(r.address+8*r.beat)^1ULL)'))
 ma=argv.copy();ma[ma.index(str(source))]=str(mutant/'source.cpp');ma[-1]=str(mutant/'probe');m=subprocess.run(ma,capture_output=True);(mutant/'compile.stderr').write_bytes(m.stderr);assert m.returncode==0
 m=subprocess.run([str(mutant/'probe'),'8','16','2','1','0','0','0','1'],capture_output=True,timeout=45);(mutant/'stdout').write_bytes(m.stdout);(mutant/'stderr').write_bytes(m.stderr);assert m.returncode==2 and b'final physical VRF-write ledger disagrees with backing' in m.stderr
 deps=[source,Path(__file__).resolve(),cc,sdk/'saturn_timing.hpp',sdk/'libiris_saturn_timing.a',sdk/'ownership-schema.json',ROOT/'build/rvv-identify-diagnostic-v2/guest.elf',ROOT/'build/rvv-identify-diagnostic-v2/build.json',ROOT/'benchmarks/rvv_identify_diag_v1/guest.c',ROOT/'third_party/saturn/src/main/scala/rocket/Integration.scala',ROOT/'third_party/saturn/src/main/scala/mem/VectorMemUnit.scala']
 deps=[x for x in deps if x.exists()]
 report=dict(schema='iris.rocket_repeated_VLE32_source_probe.v1',**{'pass':True},cases=cases,runs=len(cases),data_corruption_refused=True,build_command=argv,input_sha256={str(x):sha(x)for x in deps},source_identity='saved standalone SaturnRocketUnit full RTL, ownership SDK v7',scope='Real source reset plus128 quiet source edges; optional actual three VMV setup instructions; source EX-ready and WB retire/replay obeyed; repeated same-PC VLE32 into v8; final source VSE checks every byte. Exact diagnostic input[h2]=0x80042900 and target[h2]=0x80041d00, ELF778c...; no whole-CPU cache/NoC/CDC/SerialTL/FASED producer/service integration.',memory_service='Explicit synthetic owned A/Get plus four64-bit AccessAckData beats per32B request; complete Put messages then AccessAck. Parameters are test stimuli, not measured FPGA latency. In-order or reverse complete-message return, bounded A/D stalls, no unsolicited response or observed internal ready/state input.',ordinary_CPU_front_policy='One live EX/WB front; next command only after source retire or explicit replay, pipeline callbacks not used',all_output_bits_initialized_by_source_reset=False,VRF_load_data_defined_by_explicit_backing=True,physical_whole_VRF_written_directly=False,source_FPGA_association=False,actual_FPGA_stall_reproduced=False,hardware_contacted=False,full_CPU_timing_qualified=False)
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'runs':len(cases),'report':str(out/'report.json'),'sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
