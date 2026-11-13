#define main original_functional_corpus_main
#include "functional_fixture.cc"
#undef main
#include "iris_fp8.hpp"
#include "iris_ieee_fma.hpp"
#include "shared_fma_cases.hpp"
static const uint32_t operations[]={
 MATCH_VFADD_VV,MATCH_VFADD_VF,MATCH_VFSUB_VV,MATCH_VFSUB_VF,MATCH_VFRSUB_VF,MATCH_VFMUL_VV,MATCH_VFMUL_VF,
 MATCH_VFMACC_VV,MATCH_VFMACC_VF,MATCH_VFNMACC_VV,MATCH_VFNMACC_VF,MATCH_VFMSAC_VV,MATCH_VFMSAC_VF,
 MATCH_VFNMSAC_VV,MATCH_VFNMSAC_VF,MATCH_VFMADD_VV,MATCH_VFMADD_VF,MATCH_VFNMADD_VV,MATCH_VFNMADD_VF,
 MATCH_VFMSUB_VV,MATCH_VFMSUB_VF,MATCH_VFNMSUB_VV,MATCH_VFNMSUB_VF,
 MATCH_VFWADD_VV,MATCH_VFWADD_VF,MATCH_VFWSUB_VV,MATCH_VFWSUB_VF,MATCH_VFWADD_WV,MATCH_VFWADD_WF,
 MATCH_VFWSUB_WV,MATCH_VFWSUB_WF,MATCH_VFWMUL_VV,MATCH_VFWMUL_VF,MATCH_VFWMACC_VV,MATCH_VFWMACC_VF,
 MATCH_VFWNMACC_VV,MATCH_VFWNMACC_VF,MATCH_VFWMSAC_VV,MATCH_VFWMSAC_VF,MATCH_VFWNMSAC_VV,MATCH_VFWNMSAC_VF};
