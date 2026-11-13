// Widening FP8 arithmetic writes BF16; source io.widen forces out_altfmt=true.
if(P.get_id()>=2)throw std::runtime_error("IRIS_UNSUPPORTED_DATATYPE: hart 2 has no Mx widening FP8");
require_vector(true);
require_extension(EXT_ZVFOFP8MIN);
const bool iris_vf=insn.funct3()==5;
if(iris_vf)require_fp;
const unsigned iris_rm=STATE.frm->read(),iris_f6=insn.bits()>>26;
if(iris_f6==0x34||iris_f6==0x36){VI_CHECK_DDS(!iris_vf);}else{VI_CHECK_DSS(!iris_vf);}
if(iris_rm>4)throw std::runtime_error("IRIS_UNSUPPORTED_ROUNDING_MODE widening FP8");
if(iris_f6==0x34||iris_f6==0x36)require_align(insn.rs2(),2*P.VU.vflmul);
uint8_t iris_flags=0;bool iris_wrote=false;
for(reg_t i=P.VU.vstart->read();i<P.VU.vl->read();++i){
 if(!insn.v_vm()&&!P.VU.mask_elt(0,i))continue;
 if(!STATE.sstatus->enabled(MSTATUS_FS))throw std::runtime_error("IRIS_RTL_ASSERT: widening FP8 write requires mstatus.FS > 0");
 IrisSoftfloatScope iris_scope(iris_rm);
 auto wide8=[&](uint8_t raw){return uint16_t(iris_fp8_to_f32(raw,P.VU.altfmt)>>16);};
 // BF16 destination physical pipes [D,BF16,S,BF16] quiet same-format input
 // sNaNs only on lane0 modulo4 (D); S shares exp8 and preserves signaling.
 auto bf16_input=[&](uint16_t raw){return uint16_t(!(i&3)&&(raw&0x7f80)==0x7f80&&(raw&127)?0x7fc0:raw);};
 const uint8_t vs1=iris_vf?uint8_t(READ_FREG(insn.rs1()).v[0]):P.VU.elt<uint8_t>(insn.rs1(),i);
 auto& dest=P.VU.elt<uint16_t>(insn.rd(),i,true);
 uint16_t a=(iris_f6==0x34||iris_f6==0x36)?bf16_input(P.VU.elt<uint16_t>(insn.rs2(),i)):wide8(P.VU.elt<uint8_t>(insn.rs2(),i));
 uint16_t b=wide8(vs1),c=bf16_input(dest);unsigned cmd=0;
 if(iris_f6==0x30||iris_f6==0x32||iris_f6==0x34||iris_f6==0x36){c=b;b=0x3f80;cmd=(iris_f6==0x32||iris_f6==0x36)?1:0;}
 else if(iris_f6==0x38)c=(a^b)&0x8000;
 else{const unsigned cmds[4]={0,3,1,2};cmd=cmds[iris_f6&3];}
 if(cmd&2)a^=0x8000;if(cmd&1)c^=0x8000;
 dest=bf16_mulAdd(float16_t{a},float16_t{b},float16_t{c}).v;
 // Source FPFMAPipe.scala371 wires invalidExc Bool to flags (bit0), discarding
 // other rounding exceptions. This unusual behavior is intentional here.
 iris_flags|=bool(softfloat_exceptionFlags&softfloat_flag_invalid);iris_wrote=true;
}
if(iris_wrote)STATE.fflags->write(STATE.fflags->read()|iris_flags);
VECTOR_END;
