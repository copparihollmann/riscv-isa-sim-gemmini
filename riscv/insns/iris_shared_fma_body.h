// PipelinedFaultCheck rejects non-memory instructions with nonzero vstart
// before ExecuteSequencer. Its tval is the instruction PC, not encoding bits.
if(P.VU.vstart->read_defined(pc)!=0)throw trap_illegal_instruction(pc);
require_vector(true);
const bool shared_vf=insn.funct3()==5;
if(shared_vf)require_fp;
const unsigned shared_rm=STATE.frm->read_defined(pc),shared_f6=insn.bits()>>26;
if(shared_rm>4)throw std::runtime_error("IRIS_UNSUPPORTED_ROUNDING_MODE shared FPU");
require(P.VU.vsew==16||P.VU.vsew==32||P.VU.vsew==64);
if(P.VU.altfmt)throw std::runtime_error("IRIS_UNSUPPORTED_DATATYPE: hart2 has no alternate-format shared FPU");
require((P.VU.vsew==16&&p->extension_enabled(EXT_ZVFH))||(P.VU.vsew==32&&p->get_isa().get_zvf())||(P.VU.vsew==64&&p->get_isa().get_zvd()));
const bool shared_wide=shared_f6>=0x30,shared_wide_input=shared_f6==0x34||shared_f6==0x36;
if(shared_wide){if(shared_wide_input){VI_CHECK_DDS(!shared_vf);}else{VI_CHECK_DSS(!shared_vf);}}else{VI_CHECK_SSS(!shared_vf);}
const iris_fma::Kind shared_in=P.VU.vsew==64?iris_fma::D:P.VU.vsew==32?iris_fma::S:iris_fma::H;
const iris_fma::Kind shared_out=shared_wide?(shared_in==iris_fma::S?iris_fma::D:iris_fma::S):shared_in;
auto read=[&](unsigned reg,reg_t i,iris_fma::Kind kind)->uint64_t{switch(iris_fma::width(kind)){case 16:return P.VU.elt<uint16_t>(reg,i);case 32:return P.VU.elt<uint32_t>(reg,i);default:return P.VU.elt<uint64_t>(reg,i);}};
uint8_t shared_flags=0;
if(P.VU.vl->read()){
 if(!STATE.sstatus->enabled(MSTATUS_FS))throw std::runtime_error("IRIS_RTL_ASSERT: shared FPU flags require mstatus.FS > 0");
 for(reg_t i=0;i<P.VU.vl->read();++i){
  const uint64_t a=read(insn.rs2(),i,shared_wide_input?shared_out:shared_in);
  const uint64_t b=shared_vf?READ_FREG(insn.rs1()).v[0]:read(insn.rs1(),i,shared_in);
  const bool uses_c=(shared_f6>=0x28&&shared_f6<=0x2f)||(shared_f6>=0x3c&&shared_f6<=0x3f);
  const uint64_t c=uses_c?read(insn.rd(),i,shared_out):0;
  const auto value=iris_shared::operation(shared_f6,shared_in,a,b,c,shared_rm,shared_flags);
  // Hardware issues the FPU request for masked elements as well. Only the
  // write mask is suppressed; scalar FPU exception flags still reach the CSR.
  if(insn.v_vm()||P.VU.mask_elt(0,i))switch(iris_fma::width(shared_out)){
   case 16:P.VU.elt<uint16_t>(insn.rd(),i,true)=uint16_t(value);break;
   case 32:P.VU.elt<uint32_t>(insn.rd(),i,true)=uint32_t(value);break;
   default:P.VU.elt<uint64_t>(insn.rd(),i,true)=value;break;
  }
 }
 STATE.fflags->accumulate(shared_flags);
} else if(shared_vf) {
 // Rocket still executes its scalar-FPR extraction on VF with VL=0. The
 // elaborated decoder has wflags=0 there, but FPToInt reports valid zero flags.
 STATE.fflags->accumulate(0);
}
VECTOR_END;
