// Source-order reduction: fixed DLEN128 lane accumulators then halving folds.
if(P.get_id()>=2)throw std::runtime_error("IRIS_UNSUPPORTED_DATATYPE: hart 2 has no Mx FP8 reduction");
require_extension(EXT_ZVFOFP8MIN);
const unsigned iris_f6=insn.bits()>>26;
const bool iris_wide=iris_f6>=0x30,iris_ordered=(iris_f6&2)!=0;
VI_CHECK_REDUCTION(iris_wide);
const unsigned iris_rm=STATE.frm->read();
if(iris_rm>4)throw std::runtime_error("IRIS_UNSUPPORTED_ROUNDING_MODE FP8 reduction");
const reg_t iris_vl=P.VU.vl->read();
if(iris_vl){
 if(!STATE.sstatus->enabled(MSTATUS_FS))throw std::runtime_error("IRIS_RTL_ASSERT: FP8 reduction write requires mstatus.FS > 0");
 const unsigned lanes=iris_wide?8:16; // Audited compute DLEN128, never VLEN.
 uint16_t accum[16]={};
 accum[0]=iris_wide?P.VU.elt<uint16_t>(insn.rs1(),0):P.VU.elt<uint8_t>(insn.rs1(),0);
 uint8_t iris_flags=0;
 auto add=[&](uint16_t a,uint16_t b,unsigned lane,bool narrow_b){
  if(!iris_wide){const auto r=iris_fp8::fma(uint8_t(a),P.VU.altfmt?0x3c:0x38,uint8_t(b),P.VU.altfmt,iris_rm,0,lane&7);iris_flags|=r.flags;return r.bits;}
  IrisSoftfloatScope scope(iris_rm);
  if(narrow_b)b=uint16_t(iris_fp8_to_f32(uint8_t(b),P.VU.altfmt)>>16);
  auto quiet=[&](uint16_t raw){return uint16_t(!(lane&3)&&(raw&0x7f80)==0x7f80&&(raw&127)?0x7fc0:raw);};
  const uint16_t result=bf16_add(float16_t{quiet(a)},float16_t{quiet(b)}).v;
  iris_flags|=bool(softfloat_exceptionFlags&softfloat_flag_invalid);
  return result;
 };
 for(reg_t i=0;i<iris_vl;++i){
  if(!insn.v_vm()&&!P.VU.mask_elt(0,i))continue;
  const unsigned lane=iris_ordered?0:unsigned(i%lanes);
  accum[lane]=add(accum[lane],P.VU.elt<uint8_t>(insn.rs2(),i),lane,true);
 }
 if(iris_ordered){
  // acc_copy is an FADD with acc_init=+0, not a raw bit-copy.
  accum[0]=add(accum[0],0,0,false);
 }else{
  for(unsigned offset=lanes/2;offset;offset/=2){
   // Non-final folds issue every physical lane. Final fold writes only lane0.
   const unsigned count=offset==1?1:lanes;
   for(unsigned lane=0;lane<count;++lane)accum[lane]=add(accum[lane],lane<offset?accum[lane+offset]:0,lane,false);
  }
 }
 if(iris_wide)P.VU.elt<uint16_t>(insn.rd(),0,true)=accum[0];
 else P.VU.elt<uint8_t>(insn.rd(),0,true)=uint8_t(accum[0]);
 STATE.fflags->write(STATE.fflags->read()|iris_flags);
}
VECTOR_END;
