#define main original_functional_corpus_main
#include "functional_selftest.cc"
#undef main
#include "ieee_fma_cases.hpp"
static const uint32_t ops[]={MATCH_VFADD_VV,MATCH_VFADD_VF,MATCH_VFSUB_VV,MATCH_VFSUB_VF,MATCH_VFRSUB_VF,MATCH_VFMUL_VV,MATCH_VFMUL_VF,MATCH_VFMACC_VV,MATCH_VFMACC_VF,MATCH_VFNMACC_VV,MATCH_VFNMACC_VF,MATCH_VFMSAC_VV,MATCH_VFMSAC_VF,MATCH_VFNMSAC_VV,MATCH_VFNMSAC_VF,MATCH_VFMADD_VV,MATCH_VFMADD_VF,MATCH_VFNMADD_VV,MATCH_VFNMADD_VF,MATCH_VFMSUB_VV,MATCH_VFMSUB_VF,MATCH_VFNMSUB_VV,MATCH_VFNMSUB_VF,MATCH_VFWADD_VV,MATCH_VFWADD_VF,MATCH_VFWSUB_VV,MATCH_VFWSUB_VF,MATCH_VFWADD_WV,MATCH_VFWADD_WF,MATCH_VFWSUB_WV,MATCH_VFWSUB_WF,MATCH_VFWMUL_VV,MATCH_VFWMUL_VF,MATCH_VFWMACC_VV,MATCH_VFWMACC_VF,MATCH_VFWNMACC_VV,MATCH_VFWNMACC_VF,MATCH_VFWMSAC_VV,MATCH_VFWMSAC_VF,MATCH_VFWNMSAC_VV,MATCH_VFWNMSAC_VF};
static unsigned width(unsigned kind){return kind==3?64:kind==2?32:16;}
static uint64_t read(processor_t& p,unsigned reg,unsigned i,unsigned kind){switch(width(kind)){case 16:return p.VU.elt<uint16_t>(reg,i);case 32:return p.VU.elt<uint32_t>(reg,i);default:return p.VU.elt<uint64_t>(reg,i);}}
static void write(processor_t& p,unsigned reg,unsigned i,unsigned kind,uint64_t v){switch(width(kind)){case 16:p.VU.elt<uint16_t>(reg,i,true)=v;break;case 32:p.VU.elt<uint32_t>(reg,i,true)=v;break;default:p.VU.elt<uint64_t>(reg,i,true)=v;}}
static unsigned vtype(unsigned kind,unsigned lmul=0){return 0xc0|(kind==1?0x100:0)|((kind>=2?kind:1)<<3)|lmul;}
int main(){try{
 Fixture f(true);
 for(const auto& c:ieee_cases){
  auto& p=f.p((&c-ieee_cases)&1);const bool wide=c.code>=23,wi=c.code>=27&&c.code<=30,vf=((ops[c.code]>>12)&7)==5;const unsigned out=wide?(c.kind==2?3:2):c.kind;
  p.VU.set_vl(5,6,8,vtype(c.kind));p.get_state()->frm->write(c.rm);p.get_state()->fflags->write(4);
  for(unsigned i=0;i<64;i++)p.VU.elt<uint8_t>(24,i,true)=0xaa;
  for(unsigned i=0;i<8;i++)p.VU.set_mask_elt(0,i,i==c.lane);
  write(p,8,c.lane,wi?out:c.kind,c.a);write(p,16,c.lane,c.kind,c.b);write(p,24,c.lane,out,c.c);
  p.get_state()->FPR.write(3,float128_t{{c.b,~uint64_t(0)}});
  exec(p,ops[c.code]|(8<<20)|((vf?3:16)<<15)|(24<<7));
  const auto got=read(p,24,c.lane,out),flags=p.get_state()->fflags->read();
  if(got!=c.out||flags!=unsigned(c.flags|4))throw std::runtime_error("IEEE/BF16 handler mismatch case="+std::to_string(&c-ieee_cases)+" got="+std::to_string(got)+","+std::to_string(flags)+" expected="+std::to_string(c.out)+","+std::to_string(c.flags|4));
  for(unsigned i=0;i<64;i++)if(i<c.lane*width(out)/8||i>=(c.lane+1)*width(out)/8)check(p.VU.elt<uint8_t>(24,i)==0xaa,"compute IEEE masked lanes/tails unchanged");
 }
 for(const auto& c:ieee_reductions){
  auto& p=f.p((&c-ieee_reductions)&1);const unsigned out=c.wide?(c.kind==2?3:2):c.kind;
  p.VU.set_vl(5,6,c.vl,vtype(c.kind,c.lmul));p.get_state()->frm->write(c.rm);p.get_state()->fflags->write(4);
  const unsigned vmax=(256/width(c.kind))*(c.lmul==7?1:1<<c.lmul)/(c.lmul==7?2:1);
  for(unsigned i=0;i<vmax;i++){write(p,8,i,c.kind,c.data[i]);p.VU.set_mask_elt(0,i,c.mask[i/8]&(1<<(i%8)));}
  for(unsigned i=0;i<32;i++)p.VU.elt<uint8_t>(24,i,true)=0xa5;write(p,16,0,out,c.seed);
  const uint32_t op=c.wide?(c.ordered?MATCH_VFWREDOSUM_VS:MATCH_VFWREDUSUM_VS):(c.ordered?MATCH_VFREDOSUM_VS:MATCH_VFREDUSUM_VS);
  exec(p,op|(8<<20)|(16<<15)|(24<<7));
  const auto got=read(p,24,0,out),flags=p.get_state()->fflags->read();
  if(got!=c.out||flags!=unsigned(c.flags|4))throw std::runtime_error("IEEE/BF16 reduction mismatch case="+std::to_string(&c-ieee_reductions)+" got="+std::to_string(got)+","+std::to_string(flags)+" expected="+std::to_string(c.out)+","+std::to_string(c.flags|4));
  for(unsigned i=width(out)/8;i<32;i++)check(p.VU.elt<uint8_t>(24,i)==0xa5,"compute reduction tails unchanged");
 }
 // Hart2 and scalar IEEE retain full scalar-FPU flags, unlike compute SIMD.
 for(unsigned hart=0;hart<3;hart++){
  auto& p=f.p(hart);illegal(p,MATCH_FCVT_BF16_S|(3<<15)|(4<<7));illegal(p,MATCH_FCVT_S_BF16|(3<<15)|(4<<7));
  const uint32_t scalar_ops[]={MATCH_FMUL_H,MATCH_FMUL_S,MATCH_FMUL_D};
  const uint64_t maximum[]={0x7bff,0x7f7fffff,0x7fefffffffffffffULL},two[]={0x4000,0x40000000,0x4000000000000000ULL},infinity[]={0x7c00,0x7f800000,0x7ff0000000000000ULL};
  for(unsigned kind=0;kind<3;kind++){
   const uint64_t box=kind==0?0xffffffffffff0000ULL:kind==1?0xffffffff00000000ULL:0;
   p.get_state()->FPR.write(3,float128_t{{maximum[kind]|box,~uint64_t(0)}});p.get_state()->FPR.write(4,float128_t{{two[kind]|box,~uint64_t(0)}});p.get_state()->fflags->write(0);
   exec(p,scalar_ops[kind]|(3<<15)|(4<<20)|(5<<7));
   check(p.get_state()->FPR[5].v[0]==(infinity[kind]|box)&&p.get_state()->fflags->read()==5,"scalar H/S/D full IEEE flags retained on every hart");
  }
 }
 const std::string contradictory=std::string(dma_isa)+"_zvfbfa_zvfbfmin";
 processor_t mx_dma(contradictory.c_str(),"MSU",&f.cfg,&f,2,false,nullptr,std::cerr);
 mx_dma.get_state()->mstatus->write(MSTATUS_FS|MSTATUS_VS);mx_dma.VU.set_vl(5,6,1,0x1c8);
 bool refused=false;try{exec(mx_dma,MATCH_VFADD_VV|(1<<25)|(8<<20)|(16<<15)|(24<<7));}catch(const std::runtime_error& e){refused=std::string(e.what()).find("IRIS_UNSUPPORTED_DATATYPE")!=std::string::npos;}
 check(refused,"hart2 BF16 rejected even when caller advertises contradictory Mx ISA");
 auto& d=f.p(2);d.VU.set_vl(5,6,1,0xd0);d.get_state()->frm->write(0);d.get_state()->fflags->write(0);d.VU.elt<uint32_t>(8,0,true)=0x7f7fffff;d.VU.elt<uint32_t>(16,0,true)=0x40000000;
 exec(d,MATCH_VFMUL_VV|(1<<25)|(8<<20)|(16<<15)|(24<<7));check(d.VU.elt<uint32_t>(24,0)==0x7f800000&&d.get_state()->fflags->read()==5,"hart2 shared IEEE overflow/inexact preserved");
 std::cout<<"ieee_fma_handlers="<<std::size(ieee_cases)<<" reduction_cases="<<std::size(ieee_reductions)<<" forms=45 formats=4 rm=5 mask/tails scalar_bf16_illegal=6 hart2_ieee_flags pass\n";
}catch(const std::exception& e){std::cerr<<e.what()<<"\n";return 1;}catch(trap_t& t){std::cerr<<"unexpected trap "<<t.name()<<" bits="<<std::hex<<last_bits<<" hart="<<last_hart<<"\n";return 1;}}
