#define main original_functional_main
#include "functional_selftest.cc"
#undef main
static unsigned csr_instructions=0;
static uint64_t read_csr(processor_t& p,unsigned csr){p.get_state()->serialized=true;exec(p,(csr<<20)|(2<<12)|(5<<7)|0x73);++csr_instructions;return p.get_state()->XPR[5];}
static void write_csr(processor_t& p,unsigned csr,uint64_t value){p.get_state()->XPR.write(6,value);p.get_state()->serialized=true;exec(p,(csr<<20)|(6<<15)|(1<<12)|0x73);++csr_instructions;}
static void read_illegal(processor_t& p,unsigned csr){bool yes=false;const uint32_t raw=(csr<<20)|(2<<12)|(5<<7)|0x73;try{p.get_state()->serialized=true;exec(p,raw);}catch(trap_t& trap){yes=trap.cause()==2&&trap.get_tval()==raw;}check(yes,"HPM/absent CSR must raise illegal: "+std::to_string(csr));++csr_instructions;}
int main(){try{
 unsigned checks=0;
 for(bool tagged:{false,true}){
  Fixture fixture(true);
  for(unsigned hart=0;hart<3;++hart){
   std::string isa=hart==2?dma_isa:compute_isa;if(tagged)isa+="_zicntr_zihpm_sscofpmf";
   processor_t p(isa.c_str(),"MSU",&fixture.cfg,&fixture,hart,false,nullptr,std::cerr);p.get_state()->mstatus->write(MSTATUS_FS|MSTATUS_VS);
   write_csr(p,CSR_MCOUNTEREN,~reg_t(0));write_csr(p,CSR_SCOUNTEREN,~reg_t(0));write_csr(p,CSR_MCOUNTINHIBIT,~reg_t(0));
   check(read_csr(p,CSR_MCOUNTEREN)==7&&read_csr(p,CSR_SCOUNTEREN)==7&&read_csr(p,CSR_MCOUNTINHIBIT)==5,"Iris zero-HPM enable/inhibit masks independent of caller tags");checks+=3;write_csr(p,CSR_MCOUNTINHIBIT,0);
   for(unsigned slot=0;slot<29;++slot){const unsigned machine=CSR_MHPMCOUNTER3+slot,event=CSR_MHPMEVENT3+slot,user=CSR_HPMCOUNTER3+slot;
    p.get_state()->prv=PRV_M;check(read_csr(p,machine)==0&&read_csr(p,event)==0&&read_csr(p,user)==0,"RAZ slots");write_csr(p,machine,~reg_t(0));write_csr(p,event,~reg_t(0));check(read_csr(p,machine)==0&&read_csr(p,event)==0,"WI slots");checks+=5;
    for(auto privilege:{PRV_S,PRV_U}){p.get_state()->prv=privilege;read_illegal(p,user);++checks;}
    p.get_state()->prv=PRV_M;read_illegal(p,CSR_MHPMCOUNTER3H+slot);read_illegal(p,CSR_HPMCOUNTER3H+slot);checks+=2;
   }
   for(auto privilege:{PRV_M,PRV_S,PRV_U}){p.get_state()->prv=privilege;read_illegal(p,CSR_TIME);read_illegal(p,CSR_TIMEH);checks+=2;(void)read_csr(p,CSR_CYCLE);(void)read_csr(p,CSR_INSTRET);checks+=2;}
  }
 }
 Fixture generic(false);std::string tagged=std::string(compute_isa)+"_zicntr_zihpm";
 processor_t p(tagged.c_str(),"MSU",&generic.cfg,&generic,0,false,nullptr,std::cerr);write_csr(p,CSR_MCOUNTEREN,~reg_t(0));check(read_csr(p,CSR_MCOUNTEREN)==0xffffffffULL,"generic counteren remains ISA-dependent");(void)read_csr(p,CSR_TIME);
 std::cout<<"hpm_source_checks="<<checks<<" csr_instructions="<<csr_instructions<<" harts=3 isa_profiles=2 hardware_hpm=0 generic_preserved pass\n";
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}catch(trap_t& t){std::cerr<<"unexpected HPM trap "<<t.name()<<" bits="<<std::hex<<last_bits<<" hart="<<last_hart<<"\n";return 1;}}
