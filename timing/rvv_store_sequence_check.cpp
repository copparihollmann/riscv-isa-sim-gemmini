#include "rvv_store_sequence.hpp"
#include "VComputeStoreSeq.h"
#include "VRocketStoreSeq.h"
#include "verilated.h"
#include <chrono>
#include <iostream>
#include <random>
#include <string>
using namespace iris::rvv_store;
static void require(bool b,const std::string&why){if(!b)throw std::runtime_error(why);}
template<class M>void drive(M&m,const Inputs&i){m.reset=i.reset;m.io_dis_valid=i.dispatch_valid;const auto c=i.dispatch.value_or(Command{0x02050027,1,0,0,0,0,0,0,0});m.io_dis_bits_bits=c.raw;m.io_dis_bits_vconfig_vl=c.vl;m.io_dis_bits_vconfig_vtype_vsew=c.vsew;m.io_dis_bits_vstart=c.vstart;m.io_dis_bits_vat=c.vat;m.io_dis_bits_emul=c.emul;m.io_dis_bits_debug_id=c.debug_id;m.io_dis_bits_mop=c.mop;m.io_older_writes=i.older_writes;m.io_vat_head=i.vat_head;m.io_iss_ready=i.data_ready;m.io_rvd_ready=i.vrf_read_ready;m.io_rvm_ready=0;}
template<class M>void check(M&m,const Outputs&o,unsigned edge){
 auto eq=[&](auto a,auto b,const char*k){require(a==b,std::string(k)+" atedge"+std::to_string(edge)+" expected"+std::to_string(uint64_t(a))+" source"+std::to_string(uint64_t(b)));};
 if(!o.control_defined)return;
 eq(o.dispatch_ready,m.io_dis_ready,"dispatch_ready");eq(o.busy,m.io_busy,"busy");eq(o.busy,m.io_seq_hazard_valid,"hazard_valid");eq(o.read_request_valid,m.io_rvd_valid,"read_request_valid");eq(o.data_valid,m.io_iss_valid,"data_valid");eq(o.data_fire,m.io_iss_ready&&m.io_iss_valid,"data_fire");eq(o.dispatch_fire,m.io_dis_ready&&m.io_dis_valid,"dispatch_fire");
 if(o.payload){auto p=*o.payload;eq(p.eg,m.io_rvd_bits_eg,"readEG");eq(p.oldest,m.io_rvd_bits_oldest,"oldest");eq(p.eidx,m.io_iss_bits_eidx,"eidx");eq(p.eew,m.io_iss_bits_elem_size,"EEW");eq(p.vat,m.io_iss_bits_vat,"VAT");eq(p.vat,m.io_vat,"VATsideport");eq(p.debug_id,m.io_iss_bits_debug_id,"debugid");eq(p.tail,m.io_iss_bits_tail,"tail");eq(p.byte_mask,m.io_iss_bits_eidx_mask,"mask");eq(p.read_intent,m.io_seq_hazard_bits_rintent,"rintent");eq(false,m.io_rvm_valid,"unmasked_v0read");eq(false,m.io_iss_bits_use_stmask,"unmasked_storemask");}
}
template<class M>void run(Profile p,unsigned seed){VerilatedContext c;c.threads(1);c.randReset(2);c.randSeed(seed);const char*argv[]={"store-sequence-check"};c.commandArgs(1,argv);Verilated::threadContextp(&c);M m(&c);Sequencer q(p);std::mt19937_64 random(seed);std::optional<Command>pending;uint64_t token=0,accepted=0,micro=0,stalls=0,replacement=0,checks=0,checksum=0;constexpr unsigned cycles=100000;
 for(unsigned edge=0;edge<cycles;++edge){bool reset=edge<2;if(!reset&&!pending&&(random()%4)){unsigned emul=random()%4,eew=random()%4,group=random()%(32>>emul),max=(32u<<emul)>>eew;unsigned vl=1+random()%std::min(256u,max),start=random()%vl;uint32_t raw=0x02050027u|((group<<emul)<<7)|((eew?eew+4:0)<<12);pending=Command{raw,vl,start,emul,unsigned(random()%(p==Profile::Compute128?32:8)),unsigned(token&65535),unsigned(random()%4),0,token++};}
 Inputs i{reset,bool(pending),pending,bool(random()%4),bool(random()%5),(random()%5==0?random():0),unsigned(random()%(p==Profile::Compute128?32:8)),true};if(p==Profile::Rocket256)i.older_writes&=0xffffffffULL;if(reset){i.dispatch_valid=false;i.dispatch.reset();}
 drive(m,i);m.clock=0;Verilated::threadContextp(&c);m.eval();q.evaluate(i);auto o=q.sample();check(m,o,edge);if(o.control_defined){checks+=7+(o.payload?12:0);accepted+=o.dispatch_fire;micro+=o.data_fire;stalls+=o.busy&&!o.data_fire;replacement+=o.busy&&o.dispatch_fire;checksum=checksum*1099511628211ULL+o.dispatch_ready+17*o.data_fire+(o.payload?o.payload->read_intent:0);}
 m.clock=1;m.eval();m.clock=0;m.eval();q.commit();if(o.dispatch_fire)pending.reset();}
 require(accepted>100&&micro>accepted&&replacement>20&&stalls>100,"Meaningful continuous state/backpressure/tail replacement coverage");std::cout<<"CASE {\"profile\":\""<<(p==Profile::Compute128?"compute":"rocket")<<"\",\"seed\":"<<seed<<",\"edges\":"<<cycles<<",\"qualified_field_checks\":"<<checks<<",\"dispatches\":"<<accepted<<",\"microissues\":"<<micro<<",\"blocked_edges\":"<<stalls<<",\"same_edge_tail_replacements\":"<<replacement<<",\"checksum\":"<<checksum<<"}\n";}
int main(){try{for(unsigned seed:{1u,17u,31u}){run<VComputeStoreSeq>(Profile::Compute128,seed);run<VRocketStoreSeq>(Profile::Rocket256,seed);}std::cout<<"DONE passed\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