static unsigned type(unsigned kind,unsigned lmul=0){return 0xc0|((kind==3?3:kind==2?2:1)<<3)|lmul;}
static uint64_t read(processor_t& p,unsigned reg,unsigned index,iris_fma::Kind kind){if(kind==iris_fma::H)return p.VU.elt<uint16_t>(reg,index);if(kind==iris_fma::S)return p.VU.elt<uint32_t>(reg,index);return p.VU.elt<uint64_t>(reg,index);}
static void write(processor_t& p,unsigned reg,unsigned index,iris_fma::Kind kind,uint64_t value){if(kind==iris_fma::H)p.VU.elt<uint16_t>(reg,index,true)=value;else if(kind==iris_fma::S)p.VU.elt<uint32_t>(reg,index,true)=value;else p.VU.elt<uint64_t>(reg,index,true)=value;}
int main(){try{
 Fixture fixture(true);auto& p=fixture.p(2);
 for(const auto& c:shared_cases){
  const auto in=iris_fma::Kind(c.kind),out=c.code>=23?(in==iris_fma::S?iris_fma::D:iris_fma::S):in;
  const bool wide_input=c.code>=27&&c.code<=30,vf=((operations[c.code]>>12)&7)==5;
  p.VU.set_vl(5,6,c.vl,type(c.kind,c.lmul));p.VU.set_mask_elt(0,0,c.active);
  for(unsigned i=0;i<256;++i)p.VU.elt<uint8_t>(24,i,true)=0xa5;
  write(p,8,0,wide_input?out:in,c.a);write(p,16,0,in,c.b);write(p,24,0,out,c.c);
  p.get_state()->FPR.write(3,float128_t{{c.b|((&c-shared_cases)%2?~uint64_t(0)<<(iris_fma::width(in)%64):0),~uint64_t(0)}});
  // Width64 is never boxed; reset that case after avoiding a shift-by64.
  if(in==iris_fma::D)p.get_state()->FPR.write(3,float128_t{{c.b,~uint64_t(0)}});
  p.get_state()->frm->write(c.rm);p.get_state()->fflags->write(8);
  p.get_state()->mstatus->write((p.get_state()->mstatus->read()&~MSTATUS_FS)|0x2000);
  exec(p,operations[c.code]|(8<<20)|((vf?3:16)<<15)|(24<<7));
  const auto got=read(p,24,0,out),flags=p.get_state()->fflags->read();
  if(got!=c.out||flags!=(c.flags|8u))throw std::runtime_error("shared handler case="+std::to_string(&c-shared_cases)+" got="+std::to_string(got)+","+std::to_string(flags)+" want="+std::to_string(c.out)+","+std::to_string(c.flags|8u));
  const auto fs=p.get_state()->mstatus->read()&MSTATUS_FS;
  check(fs==MSTATUS_FS,"Rocket haveFSDirty=false preserves nonzero FS as Dirty, including VV VL0");
  for(unsigned i=iris_fma::width(out)/8;i<256;++i)check(p.VU.elt<uint8_t>(24,i)==0xa5,"shared masks/tails unchanged");
 }
 for(const auto& c:shared_reductions){
  const auto in=iris_fma::Kind(c.kind),out=c.wide?(in==iris_fma::S?iris_fma::D:iris_fma::S):in;
  p.VU.set_vl(5,6,c.vl,type(c.kind,c.lmul));
  for(unsigned i=0;i<c.vl;++i){write(p,8,i,in,c.data[i]);p.VU.set_mask_elt(0,i,c.mask[i/8]&(1<<(i%8)));}
  for(unsigned i=0;i<32;++i)p.VU.elt<uint8_t>(24,i,true)=0xa5;write(p,16,0,out,c.seed);
  p.get_state()->frm->write(c.rm);p.get_state()->fflags->write(8);
  const auto op=c.wide?(c.ordered?MATCH_VFWREDOSUM_VS:MATCH_VFWREDUSUM_VS):(c.ordered?MATCH_VFREDOSUM_VS:MATCH_VFREDUSUM_VS);
  exec(p,op|(8<<20)|(16<<15)|(24<<7));
  if(read(p,24,0,out)!=c.out||p.get_state()->fflags->read()!=(c.flags|8u))throw std::runtime_error("shared reduction case="+std::to_string(&c-shared_reductions));
  for(unsigned i=iris_fma::width(out)/8;i<32;++i)check(p.VU.elt<uint8_t>(24,i)==0xa5,"shared reduction tails unchanged");
 }
 p.VU.set_vl(5,6,1,type(0));
 for(const auto op:{MATCH_VFADD_VV,MATCH_VFREDUSUM_VS}){
  p.VU.vstart->write(1);bool correct=false;
  try{exec(p,op|(1<<25)|(8<<20)|(16<<15)|(24<<7));}catch(trap_t& trap){correct=trap.cause()==CAUSE_ILLEGAL_INSTRUCTION&&trap.get_tval()==0x80000000;}
  check(correct,"shared vstart illegal tval is source instruction PC");
 }
 p.VU.vstart->write(0);p.get_state()->mstatus->write(p.get_state()->mstatus->read()&~MSTATUS_FS);
 p.VU.set_vl(5,6,0,type(0));exec(p,MATCH_VFADD_VV|(8<<20)|(16<<15)|(24<<7));
 check((p.get_state()->mstatus->read()&MSTATUS_FS)==0,"shared VV VL0 permits FSOff without write");
 illegal(p,MATCH_VFADD_VF|(8<<20)|(3<<15)|(24<<7));
 p.VU.set_vl(5,6,1,type(0));
 bool asserted=false;try{exec(p,MATCH_VFADD_VV|(8<<20)|(16<<15)|(24<<7));}catch(const std::runtime_error& error){asserted=std::string(error.what()).find("mstatus.FS")!=std::string::npos;}
 check(asserted,"masked shared FPU still asserts with FSOff");
 std::cout<<"shared_fma_handlers="<<std::size(shared_cases)<<" reductions="<<std::size(shared_reductions)<<" forms=45 masked_flags VFboxing vstart FS pass\n";
}catch(const std::exception& error){std::cerr<<error.what()<<"\n";return 1;}catch(trap_t& trap){std::cerr<<"unexpected shared trap "<<trap.name()<<" bits="<<std::hex<<last_bits<<"\n";return 1;}}
