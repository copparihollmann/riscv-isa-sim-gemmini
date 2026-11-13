if(P.get_id()==2){
#include "iris_shared_fma_body.h"
}else{
// Compute-hart source SegmentedFMAPipe: physical input NaNs and flags bit0.
require_vector(true);
const bool iris_vf=insn.funct3()==5;
if(iris_vf)require_fp;
const unsigned iris_f6=insn.bits()>>26,iris_rm=STATE.frm->read();
if(iris_rm>4)throw std::runtime_error("IRIS_UNSUPPORTED_ROUNDING_MODE compute IEEE/BF16 FMA");
const bool iris_wide=iris_f6>=0x30,iris_wide_input=iris_f6==0x34||iris_f6==0x36;
const iris_fma::Kind iris_in=P.VU.vsew==64?iris_fma::D:P.VU.vsew==32?iris_fma::S:P.VU.altfmt?iris_fma::BF:iris_fma::H;
const iris_fma::Kind iris_out=iris_wide?(iris_in==iris_fma::S?iris_fma::D:iris_fma::S):iris_in;
require(P.VU.vsew==16||P.VU.vsew==32||P.VU.vsew==64);
if(P.VU.altfmt&&P.VU.vsew>=32)throw std::runtime_error("IRIS_UNSUPPORTED_DATATYPE: no segmented FMA output selection for wide alternate format");
require((P.VU.vsew==16&&p->extension_enabled(P.VU.altfmt?EXT_ZVFBFA:EXT_ZVFH))||(P.VU.vsew==32&&p->get_isa().get_zvf())||(P.VU.vsew==64&&p->get_isa().get_zvd()));
if(iris_wide){if(iris_wide_input){VI_CHECK_DDS(!iris_vf);}else{VI_CHECK_DSS(!iris_vf);}}else{VI_CHECK_SSS(!iris_vf);}
auto read=[&](unsigned reg,reg_t i,iris_fma::Kind kind)->uint64_t{switch(iris_fma::width(kind)){case 16:return P.VU.elt<uint16_t>(reg,i);case 32:return P.VU.elt<uint32_t>(reg,i);default:return P.VU.elt<uint64_t>(reg,i);}};
auto write=[&](reg_t i,uint64_t value){switch(iris_fma::width(iris_out)){case 16:P.VU.elt<uint16_t>(insn.rd(),i,true)=uint16_t(value);break;case 32:P.VU.elt<uint32_t>(insn.rd(),i,true)=uint32_t(value);break;default:P.VU.elt<uint64_t>(insn.rd(),i,true)=value;}};
uint8_t iris_flags=0;bool iris_wrote=false;
for(reg_t i=P.VU.vstart->read();i<P.VU.vl->read();++i){
 if(!insn.v_vm()&&!P.VU.mask_elt(0,i))continue;
 if(!STATE.sstatus->enabled(MSTATUS_FS))throw std::runtime_error("IRIS_RTL_ASSERT: compute FPFMA write requires mstatus.FS > 0");
 uint64_t a,b,c;
 // Conversion flags are not connected to vector fflags. All conversions are
 // exact except NaN quieting; clear them before fused() measures FMA invalid.
 {IrisSoftfloatScope scope(iris_rm);
  const uint64_t source1=iris_vf?READ_FREG(insn.rs1()).v[0]:read(insn.rs1(),i,iris_in);
  a=iris_fma::input(read(insn.rs2(),i,iris_wide_input?iris_out:iris_in),iris_wide_input?iris_out:iris_in,iris_out,i);
  b=iris_fma::input(source1,iris_in,iris_out,i);
  c=iris_fma::input(read(insn.rd(),i,iris_out),iris_out,iris_out,i);
 }
 unsigned cmd=0;
 if(iris_f6==0||iris_f6==2||iris_f6==0x27||iris_f6==0x30||iris_f6==0x32||iris_wide_input){c=b;b=iris_fma::one(iris_out);cmd=(iris_f6==2||iris_f6==0x32||iris_f6==0x36)?1:iris_f6==0x27?2:0;}
 else if(iris_f6==0x24||iris_f6==0x38)c=(a^b)&iris_fma::signbit(iris_out);
 else{const unsigned cmds[4]={0,3,1,2};cmd=cmds[iris_f6&3];if(!iris_wide&&iris_f6<0x2c){const uint64_t t=a;a=c;c=t;}}
 write(i,iris_fma::fused(a,b,c,iris_out,iris_rm,cmd,iris_flags));iris_wrote=true;
}
if(iris_wrote)STATE.fflags->write(STATE.fflags->read()|iris_flags);
VECTOR_END;

}
