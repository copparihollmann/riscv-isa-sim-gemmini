#include "rvv_integer_eg_source_v1.hpp"
#include <VIntegerSourceSeq.h>
#include <verilated.h>
#include <iostream>
#include <memory>
using namespace iris::rvv_integer_source;
static void need(bool x,const std::string&s){if(!x)throw std::runtime_error(s);}
int main(int argc,char**argv){try{
 unsigned seed=argc>1?std::stoul(argv[1]):1;
 auto context=std::make_unique<VerilatedContext>();context->randReset(2);context->randSeed(seed);
 auto ref=std::make_unique<VIntegerSourceSeq>(context.get());Scheduler model;
 uint64_t rng=seed+1,checks=0,accepted=0,issued=0,raw=0,waw=0,war=0,backpressure=0;
 auto random=[&](){rng^=rng<<13;rng^=rng>>7;rng^=rng<<17;return rng;};
 std::optional<Command> next;
 std::array<std::optional<Micro>,1> reference_pipe{};
 for(uint64_t edge=0;edge<30000;++edge){
   if(edge>=2&&edge<28000&&!next&&random()%4){unsigned lm=1u<<(random()%4),sew=8u<<(random()%4);next=Command{accepted+1,unsigned(accepted%32),unsigned((random()%4)*8),unsigned((random()%4)*8),unsigned((random()%4)*8),sew,lm};}
   Ports ports;
   if(edge<28000){ports.older_reads=random()%3?0:uint64_t(1)<<(random()%64);ports.older_writes=random()%3?0:uint64_t(1)<<(random()%64);ports.source1_ready=random()%7!=0;ports.source2_ready=random()%7!=0;ports.pipe_write_available=random()%7!=0;ports.execution_ready=random()%7!=0;}
   auto e=model.step(edge,next,ports);
   ref->clock=0;ref->reset=edge<2;ref->io_dis_valid=e.iq_head.has_value();
   Command c=e.iq_head.value_or(Command{1,0,8,16,24,32,1});
   ref->io_dis_bits_bits=0x02000057|(c.vs2<<20)|(c.vs1<<15)|(c.vd<<7);
   ref->io_dis_bits_vconfig_vl=256/c.sew*c.lmul;ref->io_dis_bits_vconfig_vtype_vsew=c.sew==8?0:c.sew==16?1:c.sew==32?2:3;
   ref->io_dis_bits_vconfig_vtype_altfmt=0;ref->io_dis_bits_vstart=0;ref->io_dis_bits_rs1_data=0;
   ref->io_dis_bits_vat=c.vat;ref->io_dis_bits_rm=0;ref->io_dis_bits_emul=c.lmul==1?0:c.lmul==2?1:c.lmul==4?2:3;
   ref->io_dis_bits_reduction=0;ref->io_dis_bits_scalar_to_vd0=0;ref->io_dis_bits_wide_vd=0;ref->io_dis_bits_wide_vs2=0;
   ref->io_dis_bits_writes_mask=0;ref->io_dis_bits_reads_vs1_mask=0;ref->io_dis_bits_reads_vs2_mask=0;
   ref->io_dis_bits_renv1=1;ref->io_dis_bits_renv2=1;ref->io_dis_bits_renvd=0;ref->io_dis_bits_renvm=0;ref->io_dis_bits_wvd=1;
   ref->io_older_reads=ports.older_reads;ref->io_vat_head=0;
   ref->io_rvs1_ready=ports.source1_ready;ref->io_rvs2_ready=ports.source2_ready;ref->io_rvd_ready=1;ref->io_rvm_ready=1;
   ref->io_pipe_write_req_available=ports.pipe_write_available;ref->io_iss_ready=ports.execution_ready;ref->io_acc_valid=0;
   ref->io_older_writes=ports.older_writes;ref->eval();
   // Backend's same-VXU exclusion is driven from the reference's actual VAT,
   // and independent prior source issues, never model issue/readiness output.
   for(auto&p:reference_pipe)if(p&&p->command.vat!=ref->io_vat)ref->io_older_writes|=uint64_t(1)<<p->destination;
   ref->eval();
   auto equal=[&](uint64_t actual,uint64_t expected,const char*name){++checks;need(actual==expected,"edge="+std::to_string(edge)+" "+name+" model="+std::to_string(actual)+" source="+std::to_string(expected));};
   bool fire=ref->io_iss_valid&&ref->io_iss_ready;
   if(edge>=2){
    equal(e.seq_ready,ref->io_dis_ready,"dispatch ready");equal(e.seq_before,ref->io_seq_hazard_valid,"seq valid");equal(bool(e.issue),fire,"issue fire");
    if(e.candidate){equal(e.candidate->eidx,ref->io_iss_bits_eidx,"eidx");equal(e.candidate->destination,ref->io_iss_bits_wvd_eg,"destination EG");equal(e.candidate->source1,ref->io_rvs1_bits_eg,"source1 EG");equal(e.candidate->source2,ref->io_rvs2_bits_eg,"source2 EG");equal(e.candidate->tail,ref->io_iss_bits_tail,"tail");equal(e.pending_reads,ref->io_seq_hazard_bits_rintent,"per-EG read intent");equal(e.pending_writes,ref->io_seq_hazard_bits_wintent,"per-EG write intent");equal(e.candidate->command.vat,ref->io_vat,"VAT");}
    raw+=e.raw;waw+=e.waw;war+=e.war;backpressure+=e.candidate&&(!ports.source1_ready||!ports.source2_ready||!ports.pipe_write_available||!ports.execution_ready);
   }
   std::optional<Micro> issued_ref;
   if(fire){++issued;Command rc{0,unsigned(ref->io_iss_bits_vat),unsigned(ref->io_iss_bits_wvd_eg/2),unsigned(ref->io_rvs1_bits_eg/2),unsigned(ref->io_rvs2_bits_eg/2),32,1};issued_ref=Micro{rc,0,unsigned(ref->io_iss_bits_eidx),unsigned(ref->io_iss_bits_wvd_eg),unsigned(ref->io_rvs1_bits_eg),unsigned(ref->io_rvs2_bits_eg),edge,false,bool(ref->io_iss_bits_tail)};}
   reference_pipe[0]=issued_ref;
   if(e.input_fire){++accepted;next.reset();}
   ref->clock=1;ref->eval();context->timeInc(1);
 }
 need(model.empty()&&raw&&waw&&war&&backpressure,"complete directed/random external hazard coverage");
 std::cout<<"{\"pass\":true,\"seed\":"<<seed<<",\"edges\":30000,\"commands\":"<<accepted<<",\"microissues\":"<<issued<<",\"checks\":"<<checks<<",\"RAW_edges\":"<<raw<<",\"WAW_edges\":"<<waw<<",\"WAR_edges\":"<<war<<",\"external_port_stall_edges\":"<<backpressure<<"}\n";
 return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
