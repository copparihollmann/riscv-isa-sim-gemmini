if(P.get_id()==2){
#include "iris_shared_reduction_body.h"
}else{
// Compute SegmentedFMAPipe reduction order and non-FP8 flag wiring.
const unsigned iris_f6=insn.bits()>>26,iris_rm=STATE.frm->read_defined(pc);
const bool iris_wide=iris_f6>=0x30,iris_ordered=(iris_f6&2)!=0;
VI_CHECK_REDUCTION(iris_wide);
require(P.VU.vsew==16||P.VU.vsew==32||P.VU.vsew==64);
if(P.VU.altfmt&&P.VU.vsew>=32)throw std::runtime_error("IRIS_UNSUPPORTED_DATATYPE: no segmented FMA output selection for wide alternate format");
require((P.VU.vsew==16&&p->extension_enabled(P.VU.altfmt?EXT_ZVFBFA:EXT_ZVFH))||(P.VU.vsew==32&&p->get_isa().get_zvf())||(P.VU.vsew==64&&p->get_isa().get_zvd()));
if(iris_rm>4)throw std::runtime_error("IRIS_UNSUPPORTED_ROUNDING_MODE compute reduction");
const iris_fma::Kind iris_in=P.VU.vsew==64?iris_fma::D:P.VU.vsew==32?iris_fma::S:P.VU.altfmt?iris_fma::BF:iris_fma::H;
const iris_fma::Kind iris_out=iris_wide?(iris_in==iris_fma::S?iris_fma::D:iris_fma::S):iris_in;
auto read=[&](unsigned reg,reg_t i,iris_fma::Kind kind)->uint64_t{switch(iris_fma::width(kind)){case 16:return P.VU.elt<uint16_t>(reg,i);case 32:return P.VU.elt<uint32_t>(reg,i);default:return P.VU.elt<uint64_t>(reg,i);}};
const reg_t iris_vl=P.VU.vl->read();
if(iris_vl){
 if(!STATE.sstatus->enabled(MSTATUS_FS))throw std::runtime_error("IRIS_RTL_ASSERT: compute reduction write requires mstatus.FS > 0");
 const unsigned lanes=128/iris_fma::width(iris_out);
 uint64_t accum[8]={};accum[0]=read(insn.rs1(),0,iris_out);uint8_t iris_flags=0;
 auto add=[&](uint64_t a,uint64_t b,unsigned lane,bool narrow){
  uint64_t aa,bb;
  {IrisSoftfloatScope scope(iris_rm);aa=iris_fma::input(a,iris_out,iris_out,lane);bb=iris_fma::input(b,narrow?iris_in:iris_out,iris_out,lane);}
  return iris_fma::fused(aa,iris_fma::one(iris_out),bb,iris_out,iris_rm,0,iris_flags);
 };
 for(reg_t i=0;i<iris_vl;++i){if(!insn.v_vm()&&!P.VU.mask_elt(0,i))continue;const unsigned lane=iris_ordered?0:unsigned(i%lanes);accum[lane]=add(accum[lane],read(insn.rs2(),i,iris_in),lane,true);}
 if(iris_ordered)accum[0]=add(accum[0],0,0,false);
 else for(unsigned offset=lanes/2;offset;offset/=2){const unsigned count=offset==1?1:lanes;for(unsigned lane=0;lane<count;++lane)accum[lane]=add(accum[lane],lane<offset?accum[lane+offset]:0,lane,false);}
 switch(iris_fma::width(iris_out)){case 16:P.VU.elt<uint16_t>(insn.rd(),0,true)=uint16_t(accum[0]);break;case 32:P.VU.elt<uint32_t>(insn.rd(),0,true)=uint32_t(accum[0]);break;default:P.VU.elt<uint64_t>(insn.rd(),0,true)=accum[0];}
 STATE.fflags->accumulate(iris_flags);
}
VECTOR_END;

}
