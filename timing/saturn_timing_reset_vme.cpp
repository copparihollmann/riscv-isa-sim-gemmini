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

#include <vector>
static void packet(VSaturnCompute&m,unsigned sequence,unsigned slot,bool valid){m.io_ex_valid=valid;m.io_ex_fire=valid;m.io_ex_uop_pc=0x80002000+4*slot;m.io_ex_vconfig_vl=1;m.io_ex_vconfig_vtype_vsew=0;m.io_ex_vconfig_vtype_vlmul_mag=0;m.io_ex_vconfig_vtype_tm=1;m.io_ex_vconfig_vtype_tk=1;m.io_ex_vconfig_vtype_vtwiden=3;if(sequence&&slot<2){m.io_ex_uop_inst=slot?0x5e01b857u:0x5e03b457u;m.io_ex_vconfig_vtype_vtwiden=0;}else m.io_ex_uop_inst=slot==(sequence?2:0)?0x43e06057u:0xf2880077u;}
static void run(unsigned producers,unsigned seed,bool corrupt){auto ctx=std::make_unique<VerilatedContext>();ctx->threads(1);ctx->randSeed(seed);ctx->randReset(2);VSaturnCompute m(ctx.get());inputs(m);m.reset=1;m.clock=0;m.eval();for(unsigned n=0;n<2;n++){m.clock=1;m.eval();m.clock=0;m.eval();}std::array<std::uint32_t,16>old;old[0]=m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_0;old[1]=m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_1;old[2]=m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_2;old[3]=m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_3;old[4]=m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_4;old[5]=m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_5;old[6]=m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_6;old[7]=m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_7;old[8]=m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_8;old[9]=m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_9;old[10]=m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_10;old[11]=m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_11;old[12]=m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_12;old[13]=m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_13;old[14]=m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_14;old[15]=m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_15;m.reset=0;unsigned first_mm=~0u,operand_wait_edges=0,mm_count=0;for(unsigned edge=0;edge<160;edge++){packet(m,producers,edge,edge<(producers?4:2));m.eval();auto sweep_state=sweep(m);bool mm=m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vos__DOT__mm,fire=m.rootp->SaturnShuttleUnit__DOT__vu__DOT___vos_io_iss_valid;bool reads=m.rootp->SaturnShuttleUnit__DOT__vu__DOT___vos_io_rvs1_valid||m.rootp->SaturnShuttleUnit__DOT__vu__DOT___vos_io_rvs2_valid;if(mm&&reads&&sweep_state.active){require(!fire,"VME operand read escaped source reset gate");++operand_wait_edges;}if(mm&&fire){if(first_mm==~0u)first_mm=edge;++mm_count;require(!sweep_state.active,"VME MAC issued before source scrub completion");require(ram(m,16,0)==(producers?7u:0u),"VME A operand did not honor prior vector write");require(ram(m,32,0)==(producers?3u:0u),"VME B operand did not honor prior vector write");}m.clock=1;m.eval();m.clock=0;m.eval();}require(mm_count==1&&first_mm>=64,"Early VME sequence did not issue exactly once after scrub");require((m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_0^(corrupt?1u:0u))==(producers?21u:0u),"VME MAC result contradicts explicit zero tile and source operands");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_1==old[1],"Untouched tile entry changed");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_2==old[2],"Untouched tile entry changed");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_3==old[3],"Untouched tile entry changed");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_4==old[4],"Untouched tile entry changed");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_5==old[5],"Untouched tile entry changed");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_6==old[6],"Untouched tile entry changed");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_7==old[7],"Untouched tile entry changed");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_8==old[8],"Untouched tile entry changed");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_9==old[9],"Untouched tile entry changed");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_10==old[10],"Untouched tile entry changed");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_11==old[11],"Untouched tile entry changed");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_12==old[12],"Untouched tile entry changed");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_13==old[13],"Untouched tile entry changed");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_14==old[14],"Untouched tile entry changed");require(m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_15==old[15],"Untouched tile entry changed");std::cout<<"RESET_VME_RESULT {\"seed\":"<<seed<<",\"prior_vector_producers\":"<<producers<<",\"first_MM_edge\":"<<first_mm<<",\"operand_wait_edges_during_scrub\":"<<operand_wait_edges<<",\"C00\":"<<m.rootp->SaturnShuttleUnit__DOT__vu__DOT__vopu__DOT__clusters_0_0__DOT__cells_0_0__DOT__regs_0<<",\"explicit_tile_zero\":true,\"other_sampled_entries_preserved\":true}\n";}
int main(int argc,char**argv){try{bool corrupt=argc==2&&std::string(argv[1])=="--corrupt-result";for(unsigned seed:{0u,17u})for(unsigned producers:{0u,1u})run(producers,seed,corrupt);return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
