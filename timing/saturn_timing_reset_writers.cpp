#include "VSaturnCompute.h"
#include "VSaturnCompute___024root.h"
#include "VSaturnRocket.h"
#include "VSaturnRocket___024root.h"
#include "verilated.h"
#include <array>
#include <cstdint>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
struct Sweep {bool active;unsigned cursor;};
static void require(bool value,const char*why){if(!value)throw std::runtime_error(why);}
static void inputs(VSaturnCompute&m){
m.clock=0;
m.reset=0;
m.auto_atl_out_a_ready=0;
m.auto_atl_out_d_valid=0;
m.auto_atl_out_d_bits_opcode=0;
m.auto_atl_out_d_bits_param=0;
m.auto_atl_out_d_bits_size=0;
m.auto_atl_out_d_bits_source=0;
m.auto_atl_out_d_bits_sink=0;
m.auto_atl_out_d_bits_denied=0;
m.auto_atl_out_d_bits_data[0]=0;
m.auto_atl_out_d_bits_data[1]=0;
m.auto_atl_out_d_bits_data[2]=0;
m.auto_atl_out_d_bits_data[3]=0;
m.auto_atl_out_d_bits_data[4]=0;
m.auto_atl_out_d_bits_data[5]=0;
m.auto_atl_out_d_bits_data[6]=0;
m.auto_atl_out_d_bits_data[7]=0;
m.auto_atl_out_d_bits_corrupt=0;
m.io_status_prv=0;
m.io_ex_valid=0;
m.io_ex_uop_inst=0;
m.io_ex_uop_pc=0;
m.io_ex_uop_rs1_data=0;
m.io_ex_uop_rs2_data=0;
m.io_ex_vconfig_vl=0;
m.io_ex_vconfig_vtype_vill=0;
m.io_ex_vconfig_vtype_tm=0;
m.io_ex_vconfig_vtype_tk=0;
m.io_ex_vconfig_vtype_vtwiden=0;
m.io_ex_vconfig_vtype_altfmt=0;
m.io_ex_vconfig_vtype_vma=0;
m.io_ex_vconfig_vtype_vta=0;
m.io_ex_vconfig_vtype_vsew=0;
m.io_ex_vconfig_vtype_vlmul_sign=0;
m.io_ex_vconfig_vtype_vlmul_mag=0;
m.io_ex_vstart=0;
m.io_ex_fire=0;
m.io_mem_kill=0;
m.io_mem_tlb_req_ready=0;
m.io_mem_tlb_resp_miss=0;
m.io_mem_tlb_resp_paddr=0;
m.io_mem_tlb_resp_pf_ld=0;
m.io_mem_tlb_resp_pf_st=0;
m.io_mem_tlb_resp_ae_ld=0;
m.io_mem_tlb_resp_ae_st=0;
m.io_mem_tlb_resp_ma_ld=0;
m.io_mem_tlb_resp_ma_st=0;
m.io_mem_frs1=0;
m.io_com_store_pending=0;
m.io_com_vxrm=0;
m.io_com_frm=0;
m.io_com_scalar_check_bits_addr=0;
m.io_com_scalar_check_bits_store=0;
m.io_resp_ready=0;
m.io_status_prv=3;m.io_resp_ready=1;
}
static void command(VSaturnCompute&m,bool enable){m.io_ex_valid=enable;m.io_ex_fire=enable;m.io_ex_uop_inst=0x428022d7;m.io_ex_uop_pc=0x80001000;m.io_ex_vconfig_vl=1;m.io_ex_vconfig_vtype_vsew=3;}
static Sweep sweep(VSaturnCompute&m){return {bool(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__resetting),unsigned(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__reset_ctr)} ;}
static std::uint32_t ram(VSaturnCompute&m,unsigned eg,unsigned word){switch(eg%4){
case 0:return m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__vrf_ext__DOT__Memory[eg/4][word];
case 1:return m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__vrf_ext__DOT__Memory[eg/4][word];
case 2:return m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__vrf_ext__DOT__Memory[eg/4][word];
case 3:return m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__vrf_ext__DOT__Memory[eg/4][word];
}throw std::logic_error("Invalid bank");}
static unsigned writes(VSaturnCompute&m,unsigned eg){unsigned seen=0;
if(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_valid){require(eg%4==0,"Scrub selected wrong bank");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_eg==eg/4,"Scrub wrote wrong bank address");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[0]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[0]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[1]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[1]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[2]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[2]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[3]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[3]==0xffffffffu,"Scrub mask not full width");++seen;}
if(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_valid){require(eg%4==1,"Scrub selected wrong bank");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_eg==eg/4,"Scrub wrote wrong bank address");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_data[0]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_mask[0]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_data[1]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_mask[1]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_data[2]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_mask[2]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_data[3]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_mask[3]==0xffffffffu,"Scrub mask not full width");++seen;}
if(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_valid){require(eg%4==2,"Scrub selected wrong bank");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_eg==eg/4,"Scrub wrote wrong bank address");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_data[0]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_mask[0]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_data[1]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_mask[1]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_data[2]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_mask[2]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_data[3]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_mask[3]==0xffffffffu,"Scrub mask not full width");++seen;}
if(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_valid){require(eg%4==3,"Scrub selected wrong bank");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_eg==eg/4,"Scrub wrote wrong bank address");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_data[0]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_mask[0]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_data[1]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_mask[1]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_data[2]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_mask[2]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_data[3]==0,"Scrub data is not zero");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_mask[3]==0xffffffffu,"Scrub mask not full width");++seen;}
return seen;}
static bool response(VSaturnCompute&m){return m.io_resp_valid;}
static void check_response(VSaturnCompute&m,bool corrupt){require(m.io_resp_bits_rd==5&&!m.io_resp_bits_fp,"Wrong scalar readback destination");require((m.io_resp_bits_data^(corrupt?1:0))==0,"Reset-scrub architectural readback is nonzero");}
static std::uint64_t tile_observation(VSaturnCompute&m){std::uint64_t h=1469598103934665603ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_0)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_1)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_2)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_3)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_4)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_5)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_6)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_7)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_8)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_9)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_10)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_11)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_12)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_13)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_14)*1099511628211ULL;h=(h^m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_15)*1099511628211ULL;return h;}
static void inputs(VSaturnRocket&m){
m.clock=0;
m.reset=0;
m.auto_atl_out_a_ready=0;
m.auto_atl_out_d_valid=0;
m.auto_atl_out_d_bits_opcode=0;
m.auto_atl_out_d_bits_param=0;
m.auto_atl_out_d_bits_size=0;
m.auto_atl_out_d_bits_source=0;
m.auto_atl_out_d_bits_sink=0;
m.auto_atl_out_d_bits_denied=0;
m.auto_atl_out_d_bits_data=0;
m.auto_atl_out_d_bits_corrupt=0;
m.io_core_status_dv=0;
m.io_core_status_prv=0;
m.io_core_ex_valid=0;
m.io_core_ex_inst=0;
m.io_core_ex_pc=0;
m.io_core_ex_vconfig_vl=0;
m.io_core_ex_vconfig_vtype_vill=0;
m.io_core_ex_vconfig_vtype_vtwiden=0;
m.io_core_ex_vconfig_vtype_altfmt=0;
m.io_core_ex_vconfig_vtype_vma=0;
m.io_core_ex_vconfig_vtype_vta=0;
m.io_core_ex_vconfig_vtype_vsew=0;
m.io_core_ex_vconfig_vtype_vlmul_sign=0;
m.io_core_ex_vconfig_vtype_vlmul_mag=0;
m.io_core_ex_vstart=0;
m.io_core_ex_rs1=0;
m.io_core_ex_rs2=0;
m.io_core_killm=0;
m.io_core_mem_frs1=0;
m.io_core_wb_store_pending=0;
m.io_core_wb_vxrm=0;
m.io_core_wb_frm=0;
m.io_core_resp_ready=0;
m.io_tlb_s1_resp_miss=0;
m.io_tlb_s1_resp_paddr=0;
m.io_tlb_s1_resp_pf_ld=0;
m.io_tlb_s1_resp_pf_st=0;
m.io_tlb_s1_resp_ae_ld=0;
m.io_tlb_s1_resp_ae_st=0;
m.io_tlb_s1_resp_ma_ld=0;
m.io_tlb_s1_resp_ma_st=0;
m.io_tlb_s1_resp_cmd=0;
m.io_dmem_req_ready=0;
m.io_dmem_s2_nack=0;
m.io_dmem_resp_valid=0;
m.io_dmem_resp_bits_tag=0;
m.io_dmem_resp_bits_data_raw[0]=0;
m.io_dmem_resp_bits_data_raw[1]=0;
m.io_dmem_resp_bits_data_raw[2]=0;
m.io_dmem_resp_bits_data_raw[3]=0;
m.io_dmem_resp_bits_data_raw[4]=0;
m.io_dmem_resp_bits_data_raw[5]=0;
m.io_dmem_resp_bits_data_raw[6]=0;
m.io_dmem_resp_bits_data_raw[7]=0;
m.io_dmem_s2_xcpt_ma_ld=0;
m.io_dmem_s2_xcpt_ma_st=0;
m.io_dmem_s2_xcpt_pf_ld=0;
m.io_dmem_s2_xcpt_pf_st=0;
m.io_dmem_s2_xcpt_ae_ld=0;
m.io_dmem_s2_xcpt_ae_st=0;
m.io_fp_req_ready=0;
m.io_fp_resp_valid=0;
m.io_fp_resp_bits_data[0]=0;
m.io_fp_resp_bits_data[1]=0;
m.io_fp_resp_bits_data[2]=0;
m.io_core_status_prv=3;m.io_core_resp_ready=1;
}
static void command(VSaturnRocket&m,bool enable){m.io_core_ex_valid=enable;m.io_core_ex_inst=0x428022d7;m.io_core_ex_pc=0x80001000;m.io_core_ex_vconfig_vl=1;m.io_core_ex_vconfig_vtype_vsew=3;}
static Sweep sweep(VSaturnRocket&m){return {bool(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__resetting),unsigned(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__reset_ctr)} ;}
static std::uint32_t ram(VSaturnRocket&m,unsigned eg,unsigned word){switch(eg%1){
case 0:return m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__vrf_ext__DOT__Memory[eg/1][word];
}throw std::logic_error("Invalid bank");}
static unsigned writes(VSaturnRocket&m,unsigned eg){unsigned seen=0;
if(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_valid){require(eg%1==0,"Scrub selected wrong bank");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_eg==eg/1,"Scrub wrote wrong bank address");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[0]==0,"Scrub data is not zero");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[0]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[1]==0,"Scrub data is not zero");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[1]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[2]==0,"Scrub data is not zero");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[2]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[3]==0,"Scrub data is not zero");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[3]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[4]==0,"Scrub data is not zero");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[4]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[5]==0,"Scrub data is not zero");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[5]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[6]==0,"Scrub data is not zero");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[6]==0xffffffffu,"Scrub mask not full width");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[7]==0,"Scrub data is not zero");require(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[7]==0xffffffffu,"Scrub mask not full width");++seen;}
return seen;}
static bool response(VSaturnRocket&m){return m.io_core_resp_valid;}
static void check_response(VSaturnRocket&m,bool corrupt){require(m.io_core_resp_bits_rd==5&&!m.io_core_resp_bits_fp,"Wrong scalar readback destination");require((m.io_core_resp_bits_data^(corrupt?1:0))==0,"Reset-scrub architectural readback is nonzero");}
static std::uint64_t tile_observation(VSaturnRocket&m){std::uint64_t h=1469598103934665603ULL;return h;}

