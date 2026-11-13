#define main original_functional_corpus_main
#include "functional_fixture.cc"
#undef main
#include "iris_native_fp8.hpp"
#include "native_fp8_cases.hpp"
#include "wide_fp8_cases.hpp"
#include "fp8_reduction_cases.hpp"
int main(){
 try{
  Fixture f(true);
  for(const auto& c:native_cases){
   auto& p=f.p((&c-native_cases)&1);
   p.get_state()->mstatus->write(p.get_state()->mstatus->read()|MSTATUS_FS);
   p.get_state()->frm->write(c.rm);p.get_state()->fflags->write(4);
   p.VU.set_vl(5,6,8,0xc0|(c.fmt<<8));
   for(unsigned i=0;i<8;i++){p.VU.elt<uint8_t>(8,i,true)=0;p.VU.elt<uint8_t>(16,i,true)=0;p.VU.elt<uint8_t>(24,i,true)=0xaa;p.VU.set_mask_elt(0,i,i==c.lane);}
   p.VU.elt<uint8_t>(8,c.lane,true)=c.a;p.VU.elt<uint8_t>(16,c.lane,true)=c.b;p.VU.elt<uint8_t>(24,c.lane,true)=c.c;
   const uint32_t cmds[]={MATCH_VFMACC_VV,MATCH_VFMSAC_VV,MATCH_VFNMSAC_VV,MATCH_VFNMACC_VV};
   exec(p,cmds[c.op]|(8<<20)|(16<<15)|(24<<7));
   check(p.VU.elt<uint8_t>(24,c.lane)==c.out,"actual native FP8 masked handler oracle result");
   check(p.get_state()->fflags->read()==unsigned(c.flags|4),"actual native FP8 lane-dependent flags");
   for(unsigned i=0;i<8;i++)if(i!=c.lane)check(p.VU.elt<uint8_t>(24,i)==0xaa,"masked FP8 lanes untouched");
  }
  auto& dma=f.p(2);dma.VU.set_vl(5,6,1,0xc0);
  bool dma_refused=false;try{exec(dma,MATCH_VFADD_VV|(1<<25)|(8<<20)|(16<<15)|(24<<7));}catch(const std::runtime_error& e){dma_refused=std::string(e.what()).find("IRIS_UNSUPPORTED_DATATYPE")!=std::string::npos;}
  check(dma_refused,"hart2 Mx dtype job has explicit unsupported diagnostic");
  auto& p=f.p();
  const uint32_t ops[]={MATCH_VFADD_VV,MATCH_VFADD_VF,MATCH_VFSUB_VV,MATCH_VFSUB_VF,MATCH_VFRSUB_VF,MATCH_VFMUL_VV,MATCH_VFMUL_VF,MATCH_VFMACC_VV,MATCH_VFMACC_VF,MATCH_VFNMACC_VV,MATCH_VFNMACC_VF,MATCH_VFMSAC_VV,MATCH_VFMSAC_VF,MATCH_VFNMSAC_VV,MATCH_VFNMSAC_VF,MATCH_VFMADD_VV,MATCH_VFMADD_VF,MATCH_VFNMADD_VV,MATCH_VFNMADD_VF,MATCH_VFMSUB_VV,MATCH_VFMSUB_VF,MATCH_VFNMSUB_VV,MATCH_VFNMSUB_VF};
  for(unsigned fmt=0;fmt<2;fmt++)for(unsigned lmul=0;lmul<4;lmul++)for(unsigned rm=0;rm<5;rm++)for(auto op:ops){
    const unsigned vmax=32<<lmul,vl=vmax-3;
    p.VU.set_vl(5,6,vl,0xc0|lmul|(fmt<<8));p.get_state()->frm->write(rm);p.get_state()->fflags->write(0);
    const uint8_t a=fmt?0x3e:0x3c,b=0x40,c=fmt?0x38:0x30; // 1.5,2,0.5
    for(unsigned i=0;i<vmax;i++){p.VU.elt<uint8_t>(8,i,true)=a;p.VU.elt<uint8_t>(16,i,true)=b;p.VU.elt<uint8_t>(24,i,true)=c;}
    const bool vf=((op>>12)&7)==5;
    p.get_state()->FPR.write(3,float128_t{{uint64_t(0x1234567800000000ULL|b),~uint64_t(0)}});
    const unsigned f6=op>>26;
    uint8_t expected=0;
    switch(f6){
      case 0:case 0x2c:expected=fmt?0x43:0x46;break; // 3.5
      case 2:case 0x2a:expected=fmt?0xb8:0xb0;break; // -0.5
      case 0x27:case 0x2b:expected=fmt?0x38:0x30;break; // 0.5
      case 0x24:expected=fmt?0x42:0x44;break; // 3
      case 0x2d:expected=fmt?0xc3:0xc6;break; // -3.5
      case 0x2e:case 0x28:expected=fmt?0x41:0x42;break; // 2.5
      case 0x2f:case 0x29:expected=fmt?0xc1:0xc2;break; // -2.5
      default:throw std::runtime_error("missing opcode golden");
    }
    exec(p,op|(1<<25)|(8<<20)|((vf?3:16)<<15)|(24<<7));
    for(unsigned i=0;i<vl;i++)check(p.VU.elt<uint8_t>(24,i)==expected,"all23 native FP8 forms LMUL1/2/4/8");
    for(unsigned i=vl;i<vmax;i++)check(p.VU.elt<uint8_t>(24,i)==c,"FP8 tails untouched");
  }
  const uint32_t wide_ops[]={MATCH_VFWADD_VV,MATCH_VFWADD_VF,MATCH_VFWSUB_VV,MATCH_VFWSUB_VF,MATCH_VFWADD_WV,MATCH_VFWADD_WF,MATCH_VFWSUB_WV,MATCH_VFWSUB_WF,MATCH_VFWMUL_VV,MATCH_VFWMUL_VF,MATCH_VFWMACC_VV,MATCH_VFWMACC_VF,MATCH_VFWNMACC_VV,MATCH_VFWNMACC_VF,MATCH_VFWMSAC_VV,MATCH_VFWMSAC_VF,MATCH_VFWNMSAC_VV,MATCH_VFWNMSAC_VF};
  for(const auto& c:wide_cases){
    auto& w=f.p((&c-wide_cases)&1);w.get_state()->mstatus->write(w.get_state()->mstatus->read()|MSTATUS_FS);
    w.get_state()->frm->write(c.rm);w.get_state()->fflags->write(4);w.VU.set_vl(5,6,4,0xc0|(c.fmt<<8));
    const bool wide_input=c.code>=4&&c.code<=7,vf=((wide_ops[c.code]>>12)&7)==5;
    for(unsigned i=0;i<4;i++){w.VU.elt<uint16_t>(24,i,true)=0xaaaa;w.VU.set_mask_elt(0,i,i==c.lane);}
    if(wide_input)w.VU.elt<uint16_t>(8,c.lane,true)=c.a;else w.VU.elt<uint8_t>(8,c.lane,true)=c.a;
    w.VU.elt<uint8_t>(16,c.lane,true)=c.b;w.VU.elt<uint16_t>(24,c.lane,true)=c.c;
    w.get_state()->FPR.write(3,float128_t{{c.b,~uint64_t(0)}});
    exec(w,wide_ops[c.code]|(8<<20)|((vf?3:16)<<15)|(24<<7));
    if(w.VU.elt<uint16_t>(24,c.lane)!=c.out||w.get_state()->fflags->read()!=unsigned(c.flags|4))throw std::runtime_error("widening FP8 oracle mismatch case="+std::to_string(&c-wide_cases)+" got="+std::to_string(w.VU.elt<uint16_t>(24,c.lane))+","+std::to_string(w.get_state()->fflags->read())+" want="+std::to_string(c.out)+","+std::to_string(c.flags|4));
    for(unsigned i=0;i<4;i++)if(i!=c.lane)check(w.VU.elt<uint16_t>(24,i)==0xaaaa,"widened FP8 mask preserves inactive lanes");
  }
  for(const auto& c:reduction_cases){
    auto& r=f.p((&c-reduction_cases)&1);r.get_state()->mstatus->write(r.get_state()->mstatus->read()|MSTATUS_FS);
    r.get_state()->frm->write(c.rm);r.get_state()->fflags->write(4);r.VU.set_vl(5,6,c.vl,0xc0|c.lmul|(c.fmt<<8));
    const unsigned vmax=c.lmul==7?16:32<<c.lmul;
    for(unsigned i=0;i<vmax;i++){r.VU.elt<uint8_t>(8,i,true)=c.data[i];r.VU.set_mask_elt(0,i,c.mask[i/8]&(1<<(i%8)));}
    for(unsigned i=0;i<32;i++)r.VU.elt<uint8_t>(24,i,true)=0xa5;
    if(c.wide)r.VU.elt<uint16_t>(16,0,true)=c.seed;else r.VU.elt<uint8_t>(16,0,true)=c.seed;
    const uint32_t opcode=c.wide?(c.ordered?MATCH_VFWREDOSUM_VS:MATCH_VFWREDUSUM_VS):(c.ordered?MATCH_VFREDOSUM_VS:MATCH_VFREDUSUM_VS);
    exec(r,opcode|(8<<20)|(16<<15)|(24<<7));
    const uint16_t actual=c.wide?r.VU.elt<uint16_t>(24,0):r.VU.elt<uint8_t>(24,0);
    if(actual!=c.out||r.get_state()->fflags->read()!=unsigned(c.flags|4))throw std::runtime_error("FP8 reduction sourcegraph oracle mismatch case="+std::to_string(&c-reduction_cases)+" got="+std::to_string(actual)+","+std::to_string(r.get_state()->fflags->read())+" want="+std::to_string(c.out)+","+std::to_string(c.flags|4));
    for(unsigned i=c.wide?2:1;i<32;i++)check(r.VU.elt<uint8_t>(24,i)==0xa5,"reduction destination tails preserve contents");
  }
  p.VU.set_vl(5,6,1,0xc0);p.get_state()->mstatus->write(p.get_state()->mstatus->read()&~MSTATUS_FS);
  bool fs_assert=false;try{exec(p,MATCH_VFADD_VV|(1<<25)|(8<<20)|(16<<15)|(24<<7));}catch(const std::runtime_error& e){fs_assert=std::string(e.what()).find("IRIS_RTL_ASSERT")!=std::string::npos;}
  check(fs_assert,"native FP8 FS-off write models RTL assertion");
  p.VU.set_vl(5,6,0,0xc0);exec(p,MATCH_VFADD_VV|(1<<25)|(8<<20)|(16<<15)|(24<<7));
  std::cout<<"native_fp8_handlers="<<std::size(native_cases)<<" wide_cases="<<std::size(wide_cases)<<" reduction_cases="<<std::size(reduction_cases)<<" forms=23+18+4 formats=2 rm=5 lmul=4 mask/tails pass\n";
 }catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}catch(trap_t& t){std::cerr<<"unexpected trap "<<t.name()<<"\n";return 1;}
}
