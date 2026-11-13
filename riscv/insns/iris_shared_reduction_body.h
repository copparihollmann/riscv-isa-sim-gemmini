const unsigned shared_rm=STATE.frm->read_defined(pc),shared_f6=insn.bits()>>26;
const bool shared_wide=shared_f6>=0x30;
if(P.VU.vstart->read_defined(pc)!=0)throw trap_illegal_instruction(pc);
VI_CHECK_REDUCTION(shared_wide);
require(P.VU.vsew==16||P.VU.vsew==32||P.VU.vsew==64);
if(P.VU.altfmt)throw std::runtime_error("IRIS_UNSUPPORTED_DATATYPE: hart2 has no alternate-format shared FPU");
require((P.VU.vsew==16&&p->extension_enabled(EXT_ZVFH))||(P.VU.vsew==32&&p->get_isa().get_zvf())||(P.VU.vsew==64&&p->get_isa().get_zvd()));
if(shared_rm>4)throw std::runtime_error("IRIS_UNSUPPORTED_ROUNDING_MODE shared reduction");
const iris_fma::Kind shared_in=P.VU.vsew==64?iris_fma::D:P.VU.vsew==32?iris_fma::S:iris_fma::H;
const iris_fma::Kind shared_out=shared_wide?(shared_in==iris_fma::S?iris_fma::D:iris_fma::S):shared_in;
auto read=[&](unsigned reg,reg_t i,iris_fma::Kind kind)->uint64_t{switch(iris_fma::width(kind)){case 16:return P.VU.elt<uint16_t>(reg,i);case 32:return P.VU.elt<uint32_t>(reg,i);default:return P.VU.elt<uint64_t>(reg,i);}};
if(P.VU.vl->read()){
 if(!STATE.sstatus->enabled(MSTATUS_FS))throw std::runtime_error("IRIS_RTL_ASSERT: shared reduction flags require mstatus.FS > 0");
 uint64_t accum=read(insn.rs1(),0,shared_out);uint8_t flags=0;
 // Both reduction opcodes are forced Elementwise by SharedScalarFPFMAFactory.
 for(reg_t i=0;i<P.VU.vl->read();++i){
  const auto result=iris_shared::add(accum,read(insn.rs2(),i,shared_in),shared_in,shared_out,shared_rm,flags);
  if(insn.v_vm()||P.VU.mask_elt(0,i))accum=result;
 }
 // ExecuteSequencer acc_copy always performs one final add of acc_init=+0.
 accum=iris_shared::add(accum,0,shared_out,shared_out,shared_rm,flags);
 switch(iris_fma::width(shared_out)){case 16:P.VU.elt<uint16_t>(insn.rd(),0,true)=uint16_t(accum);break;case 32:P.VU.elt<uint32_t>(insn.rd(),0,true)=uint32_t(accum);break;default:P.VU.elt<uint64_t>(insn.rd(),0,true)=accum;}
 STATE.fflags->accumulate(flags);
}
VECTOR_END;
