#!/usr/bin/env python3
"""Check the archived three-clock token stream against an absolute event calendar."""
import argparse,hashlib,json,os,re,subprocess,time
from pathlib import Path
R=Path(__file__).resolve().parents[1]
TOOL=Path('/scratch/eygao/iris-cy/.conda-env/bin/verilator')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
CPP=r'''
#include "VFASEDClockToken.h"
#include "verilated.h"
#include <algorithm>
#include <array>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>
int main(int argc,char**argv){try{
 bool wrong=argc==2&&std::string(argv[1])=="--wrong-period";
 std::uint64_t checks=0,accepted=0;
 for(unsigned seed:{1U,7U,17U,31U,113U,199U}){
  VerilatedContext context;context.commandArgs(argc,argv);context.randSeed(seed);context.randReset(2);
  VFASEDClockToken model(&context);std::mt19937 rng(seed);
  std::array<std::uint64_t,3> next={0,0,0};
  std::array<unsigned,3> period={wrong?3U:2U,1,10};
  model.clock=0;model.reset=1;model.io_ready=0;model.eval();model.clock=1;model.eval();model.clock=0;model.eval();model.reset=0;
  for(unsigned edge=0;edge<100000;++edge){
   const bool reset=edge&&edge%32117==0;
   model.reset=reset;model.io_ready=rng()%7!=0;model.eval();
   if(!reset){auto when=*std::min_element(next.begin(),next.end());
    std::array<bool,3> bits={bool(model.io_bits_0),bool(model.io_bits_1),bool(model.io_bits_2)};
    for(unsigned c=0;c<3;++c){++checks;if(bits[c]!=(next[c]==when))throw std::runtime_error("clock calendar mismatch at hostedge "+std::to_string(edge));}
    if(model.io_ready){for(unsigned c=0;c<3;++c)if(next[c]==when)next[c]+=period[c];++accepted;}
   }else next={0,0,0};
   model.clock=1;model.eval();model.clock=0;model.eval();
  }
 }
 std::cout<<"{\"status\":\"passed\",\"checks\":"<<checks<<",\"host_edges\":600000,\"accepted_clock_tokens\":"<<accepted<<",\"relative_periods\":[2,1,10],\"loaded_image_attested\":false}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
'''
def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('--source',type=Path,default=R/'build/fased-service-source-v2');p.add_argument('--output',type=Path,required=True);a=p.parse_args();source=a.source.resolve();out=a.output.resolve()
    if out.exists():raise ValueError('fresh output required')
    manifest=json.loads((source/'extraction.json').read_text());sv=source/'FireSim-generated.sv';assert sha(sv)==manifest['archived_SV_sha256']
    text=sv.read_text();match=re.search(r'^module RationalClockTokenGenerator\(',text,re.M);assert match;end=text.index('\nendmodule',match.end());module=text[match.start():end+len('\nendmodule')]+'\n'
    for index,period in enumerate((2,1,10)):assert re.search(r'timeToNextEdge_'+str(index)+r" <= 4'h"+format(period,'x')+r';',module)
    out.mkdir();(out/'model').mkdir();(out/'RationalClockTokenGenerator.sv').write_text(module);(out/'clock_test.cpp').write_text(CPP)
    command=[str(TOOL.with_name('perl')),str(TOOL),'--cc','--exe','--build','-j','8','--prefix','VFASEDClockToken','--top-module','RationalClockTokenGenerator','-Wno-fatal','--x-initial','unique','--x-assign','unique','--Mdir',str(out/'model'),'+define+RANDOMIZE_REG_INIT',str(out/'RationalClockTokenGenerator.sv'),str(out/'clock_test.cpp'),'-MAKEFLAGS','CXX=/usr/bin/g++ LINK=/usr/bin/g++ AR=/usr/bin/ar RANLIB=/usr/bin/ranlib OPT_FAST=-O3 OPT_SLOW=-O3','-o',str(out/'clock-test')]
    env=dict(os.environ,PATH=str(TOOL.parent)+os.pathsep+os.environ['PATH']);start=time.monotonic()
    with(out/'compile.log').open('w')as log:c=subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT)
    report={'schema':'iris.archived_fased_clock_calendar_check.v1','compile_argv':command,'compile_exit_status':c.returncode,'input_sha256':{str(p):sha(p)for p in [Path(__file__),source/'extraction.json',sv,TOOL,TOOL.with_name('verilator_bin'),Path('/usr/bin/g++')]},'module_sha256':sha(out/'RationalClockTokenGenerator.sv'),'test_cpp_sha256':sha(out/'clock_test.cpp'),'hardware_contacted':False,'loaded_image_verified':False,'calibration_usable':False}
    if c.returncode==0:
        cases=[]
        for name,args,expected in [('absolute-clock-calendar',[],0),('wrong-period',['--wrong-period'],1)]:
            argv=[str(out/'clock-test'),*args];r=subprocess.run(argv,text=True,capture_output=True);(out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr);cases.append({'name':name,'argv':argv,'returncode':r.returncode,'expected':expected,'passed':r.returncode==expected,'stdout_sha256':sha(out/(name+'.stdout')),'stderr_sha256':sha(out/(name+'.stderr'))})
        report.update(cases=cases,binary_sha256=sha(out/'clock-test'),status='passed'if all(x['passed']for x in cases)else'failed')
        if cases[0]['passed']:report['clock_calendar']=json.loads((out/'absolute-clock-calendar.stdout').read_text())
    else:report['status']='compile_failed'
    report['host_seconds']=time.monotonic()-start;(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k)for k in ['status','host_seconds','clock_calendar']}));raise SystemExit(report['status']!='passed')
if __name__=='__main__':main()
