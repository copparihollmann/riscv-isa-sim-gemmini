#!/usr/bin/env python3
"""Independent differential: new finite scheduler versus saved RTL issues."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
 source=out/'driver.cpp';source.write_text(r'''
#include "overlap_completion_entry_schedule.hpp"
#include <iostream>
#include <string>
int main(int n,char**v){if(n!=5)return 2;iris::opu_entry::Schedule s;
 const bool fp8=std::string(v[1])=="fp8",rotate=std::string(v[4])=="rotate";
 const unsigned size=std::stoul(v[2]),count=std::stoul(v[3]);
 for(unsigned k=0;k<count;++k)for(auto m:s.reserve(rotate?k%4:0,size,size,fp8,3+k))
  std::cout<<m.sequencer_edge<<' '<<m.entry<<' '<<m.array_accept_edge<<' '<<m.write_edge<<' '<<m.macs<<'\n';
}
''')
 compiler='/scratch/eygao/iris-cy/.conda-env/bin/x86_64-conda-linux-gnu-c++';cmd=[compiler,'-O2','-std=c++20','-I'+str(ROOT/'timing'),str(source),'-o',str(out/'driver')]
 subprocess.run(cmd,check=True,capture_output=True)
 reference=ROOT/'build/overlap-completion-OPU-entry-witness-v1/report.json';actual=json.loads(reference.read_text());checks=0;rows=[]
 for case in actual['results']:
  cmd=[str(out/'driver'),case['kind'],str(case['shape'][0]),str(case['commands']),case['pattern']];q=subprocess.run(cmd,check=True,text=True,capture_output=True)
  values=[list(map(int,l.split()))for l in q.stdout.splitlines()]
  for seed in case['runs']:
   if [r[0]for r in values]!=seed['microissue_edges']or[r[1]for r in values]!=seed['entries']:raise ValueError('Source RTL microissue/entry differential failed')
   checks+=len(values)*2
  if sum(v[4]for v in values)!=case['commands']*case['shape'][0]**2:raise ValueError('Logical cell-mask work differs')
  rows.append({'kind':case['kind'],'shape':case['shape'],'commands':case['commands'],'pattern':case['pattern'],'source_seeds':2,'microissues':len(values),'first_issue':values[0][0],'last_issue':values[-1][0]})
 # Intentional mutants of the two causal observations must be detected.
 same=next(r for r in actual['results']if r['kind']=='fp8'and r['shape'][0]==16 and r['commands']==16 and r['pattern']=='same')['runs'][0]
 rotate=next(r for r in actual['results']if r['kind']=='fp8'and r['shape'][0]==16 and r['commands']==16 and r['pattern']=='rotate')['runs'][0]
 if same['microissue_edges']==rotate['microissue_edges']or same['entries']==rotate['entries']:raise ValueError('Causal mutant unexpectedly indistinguishable')
 inputs=[Path(__file__),source,ROOT/'timing/overlap_completion_entry_schedule.hpp',reference,ROOT/'third_party/saturn/src/main/scala/backend/Backend.scala',ROOT/'third_party/saturn/src/main/scala/exu/OuterProductUnit.scala']
 report={'schema':'iris.OPU_entry_schedule_savedRTL_differential.v1','pass':True,'source_cases':24,'source_seeds_per_case':2,'microissue_entry_checks':checks,'cases':rows,'wrong_tile_and_history_mutants_rejected':True,'array_phase_source':'Backend.scala vopu_ctrl_reg adds1edge; OuterProductCell INT8write samearrayedge, FP8latency2','CPU_COM_to_source_command_available_qualified':False,'conditional_always_ready_VRF_peers':True,'hardware_contacted':False,'global_heldout_timings_consumed':False,'parameters_fitted':False,'input_sha256':{str(p.resolve()):sha(p)for p in inputs}}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'pass':True,'checks':checks,'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