#include <deque>
#include <set>
#include <vector>
struct BankWrite{unsigned eg;std::vector<std::uint32_t> data,mask;};
static std::vector<BankWrite> physical_writes(VSaturnCompute&m){std::vector<BankWrite> v;
if(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_valid){BankWrite w;w.eg=unsigned(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_eg)*4+0;w.data.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[0]);w.mask.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[0]);w.data.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[1]);w.mask.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[1]);w.data.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[2]);w.mask.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[2]);w.data.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[3]);w.mask.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[3]);v.push_back(w);}
if(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_valid){BankWrite w;w.eg=unsigned(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_eg)*4+1;w.data.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_data[0]);w.mask.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_mask[0]);w.data.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_data[1]);w.mask.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_mask[1]);w.data.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_data[2]);w.mask.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_mask[2]);w.data.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_data[3]);w.mask.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_1__DOT__write_bits_mask[3]);v.push_back(w);}
if(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_valid){BankWrite w;w.eg=unsigned(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_eg)*4+2;w.data.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_data[0]);w.mask.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_mask[0]);w.data.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_data[1]);w.mask.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_mask[1]);w.data.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_data[2]);w.mask.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_mask[2]);w.data.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_data[3]);w.mask.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_2__DOT__write_bits_mask[3]);v.push_back(w);}
if(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_valid){BankWrite w;w.eg=unsigned(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_eg)*4+3;w.data.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_data[0]);w.mask.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_mask[0]);w.data.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_data[1]);w.mask.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_mask[1]);w.data.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_data[2]);w.mask.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_mask[2]);w.data.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_data[3]);w.mask.push_back(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_3__DOT__write_bits_mask[3]);v.push_back(w);}
return v;}
static void send(VSaturnCompute&m,unsigned kind,bool valid){command(m,valid);m.io_ex_vconfig_vtype_vlmul_mag=kind==3?0:3;if(kind<3){m.io_ex_vconfig_vl=256;m.io_ex_vconfig_vtype_vsew=0;m.io_ex_uop_inst=kind==0?0x5e03b457u:kind==1?0x5e02c457u:0x02050407u;m.io_ex_uop_rs1_data=kind==2?0x80010000ULL:7ULL;}else m.io_ex_uop_rs1_data=0;m.io_mem_tlb_req_ready=1;m.io_mem_tlb_resp_paddr=0x80010000ULL;}
static bool exready(VSaturnCompute&m){return m.io_ex_ready;}
static std::uint64_t scalar(VSaturnCompute&m){return m.io_resp_bits_data;}
static void data(VSaturnCompute&m,bool valid,unsigned tag,unsigned size){m.auto_atl_out_a_ready=1;m.auto_atl_out_d_valid=valid;m.auto_atl_out_d_bits_opcode=1;m.auto_atl_out_d_bits_source=tag;m.auto_atl_out_d_bits_size=size;for(unsigned n=0;n<8;n++)m.auto_atl_out_d_bits_data[n]=0x07070707u;}
static std::vector<BankWrite> physical_writes(VSaturnRocket&m){std::vector<BankWrite> v;
if(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_valid){BankWrite w;w.eg=unsigned(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_eg)*1+0;w.data.push_back(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[0]);w.mask.push_back(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[0]);w.data.push_back(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[1]);w.mask.push_back(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[1]);w.data.push_back(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[2]);w.mask.push_back(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[2]);w.data.push_back(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[3]);w.mask.push_back(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[3]);w.data.push_back(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[4]);w.mask.push_back(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[4]);w.data.push_back(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[5]);w.mask.push_back(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[5]);w.data.push_back(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[6]);w.mask.push_back(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[6]);w.data.push_back(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_data[7]);w.mask.push_back(m.rootp->SaturnRocketUnit__DOT__vu__DOT__vrf__DOT__vrf__DOT__vrf_0__DOT__write_bits_mask[7]);v.push_back(w);}
return v;}
static void send(VSaturnRocket&m,unsigned kind,bool valid){command(m,valid);m.io_core_ex_vconfig_vtype_vlmul_mag=kind==3?0:3;if(kind<3){m.io_core_ex_vconfig_vl=256;m.io_core_ex_vconfig_vtype_vsew=0;m.io_core_ex_inst=kind==0?0x5e03b457u:kind==1?0x5e02c457u:0x02050407u;m.io_core_ex_rs1=kind==2?0x80010000ULL:7ULL;}else m.io_core_ex_rs1=0;m.io_tlb_s1_resp_paddr=0x80010000ULL;}
static bool exready(VSaturnRocket&m){return m.io_core_ex_ready;}
static std::uint64_t scalar(VSaturnRocket&m){return m.io_core_resp_bits_data;}
static void data(VSaturnRocket&m,bool valid,unsigned tag,unsigned size){m.auto_atl_out_a_ready=1;m.auto_atl_out_d_valid=valid;m.auto_atl_out_d_bits_opcode=1;m.auto_atl_out_d_bits_source=tag;m.auto_atl_out_d_bits_size=size;m.auto_atl_out_d_bits_data=0x0707070707070707ULL;}
struct Reply{unsigned source,size,left;};
 template<class M>static void run(const char*profile,unsigned egs,unsigned dlen,unsigned bus,unsigned kind,unsigned seed,bool corrupt){
 auto ctx=std::make_unique<VerilatedContext>();ctx->threads(1);ctx->randSeed(seed);ctx->randReset(2);M m(ctx.get());inputs(m);m.reset=1;m.clock=0;m.eval();for(unsigned n=0;n<2;n++){m.clock=1;m.eval();m.clock=0;m.eval();}m.reset=0;
 std::vector<std::vector<std::uint32_t>> shadow(egs,std::vector<std::uint32_t>(dlen/32)),known(egs,std::vector<std::uint32_t>(dlen/32));for(unsigned eg=0;eg<egs;eg++)for(unsigned w=0;w<dlen/32;w++)shadow[eg][w]=ram(m,eg,w);
 std::deque<Reply> replies;std::set<unsigned> scrubbed,produced;unsigned writes_total=0,scrub_done=~0u,first_producer=~0u,reader_response=~0u;std::uint64_t readback=0,expected_readback=0;bool reader_sent=false,mutated=false;
 for(unsigned edge=0;edge<egs+160;edge++){
  bool reader=edge==egs+100;send(m,reader?3:kind,edge==0||reader);if(reader){reader_sent=true;unsigned target=8*(256/dlen);expected_readback=std::uint64_t(shadow[target][0])|(std::uint64_t(shadow[target][1])<<32);}
  data(m,!replies.empty(),replies.empty()?0:replies.front().source,replies.empty()?0:replies.front().size);m.eval();auto state=sweep(m);if(edge==0||reader)require(exready(m),"Fixture did not obey physical EX acceptance");if(!state.active&&scrub_done==~0u)scrub_done=edge;
  if(response(m)){require(reader_sent,"Unexpected scalar response before reader");require(reader_response==~0u,"Repeated scalar response");require(scalar(m)==expected_readback,"Architectural readback disagrees with exact accepted-write order");reader_response=edge;readback=scalar(m);}
  auto accepted=physical_writes(m);
  for(auto write:accepted){require(write.eg<egs,"Actual bank write address out of bounds");bool zero=true,seven=true;for(unsigned w=0;w<dlen/32;w++){zero&=write.data[w]==0;seven&=write.data[w]==0x07070707u;}require(zero||seven,"Unexpected writer data in zero/seven fixture");if(zero)scrubbed.insert(write.eg);if(seven){produced.insert(write.eg);if(first_producer==~0u)first_producer=edge;}
   std::cout<<"RESET_WRITE "<<profile<<','<<kind<<','<<seed<<','<<edge<<','<<unsigned(state.active)<<','<<state.cursor<<','<<write.eg<<','<<(zero?0:7);for(unsigned w=0;w<dlen/32;w++)std::cout<<','<<write.mask[w];std::cout<<'\n';
   if(corrupt&&seven&&!mutated){write.data[0]^=1;mutated=true;}
   for(unsigned w=0;w<dlen/32;w++){shadow[write.eg][w]=(shadow[write.eg][w]&~write.mask[w])|(write.data[w]&write.mask[w]);known[write.eg][w]|=write.mask[w];}++writes_total;
  }
  bool dpop=m.auto_atl_out_d_valid&&m.auto_atl_out_d_ready;bool apush=m.auto_atl_out_a_valid&&m.auto_atl_out_a_ready;Reply incoming{};
  if(apush){require(m.auto_atl_out_a_bits_opcode==4,"Unexpected non-Get in pure-load fixture");incoming={unsigned(m.auto_atl_out_a_bits_source),unsigned(m.auto_atl_out_a_bits_size),unsigned(((1ULL<<m.auto_atl_out_a_bits_size)+bus-1)/bus)};}
  m.clock=1;m.eval();m.clock=0;m.eval();for(unsigned eg=0;eg<egs;eg++)for(unsigned w=0;w<dlen/32;w++)require(ram(m,eg,w)==shadow[eg][w],"Accepted bank-write transcript does not explain physical VRF transition");
  if(dpop){require(!replies.empty(),"Fixture D without A");if(--replies.front().left==0)replies.pop_front();}if(apush)replies.push_back(incoming);
 }
 unsigned zero_words=0,seven_words=0,unknown_words=0;for(unsigned eg=0;eg<egs;eg++)for(unsigned w=0;w<dlen/32;w++){unknown_words+=known[eg][w]!=0xffffffffu;if(eg>=8*(256/dlen)&&eg<16*(256/dlen)){zero_words+=shadow[eg][w]==0;seven_words+=shadow[eg][w]==0x07070707u;}}
 require(replies.empty()&&reader_response!=~0u,"Early writer/reader did not drain");
 std::cout<<"RESET_WRITER_RESULT {\"profile\":\""<<profile<<"\",\"kind\":"<<kind<<",\"seed\":"<<seed<<",\"scrub_flag_clear_edge\":"<<scrub_done<<",\"first_nonzero_write_edge\":"<<first_producer<<",\"scrubbed_EGs_seen\":"<<scrubbed.size()<<",\"producer_EGs_seen\":"<<produced.size()<<",\"physical_writes\":"<<writes_total<<",\"destination_zero_words\":"<<zero_words<<",\"destination_seven_words\":"<<seven_words<<",\"unwritten_unknown_words\":"<<unknown_words<<",\"scalar_readback\":"<<readback<<",\"reader_response_edge\":"<<reader_response<<"}\n";
 }
 int main(int argc,char**argv){try{bool corrupt=argc==2&&std::string(argv[1])=="--corrupt-ledger";for(unsigned seed:{0u,17u})for(unsigned kind=0;kind<3;kind++){run<VSaturnCompute>("compute",64,128,32,kind,seed,corrupt);run<VSaturnRocket>("rocket",32,256,8,kind,seed,corrupt);}return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
