// The unchanged archived whole-array checker is copied as an include by the
// driver builder. It uses only source OPU ports, actual zeroing, and readout.
#include "frozen_array_check.inc"
static constexpr unsigned values[]={1,2,3,4,5,6,7,8,10,12,14,16,20,24,28,32};
static int signed_value(unsigned i){return (i&16)?-int(values[i&15]):int(values[i&15]);}
static uint32_t fp32(int n){if(!n)return 0;unsigned sign=n<0,u=sign?-n:n,e=0;while((u>>(e+1))!=0)++e;return(sign<<31)|((127+e)<<23)|((u-(1u<<e))<<(23-e));}
static uint8_t fp8(int n,bool e5){unsigned sign=n<0,u=sign?-n:n,e=0;while((u>>(e+1))!=0)++e;unsigned m=e5?2:3,bias=e5?15:7;if(((u-(1u<<e))<<m)%(1u<<e))throw std::runtime_error("inexact FP8 test input");return(sign<<7)|((bias+e)<<m)|(((u-(1u<<e))<<m)>>e);}
int main(int argc,char**argv){
 try{
  const bool wrong=argc==2&&std::string(argv[1])=="--wrong-golden";
  const bool missing=argc==2&&std::string(argv[1])=="--omit-last-subtile";
  if(argc>2||(argc==2&&!wrong&&!missing))throw std::runtime_error("unknown finite control");
  Verilated::randSeed(17);Verilated::randReset(2);Check t;uint64_t scenarios=0,final_words=0,active_cells=0;
  for(unsigned shape:{8u,16u,32u})for(unsigned fmt=0;fmt<5;++fmt)for(unsigned n:{17u,65u}){
   t.initialize();const bool usefp=fmt!=0,Ae5=fmt>=3,Be5=fmt==2||fmt==4;
   const unsigned subs=(shape+15)/16;
   for(unsigned repeat=0;repeat<n;++repeat)for(unsigned sr=0;sr<subs;++sr)for(unsigned sc=0;sc<subs;++sc){
    if(missing&&shape==32&&sr==1&&sc==1)continue;
    t.quiet();t.top.io_op_fp8=usefp;t.top.io_op_e5m2_l=Ae5;t.top.io_op_e5m2_t=Be5;t.top.io_op_rm=0;
    const unsigned slot=2*sr+sc;
    for(unsigned cr=0;cr<4;++cr){*t.mrf[cr]=slot;*t.macc[cr]=1;
     for(unsigned lr=0;lr<4;++lr){const unsigned row=16*sr+cr+4*lr;int a=usefp?signed_value(row):1+row%3;*t.left[cr][lr]=usefp?fp8(a,Ae5):a;*t.row_en[cr][lr]=row<shape;}}
    for(unsigned cc=0;cc<4;++cc)for(unsigned lc=0;lc<4;++lc){const unsigned col=16*sc+cc+4*lc;int b=usefp?signed_value(col):1+col%4;*t.upper[cc][lc]=usefp?fp8(b,Be5):b;*t.col_en[cc][lc]=col<shape;}
    if(usefp){
     for(unsigned pr=0;pr<16;++pr)for(unsigned pc=0;pc<16;++pc){const unsigned row=16*sr+pr/4+4*(pr%4),col=16*sc+pc/4+4*(pc%4);t.golden[pr][pc]=(row<shape&&col<shape)?fp32(int(repeat+1)*signed_value(row)*signed_value(col)):0;}
     if(wrong&&scenarios==2&&repeat+1==n&&sr==0&&sc==0)t.golden[0][0]^=1;
     t.golden_valid=true;
    }
    t.tick();t.golden_valid=false;
    if(usefp){for(auto*p:t.macc)*p=0;t.tick();t.tick();}
   }
   // All16 slots are physically scanned, proving untouched tiles/tails too.
   // The independent whole-square formula is then joined to that exact state.
   t.scan();
   for(unsigned slot=0;slot<16;++slot)for(unsigned pr=0;pr<16;++pr)for(unsigned pc=0;pc<16;++pc){
    const unsigned row=16*(slot>>1)+pr/4+4*(pr%4),col=16*(slot&1)+pc/4+4*(pc%4);
    const bool active=slot<4&&row<shape&&col<shape;
    int a=usefp?signed_value(row):1+row%3,b=usefp?signed_value(col):1+col%4;
    const uint32_t want=active?(usefp?fp32(int(n)*a*b):n*a*b):0;
    if(!t.state[slot][pr][pc].known||t.state[slot][pr][pc].bits!=want)throw std::runtime_error("full-square/slot golden mismatch shape="+std::to_string(shape)+" format="+std::to_string(fmt)+" slot="+std::to_string(slot));
    ++final_words;active_cells+=active;
   }
   ++scenarios;
  }
  if(wrong||missing)throw std::runtime_error("expected finite mutation did not fail");
  std::cout<<"{\"pass\":true,\"scenarios\":"<<scenarios<<",\"final_full_MRF_words\":"<<final_words<<",\"active_tile_words\":"<<active_cells<<",\"actual_source_edges\":"<<t.edges<<",\"actual_defined_output_checks\":"<<t.output_checks<<",\"full_entry_scans\":"<<t.scans<<",\"native_Spike_or_hardware_used\":false}\n";
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
