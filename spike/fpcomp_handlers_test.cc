#define main original_functional_main
#include "functional_fixture.cc"
#undef main
#include "fpcomp_cases.hpp"
#include "iris_fpcomp.hpp"
static const uint32_t operations[]={MATCH_VFMIN_VV,MATCH_VFMIN_VF,MATCH_VFMAX_VV,MATCH_VFMAX_VF,MATCH_VFSGNJ_VV,MATCH_VFSGNJ_VF,MATCH_VFSGNJN_VV,MATCH_VFSGNJN_VF,MATCH_VFSGNJX_VV,MATCH_VFSGNJX_VF,MATCH_VMFEQ_VV,MATCH_VMFEQ_VF,MATCH_VMFNE_VV,MATCH_VMFNE_VF,MATCH_VMFLT_VV,MATCH_VMFLT_VF,MATCH_VMFLE_VV,MATCH_VMFLE_VF,MATCH_VMFGT_VF,MATCH_VMFGE_VF,MATCH_VFREDMIN_VS,MATCH_VFREDMAX_VS};
static unsigned vtype(const CmpCase& c){return 0xc0|((c.width==64?3:c.width==32?2:1)<<3)|(c.alt?0x100:0)|c.lmul;}
int main(){try{
 Fixture f(true);unsigned cases=0;
 Fixture generic(false);
 for(unsigned width:{16u,32u,64u}){
  auto& p=generic.p();p.VU.set_vl(5,6,1,0xc0|((width==64?3:width==32?2:1)<<3));
  auto put=[&](unsigned reg,uint64_t value){if(width==16)p.VU.elt<uint16_t>(reg,0,true)=value;else if(width==32)p.VU.elt<uint32_t>(reg,0,true)=value;else p.VU.elt<uint64_t>(reg,0,true)=value;};
  auto get=[&]()->uint64_t{if(width==16)return p.VU.elt<uint16_t>(24,0);if(width==32)return p.VU.elt<uint32_t>(24,0);return p.VU.elt<uint64_t>(24,0);};
  p.get_state()->fflags->write(8);put(8,0);put(16,iris_cmp::sign(width));exec(p,MATCH_VFMAX_VV|(1<<25)|(8<<20)|(16<<15)|(24<<7));
  check(get()==0&&p.get_state()->fflags->read()==8,"generic max signed-zero stays architectural");
  const auto nan=iris_cmp::infinity(width)|(uint64_t(1)<<(iris_cmp::fraction(width)-1));put(8,nan);put(16,0);
  exec(p,MATCH_VFSGNJ_VV|(1<<25)|(8<<20)|(16<<15)|(24<<7));check(get()==nan&&p.get_state()->fflags->read()==8,"generic sign-injection preserves flags");
  p.VU.set_mask_elt(0,0,false);p.VU.set_mask_elt(24,0,true);put(8,iris_cmp::infinity(width)|1);exec(p,MATCH_VMFEQ_VV|(8<<20)|(16<<15)|(24<<7));
  check(p.VU.mask_elt(24,0)&&p.get_state()->fflags->read()==8,"generic masked signaling NaN produces no flags");
 }

 for(const auto& c:cmp_cases)for(unsigned hart=c.hart;hart<(c.hart?3:2);++hart){
  auto& p=f.p(hart);
  for(unsigned i=0;i<256;++i){p.VU.elt<uint8_t>(8,i,true)=c.a[i];p.VU.elt<uint8_t>(16,i,true)=c.b[i];p.VU.elt<uint8_t>(24,i,true)=0xa5;}
  if(c.code>=20){if(c.width==16)p.VU.elt<uint16_t>(16,0,true)=c.seed;else if(c.width==32)p.VU.elt<uint32_t>(16,0,true)=c.seed;else p.VU.elt<uint64_t>(16,0,true)=c.seed;}
  for(unsigned i=0;i<128;++i)p.VU.set_mask_elt(0,i,c.mask[i/8]&(1<<(i%8)));
  p.VU.set_vl(5,6,c.vl,vtype(c));
  p.get_state()->FPR.write(3,float128_t{{c.scalar,~uint64_t(0)}});
  p.get_state()->frm->write((&c-cmp_cases)%8);p.get_state()->fflags->write(8);
  p.get_state()->mstatus->write((p.get_state()->mstatus->read()&~MSTATUS_FS)|0x2000);
  const bool vf=((operations[c.code]>>12)&7)==5;
  exec(p,operations[c.code]|(8<<20)|((vf?3:16)<<15)|(24<<7)|(c.vm<<25));
  for(unsigned i=0;i<256;++i)if(p.VU.elt<uint8_t>(24,i)!=c.out[i])throw std::runtime_error("FPComp output case="+std::to_string(&c-cmp_cases)+" hart="+std::to_string(hart)+" byte="+std::to_string(i)+" got="+std::to_string(p.VU.elt<uint8_t>(24,i))+" expected="+std::to_string(c.out[i]));
  check(p.get_state()->fflags->read()==unsigned(c.flags|8),"FPComp source selected flags case="+std::to_string(&c-cmp_cases));
  check((p.get_state()->mstatus->read()&MSTATUS_FS)==(hart==2||c.vl||vf?MSTATUS_FS:0x2000),"FPComp source FS state");++cases;
 }
 for(unsigned hart:{0u,2u}){
  std::string isa=hart?dma_isa:compute_isa;isa.replace(isa.find("zvl256b"),7,"zvl512b");
  processor_t other(isa.c_str(),"MSU",&f.cfg,&f,hart,false,nullptr,std::cerr);other.get_state()->mstatus->write(MSTATUS_FS|MSTATUS_VS);other.VU.vstart->write(0);other.VU.set_vl(5,6,1,0xd0);
  bool closed=false;try{exec(other,MATCH_VFSGNJ_VV|(8<<20)|(16<<15)|(24<<7));}catch(const std::runtime_error& error){closed=std::string(error.what()).find("IRIS_UNSUPPORTED_VECTOR_CONFIG")!=std::string::npos;}check(closed,"contradictory VLEN must fail closed");
 }
 for(unsigned hart=0;hart<3;++hart)for(unsigned alt=0;alt<2;++alt)for(unsigned code=0;code<22;++code){
  auto& p=f.p(hart);p.VU.set_vl(5,6,1,0xc0|(alt<<8));const bool vf=((operations[code]>>12)&7)==5;
  const uint32_t raw=operations[code]|(8<<20)|((vf?3:16)<<15)|(24<<7)|(1<<25);
  p.get_mmu()->store<uint32_t>(0x80000000,raw);p.get_mmu()->flush_icache();p.get_state()->pc=0x80000000;p.step(1);
  check(p.get_state()->mcause->read()==2&&p.get_state()->mepc->read()==0x80000000&&p.get_state()->mtval->read()==raw,"source-absent SEW8 FPComp must trap architectural illegal");
 }
 for(unsigned hart=0;hart<3;++hart){auto& p=f.p(hart);
  p.VU.set_vl(5,6,1,0xd0);p.VU.vstart->write(1);
  const uint32_t vf=MATCH_VFMIN_VF|(8<<20)|(3<<15)|(24<<7),vv=MATCH_VFMIN_VV|(8<<20)|(16<<15)|(24<<7);
  for(bool off_vs:{false,true}){
   const auto status=p.get_state()->mstatus->read();p.get_state()->mstatus->write(off_vs?(status|MSTATUS_FS)&~MSTATUS_VS:(status|MSTATUS_VS)&~MSTATUS_FS);
   const auto raw=off_vs?vv:vf;bool correct=false;try{exec(p,raw);}catch(trap_t& trap){correct=trap.cause()==2&&trap.get_tval()==raw;}check(correct,"core-disabled FP/VS illegal takes priority over vector vstart PC trap");
  }
  p.get_state()->mstatus->write(p.get_state()->mstatus->read()|MSTATUS_FS|MSTATUS_VS);p.VU.vstart->write(0);
 }
 for(unsigned hart=0;hart<3;++hart){auto& p=f.p(hart);p.VU.set_vl(5,6,0,0xd0);p.get_state()->mstatus->write(p.get_state()->mstatus->read()&~MSTATUS_FS);
  exec(p,MATCH_VFSGNJ_VV|(8<<20)|(16<<15)|(24<<7));illegal(p,MATCH_VFMIN_VF|(8<<20)|(3<<15)|(24<<7));
  p.VU.set_vl(5,6,1,0xd0);p.VU.set_mask_elt(0,0,false);bool asserted=false;
  try{exec(p,MATCH_VMFEQ_VV|(8<<20)|(16<<15)|(24<<7));}catch(const std::runtime_error& e){asserted=std::string(e.what()).find("mstatus.FS")!=std::string::npos;}
  check(asserted,"FPComp masked FSOff assertion");p.get_state()->mstatus->write(p.get_state()->mstatus->read()|MSTATUS_FS);p.VU.vstart->write(1);
  bool trapped=false;try{exec(p,MATCH_VFMAX_VV|(8<<20)|(16<<15)|(24<<7));}catch(trap_t& trap){trapped=trap.cause()==2&&trap.get_tval()==0x80000000;}check(trapped,"FPComp vstart source PC tval");p.VU.vstart->write(0);
 }
 std::cout<<"fpcomp_handlers="<<cases<<" oracle_cases="<<std::size(cmp_cases)<<" forms=22 all3harts source_flags signed_zero mask_tail altfmt FS vstart illegal_sew8=132 generic_semantics=9 core_priority=6 config_refusals=2 pass\n";
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}catch(trap_t& t){std::cerr<<"unexpected FPComp trap "<<t.name()<<" bits="<<std::hex<<last_bits<<" hart="<<last_hart<<"\n";return 1;}}
