#include "iris_saturn_oracle.h"
#include "processor.h"
#include "simif.h"
#include <cstring>
#include <iostream>
#include <map>
#include <sstream>
struct Host final:simif_t {
 cfg_t cfg;std::map<size_t,processor_t*>harts;
 Host(){cfg.isa="rv64gcv_zfh_zvfh_zba_zbb_zbs_zvbb_zvl256b_zvfofp8min_zvfbfmin_zvfbfa_zvt32t_zvti8i32mm_zvtofp8fmm";cfg.priv="MSU";cfg.iris_vme=true;cfg.hartids={0,1,2};debug_mmu=nullptr;}
 char*addr_to_mem(reg_t)override{throw std::runtime_error("unexpected real memory access");}bool mmio_load(reg_t,size_t,uint8_t*)override{throw std::runtime_error("unexpected real MMIO access");}bool mmio_store(reg_t,size_t,const uint8_t*)override{throw std::runtime_error("unexpected real MMIO access");}void proc_reset(unsigned)override{}const cfg_t&get_cfg()const override{return cfg;}const std::map<size_t,processor_t*>&get_harts()const override{return harts;}const char*get_symbol(uint64_t)override{return nullptr;}
};
int main(){try{
 Host host;std::ostringstream output;processor_t real(host.cfg.isa,host.cfg.priv,&host.cfg,&host,0,false,nullptr,output);host.harts[0]=&real;real.get_state()->mstatus->write(MSTATUS_FS|MSTATUS_VS);real.VU.vstart->write_raw(0);real.VU.vxrm->write_raw(0);real.VU.set_vl(1,1,1,0xc0);
 iris_definedness::Value<uint64_t> zero;zero.known.fill(255);for(unsigned r=0;r<32;++r)real.iris_write_xpr_transport(r,zero);
 iris_saturn_oracle oracle(real);unsigned checks=0;uint64_t node=1;
 auto need=[&](bool value){++checks;if(!value)throw std::runtime_error("private oracle invariant");};
 auto preview=[&](uint32_t raw){const auto mstatus=real.get_state()->mstatus->read();const auto before_vstart=real.VU.vstart->read();std::vector<uint8_t>vrf(real.VU.vlenb*32);std::memcpy(vrf.data(),real.VU.reg_file,vrf.size());auto tile=real.VU.mt;auto known=real.VU.iris_vrf_definedness.read(0,vrf.size());auto tk=real.VU.iris_tile_definedness.read(0,tile.size());const auto retired=real.get_csr(CSR_MINSTRET);auto row=oracle.preview(real,node++,0x80001000+4*node,raw,zero,zero);need(real.get_state()->mstatus->read()==mstatus&&real.VU.vstart->read()==before_vstart);need(std::memcmp(real.VU.reg_file,vrf.data(),vrf.size())==0&&real.VU.mt==tile);need(real.VU.iris_vrf_definedness.read(0,vrf.size())==known&&real.VU.iris_tile_definedness.read(0,tile.size())==tk);need(real.get_csr(CSR_MINSTRET)==retired);return row;};
 auto init=preview(0x5e03b257);need(init.after.vrf[4*32]==7&&init.after.vrf_known.byte(4*32)==255);auto add=preview(0x0240b257);need(add.after.vrf[4*32]==8);auto scalar=preview(0x424027d7);need(scalar.scalar&&scalar.scalar->value==8);need(real.get_state()->XPR[15]==0);
 real.VU.msetmtype(3,0);real.VU.msettn(32);real.VU.msettm(32);real.VU.msettk(1);
 auto clear=preview(0x43e06057);need(clear.after.mrf_known.byte(0)==255);preview(0x5e013457);preview(0x5e01b857);auto mm=preview(0xf2880077);for(unsigned i=0;i<32*32;++i){uint32_t value;std::memcpy(&value,mm.after.mrf.data()+i*4,4);need(value==6&&mm.after.mrf_known.byte(i*4)==255);}
 real.VU.msetmtype(1,16);real.VU.msettn(32);auto row=preview(0x43f46c57);for(unsigned i=0;i<32;++i){uint32_t value;std::memcpy(&value,row.after.vrf.data()+24*32+i*4,4);need(value==6);}auto result=preview(0x438026d7);need(result.scalar&&result.scalar->value==6);
 oracle.rollback(init.before);bool rejected=false;try{preview(0x0240b257);}catch(const std::runtime_error&e){rejected=std::string(e.what()).find("IRIS_UNDEFINED_STATE")!=std::string::npos;}need(rejected);
 std::cout<<"{\"status\":\"passed_isolated_numeric_intents_and_real_state_unchanged\",\"checks\":"<<checks<<",\"commands\":9,\"K\":1,\"uninitialized_rollback_refusals\":1,\"live_CPU_hook_executed\":false}\n";
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}}
