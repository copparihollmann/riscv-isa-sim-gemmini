// FPCompPipe inspects H chunks for SEW16/32 and S chunks for SEW64,
// independent of mask/tail and even on sign injection.
require_vector_vs;
require(!P.VU.vill);
if(insn.funct3()==5)require_fp;
if(P.VU.vstart->read_defined(pc)!=0)throw trap_illegal_instruction(pc);
require_vector(true);
if(P.VU.VLEN!=256||P.VU.ELEN!=64)throw std::runtime_error("IRIS_UNSUPPORTED_VECTOR_CONFIG: FPComp requires audited VLEN256 ELEN64");
const unsigned cmp_width=P.VU.vsew,cmp_f6=insn.bits()>>26;
const bool cmp_vf=insn.funct3()==5,cmp_reduction=cmp_f6==5||cmp_f6==7,cmp_mask=cmp_f6>=0x18;
if(cmp_vf)require_fp;
require(cmp_width==16||cmp_width==32||cmp_width==64);
// FPComp does not read altfmt: each accepted width always uses H/S/D.
require((cmp_width==16&&p->extension_enabled(EXT_ZVFH))||(cmp_width==32&&p->get_isa().get_zvf())||(cmp_width==64&&p->get_isa().get_zvd()));
if(cmp_reduction){VI_CHECK_REDUCTION(false);}else if(cmp_mask){VI_CHECK_MSS(!cmp_vf);}else{VI_CHECK_SSS(!cmp_vf);}
const reg_t cmp_vl=P.VU.vl->read();
const unsigned cmp_lanes=(P.get_id()==2?256:128)/cmp_width;
auto read=[&](unsigned reg,reg_t i)->uint64_t{if(cmp_width==16)return P.VU.elt<uint16_t>(reg,i);if(cmp_width==32)return P.VU.elt<uint32_t>(reg,i);return P.VU.elt<uint64_t>(reg,i);};
auto write=[&](reg_t i,uint64_t value){if(cmp_width==16)P.VU.elt<uint16_t>(insn.rd(),i,true)=value;else if(cmp_width==32)P.VU.elt<uint32_t>(insn.rd(),i,true)=value;else P.VU.elt<uint64_t>(insn.rd(),i,true)=value;};
if(cmp_vl){
 if(!STATE.sstatus->enabled(MSTATUS_FS))throw std::runtime_error("IRIS_RTL_ASSERT: FPComp flags require mstatus.FS > 0");
 const unsigned count=((cmp_vl+cmp_lanes-1)/cmp_lanes)*cmp_lanes;
 uint64_t src2[128]={},src1[128]={};bool active[128]={};
 for(unsigned i=0;i<count;++i){src2[i]=read(insn.rs2(),i);src1[i]=cmp_vf?READ_FREG(insn.rs1()).v[0]&iris_cmp::mask(cmp_width):cmp_reduction?0:read(insn.rs1(),i);active[i]=i<cmp_vl&&(insn.v_vm()||P.VU.mask_elt(0,i));}
 uint8_t flags=0;
 if(cmp_reduction){
  uint64_t acc[16]={},b[16]={},a[16]={};
  const uint64_t initial=iris_cmp::infinity(cmp_width)|(cmp_f6==7?iris_cmp::sign(cmp_width):0);
  for(unsigned lane=0;lane<cmp_lanes;++lane)acc[lane]=initial;
  acc[0]=read(insn.rs1(),0);
  for(unsigned base=0;base<count;base+=cmp_lanes){
   flags|=iris_cmp::flags(src2+base,acc,cmp_lanes,cmp_width);
   for(unsigned lane=0;lane<cmp_lanes;++lane)if(active[base+lane])acc[lane]=iris_cmp::element(src2[base+lane],acc[lane],cmp_width,cmp_f6);
  }
  for(unsigned offset=cmp_lanes/2;offset;offset/=2){
   for(unsigned lane=0;lane<cmp_lanes;++lane){a[lane]=acc[lane];b[lane]=lane<offset?acc[lane+offset]:0;}
   flags|=iris_cmp::flags(a,b,cmp_lanes,cmp_width);
   for(unsigned lane=0;lane<(offset==1?1:cmp_lanes);++lane)acc[lane]=iris_cmp::element(a[lane],b[lane],cmp_width,cmp_f6);
  }
  write(0,acc[0]);
 }else{
  for(unsigned base=0;base<count;base+=cmp_lanes){
   flags|=iris_cmp::flags(src2+base,src1+base,cmp_lanes,cmp_width);
   for(unsigned lane=0;lane<cmp_lanes;++lane)if(active[base+lane]){
    const auto value=iris_cmp::element(src2[base+lane],src1[base+lane],cmp_width,cmp_f6);
    if(cmp_mask)P.VU.set_mask_elt(insn.rd(),base+lane,value);else write(base+lane,value);
   }
  }
 }
 STATE.fflags->accumulate(flags);
}else if(cmp_vf)STATE.fflags->accumulate(0);
VECTOR_END;
