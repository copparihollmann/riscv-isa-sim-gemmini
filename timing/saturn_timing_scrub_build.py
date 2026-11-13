#!/usr/bin/env python3
"""Observe actual post-reset VRF writes and early-command readback, without state injection."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);native=R/'build/saturn-timing-native-v1';sdk=R/'build/saturn-timing-sdk-v1';code='''#include "VSaturnCompute.h"
#include "VSaturnCompute___024root.h"
#include "VSaturnRocket.h"
#include "VSaturnRocket___024root.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
struct Sweep {bool active;unsigned cursor;};
static void require(bool value,const char*why){if(!value)throw std::runtime_error(why);}
''';bindings=[]
 for profile,model,top,banks,dlen,egs in [('compute','VSaturnCompute','SaturnShuttleUnit',4,128,64),('rocket','VSaturnRocket','SaturnRocketUnit',1,256,32)]:
  j=json.loads((native/profile/'ports.json').read_text());root=(native/profile/'model'/(model+'___024root.h')).read_text();prefix=top+'__DOT__vu__DOT__vrf__DOT__';rf=prefix+'vrf__DOT__';member=lambda s:'m.rootp->'+s
  def bind(s):
   if s not in root:raise ValueError('Missing exact native read-only member '+s)
   bindings.append(s);return member(s)
  code+='static void inputs('+model+'&m){\n'
  for f in j['physical_ports']:
   if f['direction']!='input':continue
   if f['width']<=64:code+='m.'+f['name']+'=0;\n'
   else:
    for n in range((f['width']+31)//32):code+='m.'+f['name']+'['+str(n)+']=0;\n'
  core='io_core_'if profile=='rocket'else'io_';code+='m.'+core+'status_prv=3;m.'+core+'resp_ready=1;\n}\n'
  code+='static void command('+model+'&m,bool enable){m.'+core+'ex_valid=enable;'
  if profile=='compute':code+='m.io_ex_fire=enable;m.io_ex_uop_inst=0x428022d7;m.io_ex_uop_pc=0x80001000;'
  else:code+='m.io_core_ex_inst=0x428022d7;m.io_core_ex_pc=0x80001000;'
  code+='m.'+core+'ex_vconfig_vl=1;m.'+core+'ex_vconfig_vtype_vsew=3;}\n'
  code+='static Sweep sweep('+model+'&m){return {bool('+bind(prefix+'resetting')+'),unsigned('+bind(prefix+'reset_ctr')+')} ;}\n'
  code+='static std::uint32_t ram('+model+'&m,unsigned eg,unsigned word){switch(eg%'+str(banks)+'){\n'
  for bank in range(banks):code+='case '+str(bank)+':return '+bind(rf+'vrf_'+str(bank)+'__DOT__vrf_ext__DOT__Memory')+'[eg/'+str(banks)+'][word];\n'
  code+='}throw std::logic_error("Invalid bank");}\n'
  code+='static unsigned writes('+model+'&m,unsigned eg){unsigned seen=0;\n'
  for bank in range(banks):
   path=rf+'vrf_'+str(bank)+'__DOT__';code+='if('+bind(path+'write_valid')+'){require(eg%'+str(banks)+'=='+str(bank)+',"Scrub selected wrong bank");require('+bind(path+'write_bits_eg')+'==eg/'+str(banks)+',"Scrub wrote wrong bank address");'
   for w in range(dlen//32):code+='require('+bind(path+'write_bits_data')+'['+str(w)+']==0,"Scrub data is not zero");require('+bind(path+'write_bits_mask')+'['+str(w)+']==0xffffffffu,"Scrub mask not full width");'
   code+='++seen;}\n'
  code+='return seen;}\n'
  code+='static bool response('+model+'&m){return m.'+core+'resp_valid;}\nstatic void check_response('+model+'&m,bool corrupt){require(m.'+core+'resp_bits_rd==5&&!m.'+core+'resp_bits_fp,"Wrong scalar readback destination");require((m.'+core+'resp_bits_data^(corrupt?1:0))==0,"Reset-scrub architectural readback is nonzero");}\n'
  code+='static std::uint64_t tile_observation('+model+'&m){std::uint64_t h=1469598103934665603ULL;'
  if profile=='compute':
   for n in range(16):code+='h=(h^'+bind(top+'__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_'+str(n))+')*1099511628211ULL;'
  code+='return h;}\n'
 code+='''template<class M>static void run(const char*name,unsigned egs,unsigned dlen,unsigned seed,bool corrupt){
 auto context=std::make_unique<VerilatedContext>();context->threads(1);context->randSeed(seed);context->randReset(2);M m(context.get());inputs(m);m.reset=1;m.clock=0;m.eval();
 std::uint64_t before_nonzero=0;for(unsigned eg=0;eg<egs;eg++)for(unsigned w=0;w<dlen/32;w++)before_nonzero+=ram(m,eg,w)!=0;
 for(unsigned r=0;r<2;r++){m.clock=1;m.eval();m.clock=0;m.eval();}
 auto tile=tile_observation(m);unsigned response_edge=~0u,write_checks=0,zero_checks=0;std::uint64_t seen=0;m.reset=0;
 for(unsigned edge=0;edge<egs+24;edge++){
  command(m,edge==0);m.eval();auto state=sweep(m);
  if(edge<egs){require(state.active&&state.cursor==edge,"Source scrub progression differs from actual EG count");require(writes(m,edge)==1,"Reset sweep write not accepted by actual bank");if(egs<64||edge<64)seen|=1ULL<<edge;++write_checks;require(!response(m),"Vector read escaped reset-scrub read blocking");}
  else require(!state.active,"Scrub did not complete at exact source boundary");
  if(response(m)){require(response_edge==~0u,"Duplicate scalar response");check_response(m,corrupt);response_edge=edge;}
  m.clock=1;m.eval();m.clock=0;m.eval();
  unsigned cleared=edge<egs?edge+1:egs;for(unsigned eg=0;eg<cleared;eg++)for(unsigned w=0;w<dlen/32;w++){require(ram(m,eg,w)==0,"Scrubbed physical VRF bit is nonzero");++zero_checks;}
 }
 require(response_edge!=~0u&&response_edge>=egs,"Queued architectural readback did not complete after scrub");require(tile_observation(m)==tile,"Idle reset-scrub unexpectedly modified sampled tile entries");
 std::cout<<"SCRUB_RESULT {\\"profile\\":\\""<<name<<"\\",\\"seed\\":"<<seed<<",\\"post_reset_scrub_edges\\":"<<egs<<",\\"accepted_full_EG_writes\\":"<<write_checks<<",\\"zero_word_checks\\":"<<zero_checks<<",\\"pre_reset_nonzero_words_observed\\":"<<before_nonzero<<",\\"early_readback_response_edge\\":"<<response_edge<<",\\"sampled_tile_state_preserved\\":true}\\n";
}
int main(int argc,char**argv){try{bool corrupt=argc==2&&std::string(argv[1])=="--corrupt-readback";for(unsigned seed:{0u,1u,17u,91u}){run<VSaturnCompute>("compute",64,128,seed,corrupt);run<VSaturnRocket>("rocket",32,256,seed,corrupt);}return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\\n';return 2;}}
''';source=R/'timing/saturn_timing_scrub.cpp';source.write_text(code);(out/'read-only-members.json').write_text(json.dumps(sorted(set(bindings)),indent=2)+'\n');tool=Path('/scratch/eygao/iris-cy/.conda-env');include=tool/'share/verilator/include';c=Path('/usr/bin/g++');command=[str(c),'-O3','-std=c++20','-I'+str(include),'-I'+str(include/'vltstd')]+['-I'+str(native/k/'model')for k in ['compute','rocket']]+[str(source),str(sdk/'sdk/libiris_saturn_timing.a'),'-pthread','-latomic','-o',str(out/'scrub-proof')]
 with(out/'build.log').open('w')as log:q=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
 if q.returncode:raise RuntimeError('Read-only source scrub observer failed to compile')
 q=subprocess.run([str(out/'scrub-proof')],capture_output=True,text=True,timeout=60);(out/'stdout').write_text(q.stdout);(out/'stderr').write_text(q.stderr)
 if q.returncode:raise RuntimeError('Source reset-scrub assertion failed')
 checks=[json.loads(x.split(' ',1)[1])for x in q.stdout.splitlines()if x.startswith('SCRUB_RESULT ')];assert len(checks)==8;bad=subprocess.run([str(out/'scrub-proof'),'--corrupt-readback'],capture_output=True,text=True,timeout=60);(out/'corrupt-readback.stderr').write_text(bad.stderr);assert bad.returncode==2
 inputs=[Path(__file__),source,sdk/'build.json',sdk/'sdk/libiris_saturn_timing.a']+[native/k/'build.json'for k in ['compute','rocket']]+[native/k/'model'/('VSaturnCompute___024root.h'if k=='compute'else'VSaturnRocket___024root.h')for k in ['compute','rocket']];report={'schema':'iris.saturn_source_reset_scrub_proof.v1','argv':command,'checks':checks,'input_sha256':{str(p):sha(p)for p in inputs},'native_sha256':sha(out/'scrub-proof'),'corrupt_readback_rejected':True,'internal_members_readonly':True,'internal_memory_or_state_modified_by_harness':False,'architectural_initialization_program_added':False,'whole_SoC_or_Ethan_image_association_proven':False,'hardware_contacted':False};(out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'checks':checks,'report_sha256':sha(out/'report.json')}))
if __name__=='__main__':main()
