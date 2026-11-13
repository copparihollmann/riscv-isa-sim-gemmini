#include "VIrisScalarFaddControlReference.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <vector>
struct In{bool sv=false,k1=false,k2=false,rv=false,kx=false,km=false;unsigned rd=0,tag=0;};
struct Reference{bool ex=false,mem=false;unsigned exrd=0,memrd=0;uint8_t wen=0;unsigned slot0=0,slot1=0;std::array<In,4>sh{};
 void commit(const In&i){
  const bool killm=i.km,killx=i.kx||(mem&&killm);auto old=wen;
  wen=(wen>>1)|((mem&&!killm)?2:0);if(old&2)slot0=slot1;if(mem)slot1=memrd;
  mem=ex&&!killx;if(ex)memrd=exrd;ex=i.rv;if(i.rv)exrd=i.rd;
  for(unsigned j=3;j;--j)sh[j]=sh[j-1];sh[0]=i;
 }
};
int main(int argc,char**argv){try{VerilatedContext ctx;ctx.commandArgs(argc,argv);ctx.threads(1);ctx.randSeed(17);VIrisScalarFaddControlReference d(&ctx);uint64_t checks=0,cycles=0,shlive=0,rolive=0;auto input=[&](In i){d.sh_valid=i.sv;d.sh_k1=i.k1;d.sh_k2=i.k2;d.sh_rd=i.rd;d.sh_tag=i.tag;d.ro_valid=i.rv;d.ro_kx=i.kx;d.ro_km=i.km;const unsigned fmt=i.tag==0?2:i.tag==1?0:1;d.ro_inst=(fmt<<25)|(2<<20)|(1<<15)|(i.rd<<7)|0x53;};auto edge=[&]{d.clock=1;d.eval();ctx.timeInc(1);d.clock=0;d.eval();ctx.timeInc(1);};
 d.reset=1;d.ro_load=0;d.ro_load_rd=0;input({});for(unsigned j=0;j<8;++j)edge();d.reset=0;
 // Establish FP storage through actual load write ports; clear unreset busy
 // control through an actual FADD request followed by invalid bubbles.
 for(unsigned j=0;j<2;++j){d.ro_load=1;d.ro_load_rd=j+1;edge();}d.ro_load=0;edge();In warm;warm.rv=true;warm.rd=3;warm.tag=2;input(warm);edge();input({});for(unsigned j=0;j<10;++j)edge();Reference ref;
 uint64_t rng=0x839291983ULL;auto random=[&]{rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;};
 for(unsigned t=0;t<20000;++t){In i;i.sv=(random()%4)!=0;i.rv=(random()%4)!=0;i.k1=random()%19==0;i.k2=random()%23==0;i.kx=random()%17==0;i.km=random()%29==0;i.rd=random()%32;i.tag=random()%3;input(i);d.eval();
  const bool sv=ref.sh[3].sv&&!ref.sh[2].k1&&!ref.sh[1].k2;
  if(bool(d.sh_out_valid)!=sv)throw std::runtime_error("Shuttle pre-edge valid phase t="+std::to_string(t));++checks;
  if(sv){if(d.sh_out_rd!=ref.sh[3].rd||d.sh_out_tag!=ref.sh[3].tag)throw std::runtime_error("Shuttle tag phase");checks+=2;++shlive;}
  const bool rw=ref.wen&1;if(bool(d.ro_flags_valid)!=rw||bool(d.ro_rf_write)!=rw||d.ro_nack)throw std::runtime_error("Rocket pre-edge flags/write phase t="+std::to_string(t));checks+=3;
  if(rw){if(d.ro_rf_rd!=ref.slot0)throw std::runtime_error("Rocket FPR destination phase");++checks;++rolive;}
  if(bool(d.ro_ready)!=( !ref.ex&&!ref.mem&&!ref.wen))throw std::runtime_error("Rocket FCSR ready phase");++checks;
  edge();ref.commit(i);++cycles;
 }
 std::cout<<"{\"cycles\":"<<cycles<<",\"checks\":"<<checks<<",\"Shuttle_valid_outputs\":"<<shlive<<",\"Rocket_FPR_writes\":"<<rolive<<",\"source_same_edge_write_sample_phase\":\"pre-edge outputs, then one commit; no internal state injection\",\"pass\":true}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
