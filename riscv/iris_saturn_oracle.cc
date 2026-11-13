#include "iris_saturn_oracle.h"
#include "processor.h"
#include "simif.h"
#include <cstring>
#include <map>
#include <sstream>
namespace {
struct PrivateMachine final:simif_t {
 const cfg_t&cfg;std::map<size_t,processor_t*>harts;
 explicit PrivateMachine(const cfg_t&c):cfg(c){debug_mmu=nullptr;}
 char*addr_to_mem(reg_t)override{throw std::runtime_error("IRIS_SATURN_PRIVATE_ORACLE_MEMORY_FORBIDDEN");}
 bool mmio_load(reg_t,size_t,uint8_t*)override{throw std::runtime_error("IRIS_SATURN_PRIVATE_ORACLE_MMIO_FORBIDDEN");}
 bool mmio_store(reg_t,size_t,const uint8_t*)override{throw std::runtime_error("IRIS_SATURN_PRIVATE_ORACLE_MMIO_FORBIDDEN");}
 void proc_reset(unsigned)override{}
 const cfg_t&get_cfg()const override{return cfg;}
 const std::map<size_t,processor_t*>&get_harts()const override{return harts;}
 const char*get_symbol(uint64_t)override{return nullptr;}
};
using Image=iris_saturn_oracle::Image;
Image capture(const vectorUnit_t&v){
 Image i;const auto bytes=v.vlenb*32;i.vrf.resize(bytes);std::memcpy(i.vrf.data(),v.reg_file,bytes);i.mrf.assign(v.mt.begin(),v.mt.end());i.vrf_known=v.iris_vrf_definedness;i.mrf_known=v.iris_tile_definedness;i.initialized=v.iris_initialized;
 i.vl=v.vl->read();i.vlmax=v.vlmax;i.vtype=v.vtype->read();i.mtype=v.mtype->read();i.vstart=v.vstart->read();i.vxrm=v.vxrm->read();i.vstart_known=v.vstart->iris_known_bits();i.vxrm_known=v.vxrm->iris_known_bits();i.vma=v.vma;i.vta=v.vta;i.vsew=v.vsew;i.altfmt=v.altfmt;i.widen=v.widen;i.tm=v.tm;i.tk=v.tk;i.lmul=v.vflmul;i.vill=v.vill;return i;
}
void config(vectorUnit_t&v,const Image&i){v.vl->write_raw(i.vl);v.vlmax=i.vlmax;v.vtype->write_raw(i.vtype);v.mtype->write_raw(i.mtype);v.vstart->write_raw(i.vstart);v.vxrm->write_raw(i.vxrm);v.vstart->iris_set_known(i.vstart_known);v.vxrm->iris_set_known(i.vxrm_known);v.vma=i.vma;v.vta=i.vta;v.vsew=i.vsew;v.altfmt=i.altfmt;v.widen=i.widen;v.tm=i.tm;v.tk=i.tk;v.vflmul=i.lmul;v.vill=i.vill;}
void restore(vectorUnit_t&v,const Image&i){if(i.vrf.size()!=v.vlenb*32||i.mrf.size()!=v.mt.size())throw std::runtime_error("IRIS_SATURN_PRIVATE_IMAGE_SHAPE");std::memcpy(v.reg_file,i.vrf.data(),i.vrf.size());std::copy(i.mrf.begin(),i.mrf.end(),v.mt.begin());v.iris_vrf_definedness=i.vrf_known;v.iris_tile_definedness=i.mrf_known;v.iris_initialized=i.initialized;config(v,i);}
}
struct iris_saturn_oracle::Impl {
 cfg_t cfg;PrivateMachine machine;std::ostringstream output;std::unique_ptr<processor_t>cpu;
 explicit Impl(processor_t&real):cfg(real.get_cfg()),machine(cfg){
  const auto isa=real.get_isa().get_isa_string();cpu=std::make_unique<processor_t>(isa.c_str(),real.get_privilege_string(),&cfg,&machine,real.get_id(),false,nullptr,output);machine.harts.emplace(real.get_id(),cpu.get());
  if(!real.VU.iris_mode||!cpu->VU.iris_mode||real.VU.VLEN!=256)throw std::runtime_error("IRIS_SATURN_PRIVATE_ORACLE_REQUIRES_IRIS_VLEN256");restore(cpu->VU,capture(real.VU));
 }
};
iris_saturn_oracle::iris_saturn_oracle(processor_t&real):impl_(std::make_unique<Impl>(real)){}
iris_saturn_oracle::~iris_saturn_oracle()=default;
void iris_saturn_oracle::rollback(const Image&image){restore(impl_->cpu->VU,image);}
iris_saturn_oracle::Intent iris_saturn_oracle::preview(processor_t&real,uint64_t node,uint64_t pc,uint32_t raw,iris_definedness::Value<uint64_t>rs1,iris_definedness::Value<uint64_t>rs2){
 auto&oracle=*impl_->cpu;const auto before=capture(oracle.VU);Intent intent;intent.node=node;intent.pc=pc;intent.instruction=raw;intent.before=before;
 // Only scalar/config transports are synchronized here. The private logical
 // VRF/MRF remains ahead of physical commits for dependent unit commands.
 config(oracle.VU,capture(real.VU));auto*state=oracle.get_state();state->prv=real.get_state()->prv;state->v=real.get_state()->v;state->pc=pc;
 state->mstatus->write(real.get_state()->mstatus->read());
 for(unsigned r=0;r<32;++r)oracle.iris_write_xpr_transport(r,real.get_state()->XPR.read_transport(r));
 oracle.iris_write_xpr_transport((raw>>15)&31,rs1);oracle.iris_write_xpr_transport((raw>>20)&31,rs2);
 try {const insn_t insn(raw);const auto next=oracle.decode_for_model(insn)(&oracle,insn,pc);if(next!=pc+4)throw std::runtime_error("IRIS_SATURN_PRIVATE_ORACLE_NONLOCAL_PC");intent.after=capture(oracle.VU);if(((raw>>12)&7)==2&&((raw>>26)==0x10))intent.scalar=state->XPR.read_transport((raw>>7)&31);}
 catch(...){restore(oracle.VU,before);throw;}
 return intent;
}
