#include "saturn_timing.hpp"
#include "saturn_timing_identity.hpp"
#include "VSaturnCompute.h"
#include "VSaturnRocket.h"
#include "verilated.h"
#include <stdexcept>
namespace iris::saturn {
struct SaturnTimingCut::Impl {
 Profile profile;unsigned hart;std::uint64_t edge_count=0;bool evaluated=false;
 std::unique_ptr<VerilatedContext> context;std::unique_ptr<VSaturnCompute> compute;std::unique_ptr<VSaturnRocket> rocket;
 Impl(Profile p,unsigned h,std::uint32_t seed):profile(p),hart(h),context(std::make_unique<VerilatedContext>()){
  if((p==Profile::Compute128&&h>1)||(p==Profile::Rocket256&&h!=2))throw std::invalid_argument("Hart/profile mismatch");
  context->threads(1);context->randSeed(seed);context->randReset(2);
  if(p==Profile::Compute128){compute=std::make_unique<VSaturnCompute>(context.get());compute->clock=0;}
  else{rocket=std::make_unique<VSaturnRocket>(context.get());rocket->clock=0;}
 }
};
SaturnTimingCut::SaturnTimingCut(Profile p,unsigned h,std::uint32_t seed,ReferenceScope scope):impl_(std::make_unique<Impl>(p,h,seed)){
 if(scope!=ReferenceScope::ExplicitTwoStateWithExternalDefinedness)throw std::invalid_argument("Explicit reference definedness scope required");
}
SaturnTimingCut::~SaturnTimingCut()=default;
SaturnTimingCut::SaturnTimingCut(SaturnTimingCut&&)noexcept=default;
SaturnTimingCut&SaturnTimingCut::operator=(SaturnTimingCut&&)noexcept=default;
void SaturnTimingCut::evaluate(const ReferenceInputs&i){
 impl_->evaluated=false;
 auto fields=input_fields(impl_->profile);
 if(i.words.size()!=fields.size())throw std::invalid_argument("Incomplete/extra physical Saturn boundary");
 for(unsigned n=0;n<fields.size();n++)if(fields[n].word_width<64&&i.words[n]>=(1ULL<<fields[n].word_width))throw std::invalid_argument("Physical Saturn field exceeds source width");
if(impl_->profile==Profile::Compute128){auto&m=*impl_->compute;m.clock=0;
m.reset=i.words[0];
m.auto_atl_out_a_ready=i.words[1];
m.auto_atl_out_d_valid=i.words[2];
m.auto_atl_out_d_bits_opcode=i.words[3];
m.auto_atl_out_d_bits_param=i.words[4];
m.auto_atl_out_d_bits_size=i.words[5];
m.auto_atl_out_d_bits_source=i.words[6];
m.auto_atl_out_d_bits_sink=i.words[7];
m.auto_atl_out_d_bits_denied=i.words[8];
m.auto_atl_out_d_bits_data[0]=std::uint32_t(i.words[9]);
m.auto_atl_out_d_bits_data[1]=std::uint32_t(i.words[9]>>32);
m.auto_atl_out_d_bits_data[2]=std::uint32_t(i.words[10]);
m.auto_atl_out_d_bits_data[3]=std::uint32_t(i.words[10]>>32);
m.auto_atl_out_d_bits_data[4]=std::uint32_t(i.words[11]);
m.auto_atl_out_d_bits_data[5]=std::uint32_t(i.words[11]>>32);
m.auto_atl_out_d_bits_data[6]=std::uint32_t(i.words[12]);
m.auto_atl_out_d_bits_data[7]=std::uint32_t(i.words[12]>>32);
m.auto_atl_out_d_bits_corrupt=i.words[13];
m.io_status_prv=i.words[14];
m.io_ex_valid=i.words[15];
m.io_ex_uop_inst=i.words[16];
m.io_ex_uop_pc=i.words[17];
m.io_ex_uop_rs1_data=i.words[18];
m.io_ex_uop_rs2_data=i.words[19];
m.io_ex_vconfig_vl=i.words[20];
m.io_ex_vconfig_vtype_vill=i.words[21];
m.io_ex_vconfig_vtype_tm=i.words[22];
m.io_ex_vconfig_vtype_tk=i.words[23];
m.io_ex_vconfig_vtype_vtwiden=i.words[24];
m.io_ex_vconfig_vtype_altfmt=i.words[25];
m.io_ex_vconfig_vtype_vma=i.words[26];
m.io_ex_vconfig_vtype_vta=i.words[27];
m.io_ex_vconfig_vtype_vsew=i.words[28];
m.io_ex_vconfig_vtype_vlmul_sign=i.words[29];
m.io_ex_vconfig_vtype_vlmul_mag=i.words[30];
m.io_ex_vstart=i.words[31];
m.io_ex_fire=i.words[32];
m.io_mem_kill=i.words[33];
m.io_mem_tlb_req_ready=i.words[34];
m.io_mem_tlb_resp_miss=i.words[35];
m.io_mem_tlb_resp_paddr=i.words[36];
m.io_mem_tlb_resp_pf_ld=i.words[37];
m.io_mem_tlb_resp_pf_st=i.words[38];
m.io_mem_tlb_resp_ae_ld=i.words[39];
m.io_mem_tlb_resp_ae_st=i.words[40];
m.io_mem_tlb_resp_ma_ld=i.words[41];
m.io_mem_tlb_resp_ma_st=i.words[42];
m.io_mem_frs1=i.words[43];
m.io_com_store_pending=i.words[44];
m.io_com_vxrm=i.words[45];
m.io_com_frm=i.words[46];
m.io_com_scalar_check_bits_addr=i.words[47];
m.io_com_scalar_check_bits_store=i.words[48];
m.io_resp_ready=i.words[49];
m.eval();}
if(impl_->profile==Profile::Rocket256){auto&m=*impl_->rocket;m.clock=0;
m.reset=i.words[0];
m.auto_atl_out_a_ready=i.words[1];
m.auto_atl_out_d_valid=i.words[2];
m.auto_atl_out_d_bits_opcode=i.words[3];
m.auto_atl_out_d_bits_param=i.words[4];
m.auto_atl_out_d_bits_size=i.words[5];
m.auto_atl_out_d_bits_source=i.words[6];
m.auto_atl_out_d_bits_sink=i.words[7];
m.auto_atl_out_d_bits_denied=i.words[8];
m.auto_atl_out_d_bits_data=i.words[9];
m.auto_atl_out_d_bits_corrupt=i.words[10];
m.io_core_status_dv=i.words[11];
m.io_core_status_prv=i.words[12];
m.io_core_ex_valid=i.words[13];
m.io_core_ex_inst=i.words[14];
m.io_core_ex_pc=i.words[15];
m.io_core_ex_vconfig_vl=i.words[16];
m.io_core_ex_vconfig_vtype_vill=i.words[17];
m.io_core_ex_vconfig_vtype_vtwiden=i.words[18];
m.io_core_ex_vconfig_vtype_altfmt=i.words[19];
m.io_core_ex_vconfig_vtype_vma=i.words[20];
m.io_core_ex_vconfig_vtype_vta=i.words[21];
m.io_core_ex_vconfig_vtype_vsew=i.words[22];
m.io_core_ex_vconfig_vtype_vlmul_sign=i.words[23];
m.io_core_ex_vconfig_vtype_vlmul_mag=i.words[24];
m.io_core_ex_vstart=i.words[25];
m.io_core_ex_rs1=i.words[26];
m.io_core_ex_rs2=i.words[27];
m.io_core_killm=i.words[28];
m.io_core_mem_frs1=i.words[29];
m.io_core_wb_store_pending=i.words[30];
m.io_core_wb_vxrm=i.words[31];
m.io_core_wb_frm=i.words[32];
m.io_core_resp_ready=i.words[33];
m.io_tlb_s1_resp_miss=i.words[34];
m.io_tlb_s1_resp_paddr=i.words[35];
m.io_tlb_s1_resp_pf_ld=i.words[36];
m.io_tlb_s1_resp_pf_st=i.words[37];
m.io_tlb_s1_resp_ae_ld=i.words[38];
m.io_tlb_s1_resp_ae_st=i.words[39];
m.io_tlb_s1_resp_ma_ld=i.words[40];
m.io_tlb_s1_resp_ma_st=i.words[41];
m.io_tlb_s1_resp_cmd=i.words[42];
m.io_dmem_req_ready=i.words[43];
m.io_dmem_s2_nack=i.words[44];
m.io_dmem_resp_valid=i.words[45];
m.io_dmem_resp_bits_tag=i.words[46];
m.io_dmem_resp_bits_data_raw[0]=std::uint32_t(i.words[47]);
m.io_dmem_resp_bits_data_raw[1]=std::uint32_t(i.words[47]>>32);
m.io_dmem_resp_bits_data_raw[2]=std::uint32_t(i.words[48]);
m.io_dmem_resp_bits_data_raw[3]=std::uint32_t(i.words[48]>>32);
m.io_dmem_resp_bits_data_raw[4]=std::uint32_t(i.words[49]);
m.io_dmem_resp_bits_data_raw[5]=std::uint32_t(i.words[49]>>32);
m.io_dmem_resp_bits_data_raw[6]=std::uint32_t(i.words[50]);
m.io_dmem_resp_bits_data_raw[7]=std::uint32_t(i.words[50]>>32);
m.io_dmem_s2_xcpt_ma_ld=i.words[51];
m.io_dmem_s2_xcpt_ma_st=i.words[52];
m.io_dmem_s2_xcpt_pf_ld=i.words[53];
m.io_dmem_s2_xcpt_pf_st=i.words[54];
m.io_dmem_s2_xcpt_ae_ld=i.words[55];
m.io_dmem_s2_xcpt_ae_st=i.words[56];
m.io_fp_req_ready=i.words[57];
m.io_fp_resp_valid=i.words[58];
m.io_fp_resp_bits_data[0]=std::uint32_t(i.words[59]);
m.io_fp_resp_bits_data[1]=std::uint32_t(i.words[59]>>32);
m.io_fp_resp_bits_data[2]=std::uint32_t(i.words[60]);
m.eval();}
impl_->evaluated=true;
}
ReferenceOutputs SaturnTimingCut::sample()const{
if(!impl_->evaluated)throw std::logic_error("Saturn sample requires fresh evaluate");ReferenceOutputs o;o.words.resize(output_fields(impl_->profile).size());
if(impl_->profile==Profile::Compute128){const auto&m=*impl_->compute;
o.words[0]=m.auto_atl_out_a_valid;
o.words[1]=m.auto_atl_out_a_bits_opcode;
o.words[2]=m.auto_atl_out_a_bits_param;
o.words[3]=m.auto_atl_out_a_bits_size;
o.words[4]=m.auto_atl_out_a_bits_source;
o.words[5]=m.auto_atl_out_a_bits_address;
o.words[6]=m.auto_atl_out_a_bits_mask;
o.words[7]=std::uint64_t{m.auto_atl_out_a_bits_data[0]}|(std::uint64_t{m.auto_atl_out_a_bits_data[1]}<<32);
o.words[8]=std::uint64_t{m.auto_atl_out_a_bits_data[2]}|(std::uint64_t{m.auto_atl_out_a_bits_data[3]}<<32);
o.words[9]=std::uint64_t{m.auto_atl_out_a_bits_data[4]}|(std::uint64_t{m.auto_atl_out_a_bits_data[5]}<<32);
o.words[10]=std::uint64_t{m.auto_atl_out_a_bits_data[6]}|(std::uint64_t{m.auto_atl_out_a_bits_data[7]}<<32);
o.words[11]=m.auto_atl_out_a_bits_corrupt;
o.words[12]=m.auto_atl_out_d_ready;
o.words[13]=m.io_ex_ready;
o.words[14]=m.io_mem_tlb_req_valid;
o.words[15]=m.io_mem_tlb_req_bits_vaddr;
o.words[16]=m.io_mem_tlb_req_bits_size;
o.words[17]=m.io_mem_tlb_req_bits_cmd;
o.words[18]=m.io_mem_tlb_req_bits_prv;
o.words[19]=m.io_com_retire_late;
o.words[20]=m.io_com_pc;
o.words[21]=m.io_com_xcpt;
o.words[22]=m.io_com_cause;
o.words[23]=m.io_com_tval;
o.words[24]=m.io_com_scalar_check_ready;
o.words[25]=m.io_com_internal_replay;
o.words[26]=m.io_com_block_all;
o.words[27]=m.io_resp_valid;
o.words[28]=m.io_resp_bits_fp;
o.words[29]=m.io_resp_bits_size;
o.words[30]=m.io_resp_bits_rd;
o.words[31]=m.io_resp_bits_data;
o.words[32]=m.io_set_vstart_valid;
o.words[33]=m.io_set_vstart_bits;
o.words[34]=m.io_set_vxsat;
o.words[35]=m.io_set_vconfig_valid;
o.words[36]=m.io_set_vconfig_bits_vl;
o.words[37]=m.io_set_vconfig_bits_vtype_vill;
o.words[38]=m.io_set_vconfig_bits_vtype_tm;
o.words[39]=m.io_set_vconfig_bits_vtype_tk;
o.words[40]=m.io_set_vconfig_bits_vtype_vtwiden;
o.words[41]=m.io_set_vconfig_bits_vtype_altfmt;
o.words[42]=m.io_set_vconfig_bits_vtype_vma;
o.words[43]=m.io_set_vconfig_bits_vtype_vta;
o.words[44]=m.io_set_vconfig_bits_vtype_vsew;
o.words[45]=m.io_set_vconfig_bits_vtype_vlmul_sign;
o.words[46]=m.io_set_vconfig_bits_vtype_vlmul_mag;
o.words[47]=m.io_set_fflags_valid;
o.words[48]=m.io_set_fflags_bits;
o.words[49]=m.io_trap_check_busy;
o.words[50]=m.io_backend_busy;
}
if(impl_->profile==Profile::Rocket256){const auto&m=*impl_->rocket;
o.words[0]=m.auto_atl_out_a_valid;
o.words[1]=m.auto_atl_out_a_bits_opcode;
o.words[2]=m.auto_atl_out_a_bits_param;
o.words[3]=m.auto_atl_out_a_bits_size;
o.words[4]=m.auto_atl_out_a_bits_source;
o.words[5]=m.auto_atl_out_a_bits_address;
o.words[6]=m.auto_atl_out_a_bits_mask;
o.words[7]=m.auto_atl_out_a_bits_data;
o.words[8]=m.auto_atl_out_a_bits_corrupt;
o.words[9]=m.auto_atl_out_d_ready;
o.words[10]=m.io_core_ex_ready;
o.words[11]=m.io_core_mem_block_mem;
o.words[12]=m.io_core_mem_block_all;
o.words[13]=m.io_core_wb_replay;
o.words[14]=m.io_core_wb_retire;
o.words[15]=m.io_core_wb_inst;
o.words[16]=m.io_core_wb_pc;
o.words[17]=m.io_core_wb_xcpt;
o.words[18]=m.io_core_wb_cause;
o.words[19]=m.io_core_wb_tval;
o.words[20]=m.io_core_resp_valid;
o.words[21]=m.io_core_resp_bits_fp;
o.words[22]=m.io_core_resp_bits_size;
o.words[23]=m.io_core_resp_bits_rd;
o.words[24]=m.io_core_resp_bits_data;
o.words[25]=m.io_core_set_vstart_valid;
o.words[26]=m.io_core_set_vstart_bits;
o.words[27]=m.io_core_set_vxsat;
o.words[28]=m.io_core_set_vconfig_valid;
o.words[29]=m.io_core_set_vconfig_bits_vl;
o.words[30]=m.io_core_set_vconfig_bits_vtype_vill;
o.words[31]=m.io_core_set_vconfig_bits_vtype_vtwiden;
o.words[32]=m.io_core_set_vconfig_bits_vtype_altfmt;
o.words[33]=m.io_core_set_vconfig_bits_vtype_vma;
o.words[34]=m.io_core_set_vconfig_bits_vtype_vta;
o.words[35]=m.io_core_set_vconfig_bits_vtype_vsew;
o.words[36]=m.io_core_set_vconfig_bits_vtype_vlmul_sign;
o.words[37]=m.io_core_set_vconfig_bits_vtype_vlmul_mag;
o.words[38]=m.io_core_set_fflags_valid;
o.words[39]=m.io_core_set_fflags_bits;
o.words[40]=m.io_core_trap_check_busy;
o.words[41]=m.io_core_backend_busy;
o.words[42]=m.io_tlb_req_valid;
o.words[43]=m.io_tlb_req_bits_vaddr;
o.words[44]=m.io_tlb_req_bits_size;
o.words[45]=m.io_tlb_req_bits_cmd;
o.words[46]=m.io_tlb_req_bits_prv;
o.words[47]=m.io_dmem_req_valid;
o.words[48]=m.io_dmem_req_bits_addr;
o.words[49]=m.io_dmem_req_bits_tag;
o.words[50]=m.io_dmem_req_bits_cmd;
o.words[51]=m.io_dmem_req_bits_size;
o.words[52]=m.io_dmem_req_bits_signed;
o.words[53]=m.io_dmem_req_bits_dprv;
o.words[54]=m.io_dmem_req_bits_dv;
o.words[55]=m.io_dmem_req_bits_phys;
o.words[56]=m.io_dmem_req_bits_no_alloc;
o.words[57]=m.io_dmem_req_bits_no_xcpt;
o.words[58]=m.io_dmem_req_bits_mask;
o.words[59]=std::uint64_t{m.io_dmem_s1_data_data[0]}|(std::uint64_t{m.io_dmem_s1_data_data[1]}<<32);
o.words[60]=std::uint64_t{m.io_dmem_s1_data_data[2]}|(std::uint64_t{m.io_dmem_s1_data_data[3]}<<32);
o.words[61]=std::uint64_t{m.io_dmem_s1_data_data[4]}|(std::uint64_t{m.io_dmem_s1_data_data[5]}<<32);
o.words[62]=std::uint64_t{m.io_dmem_s1_data_data[6]}|(std::uint64_t{m.io_dmem_s1_data_data[7]}<<32);
o.words[63]=m.io_dmem_s1_data_mask;
o.words[64]=m.io_fp_req_valid;
o.words[65]=m.io_fp_req_bits_ren3;
o.words[66]=m.io_fp_req_bits_swap23;
o.words[67]=m.io_fp_req_bits_typeTagIn;
o.words[68]=m.io_fp_req_bits_typeTagOut;
o.words[69]=m.io_fp_req_bits_rm;
o.words[70]=m.io_fp_req_bits_fmaCmd;
o.words[71]=std::uint64_t{m.io_fp_req_bits_in1[0]}|(std::uint64_t{m.io_fp_req_bits_in1[1]}<<32);
o.words[72]=std::uint64_t{m.io_fp_req_bits_in1[2]};
o.words[73]=std::uint64_t{m.io_fp_req_bits_in2[0]}|(std::uint64_t{m.io_fp_req_bits_in2[1]}<<32);
o.words[74]=std::uint64_t{m.io_fp_req_bits_in2[2]};
o.words[75]=std::uint64_t{m.io_fp_req_bits_in3[0]}|(std::uint64_t{m.io_fp_req_bits_in3[1]}<<32);
o.words[76]=std::uint64_t{m.io_fp_req_bits_in3[2]};
}
return o;
}
void SaturnTimingCut::commit(){
 if(!impl_->evaluated)throw std::logic_error("Saturn commit requires fresh evaluate");
 if(impl_->profile==Profile::Compute128){auto&m=*impl_->compute;m.clock=1;m.eval();m.clock=0;m.eval();}
 else{auto&m=*impl_->rocket;m.clock=1;m.eval();m.clock=0;m.eval();}
 ++impl_->edge_count;impl_->evaluated=false;
}
ReferenceOutputs SaturnTimingCut::step(const ReferenceInputs&i){evaluate(i);auto o=sample();commit();return o;}
std::uint64_t SaturnTimingCut::edges()const{return impl_->edge_count;}
Profile SaturnTimingCut::profile()const{return impl_->profile;}
unsigned SaturnTimingCut::hart()const{return impl_->hart;}
const char* SaturnTimingCut::source_identity(){return IRIS_SATURN_TIMING_SOURCE_ID;}
std::string_view SaturnTimingCut::source_clock_id(Profile p,unsigned h){
 if(p==Profile::Compute128&&h==0)return "sbusFixedClockNode.out2";
 if(p==Profile::Compute128&&h==1)return "sbusFixedClockNode.out3";
 if(p==Profile::Rocket256&&h==2)return "tileClockGroup.rockettile_2";
 throw std::invalid_argument("Hart/profile clock mismatch");
}
std::span<const Field> SaturnTimingCut::input_fields(Profile p){
static constexpr Field compute[]={{"reset",1,0,1},{"auto_atl_out_a_ready",1,0,1},{"auto_atl_out_d_valid",1,0,1},{"auto_atl_out_d_bits_opcode",3,0,3},{"auto_atl_out_d_bits_param",2,0,2},{"auto_atl_out_d_bits_size",4,0,4},{"auto_atl_out_d_bits_source",5,0,5},{"auto_atl_out_d_bits_sink",4,0,4},{"auto_atl_out_d_bits_denied",1,0,1},{"auto_atl_out_d_bits_data_0",256,0,64},{"auto_atl_out_d_bits_data_1",256,64,64},{"auto_atl_out_d_bits_data_2",256,128,64},{"auto_atl_out_d_bits_data_3",256,192,64},{"auto_atl_out_d_bits_corrupt",1,0,1},{"io_status_prv",2,0,2},{"io_ex_valid",1,0,1},{"io_ex_uop_inst",32,0,32},{"io_ex_uop_pc",40,0,40},{"io_ex_uop_rs1_data",64,0,64},{"io_ex_uop_rs2_data",64,0,64},{"io_ex_vconfig_vl",9,0,9},{"io_ex_vconfig_vtype_vill",1,0,1},{"io_ex_vconfig_vtype_tm",14,0,14},{"io_ex_vconfig_vtype_tk",3,0,3},{"io_ex_vconfig_vtype_vtwiden",2,0,2},{"io_ex_vconfig_vtype_altfmt",1,0,1},{"io_ex_vconfig_vtype_vma",1,0,1},{"io_ex_vconfig_vtype_vta",1,0,1},{"io_ex_vconfig_vtype_vsew",3,0,3},{"io_ex_vconfig_vtype_vlmul_sign",1,0,1},{"io_ex_vconfig_vtype_vlmul_mag",2,0,2},{"io_ex_vstart",8,0,8},{"io_ex_fire",1,0,1},{"io_mem_kill",1,0,1},{"io_mem_tlb_req_ready",1,0,1},{"io_mem_tlb_resp_miss",1,0,1},{"io_mem_tlb_resp_paddr",35,0,35},{"io_mem_tlb_resp_pf_ld",1,0,1},{"io_mem_tlb_resp_pf_st",1,0,1},{"io_mem_tlb_resp_ae_ld",1,0,1},{"io_mem_tlb_resp_ae_st",1,0,1},{"io_mem_tlb_resp_ma_ld",1,0,1},{"io_mem_tlb_resp_ma_st",1,0,1},{"io_mem_frs1",64,0,64},{"io_com_store_pending",1,0,1},{"io_com_vxrm",2,0,2},{"io_com_frm",3,0,3},{"io_com_scalar_check_bits_addr",35,0,35},{"io_com_scalar_check_bits_store",1,0,1},{"io_resp_ready",1,0,1}};
static constexpr Field rocket[]={{"reset",1,0,1},{"auto_atl_out_a_ready",1,0,1},{"auto_atl_out_d_valid",1,0,1},{"auto_atl_out_d_bits_opcode",3,0,3},{"auto_atl_out_d_bits_param",2,0,2},{"auto_atl_out_d_bits_size",4,0,4},{"auto_atl_out_d_bits_source",6,0,6},{"auto_atl_out_d_bits_sink",4,0,4},{"auto_atl_out_d_bits_denied",1,0,1},{"auto_atl_out_d_bits_data",64,0,64},{"auto_atl_out_d_bits_corrupt",1,0,1},{"io_core_status_dv",1,0,1},{"io_core_status_prv",2,0,2},{"io_core_ex_valid",1,0,1},{"io_core_ex_inst",32,0,32},{"io_core_ex_pc",40,0,40},{"io_core_ex_vconfig_vl",9,0,9},{"io_core_ex_vconfig_vtype_vill",1,0,1},{"io_core_ex_vconfig_vtype_vtwiden",2,0,2},{"io_core_ex_vconfig_vtype_altfmt",1,0,1},{"io_core_ex_vconfig_vtype_vma",1,0,1},{"io_core_ex_vconfig_vtype_vta",1,0,1},{"io_core_ex_vconfig_vtype_vsew",3,0,3},{"io_core_ex_vconfig_vtype_vlmul_sign",1,0,1},{"io_core_ex_vconfig_vtype_vlmul_mag",2,0,2},{"io_core_ex_vstart",8,0,8},{"io_core_ex_rs1",64,0,64},{"io_core_ex_rs2",64,0,64},{"io_core_killm",1,0,1},{"io_core_mem_frs1",64,0,64},{"io_core_wb_store_pending",1,0,1},{"io_core_wb_vxrm",2,0,2},{"io_core_wb_frm",3,0,3},{"io_core_resp_ready",1,0,1},{"io_tlb_s1_resp_miss",1,0,1},{"io_tlb_s1_resp_paddr",35,0,35},{"io_tlb_s1_resp_pf_ld",1,0,1},{"io_tlb_s1_resp_pf_st",1,0,1},{"io_tlb_s1_resp_ae_ld",1,0,1},{"io_tlb_s1_resp_ae_st",1,0,1},{"io_tlb_s1_resp_ma_ld",1,0,1},{"io_tlb_s1_resp_ma_st",1,0,1},{"io_tlb_s1_resp_cmd",5,0,5},{"io_dmem_req_ready",1,0,1},{"io_dmem_s2_nack",1,0,1},{"io_dmem_resp_valid",1,0,1},{"io_dmem_resp_bits_tag",8,0,8},{"io_dmem_resp_bits_data_raw_0",256,0,64},{"io_dmem_resp_bits_data_raw_1",256,64,64},{"io_dmem_resp_bits_data_raw_2",256,128,64},{"io_dmem_resp_bits_data_raw_3",256,192,64},{"io_dmem_s2_xcpt_ma_ld",1,0,1},{"io_dmem_s2_xcpt_ma_st",1,0,1},{"io_dmem_s2_xcpt_pf_ld",1,0,1},{"io_dmem_s2_xcpt_pf_st",1,0,1},{"io_dmem_s2_xcpt_ae_ld",1,0,1},{"io_dmem_s2_xcpt_ae_st",1,0,1},{"io_fp_req_ready",1,0,1},{"io_fp_resp_valid",1,0,1},{"io_fp_resp_bits_data_0",65,0,64},{"io_fp_resp_bits_data_1",65,64,1}};
if(p==Profile::Compute128)return compute;if(p==Profile::Rocket256)return rocket;throw std::invalid_argument("Unknown source Saturn profile");}
std::span<const Field> SaturnTimingCut::output_fields(Profile p){
static constexpr Field compute[]={{"auto_atl_out_a_valid",1,0,1},{"auto_atl_out_a_bits_opcode",3,0,3},{"auto_atl_out_a_bits_param",3,0,3},{"auto_atl_out_a_bits_size",4,0,4},{"auto_atl_out_a_bits_source",5,0,5},{"auto_atl_out_a_bits_address",35,0,35},{"auto_atl_out_a_bits_mask",32,0,32},{"auto_atl_out_a_bits_data_0",256,0,64},{"auto_atl_out_a_bits_data_1",256,64,64},{"auto_atl_out_a_bits_data_2",256,128,64},{"auto_atl_out_a_bits_data_3",256,192,64},{"auto_atl_out_a_bits_corrupt",1,0,1},{"auto_atl_out_d_ready",1,0,1},{"io_ex_ready",1,0,1},{"io_mem_tlb_req_valid",1,0,1},{"io_mem_tlb_req_bits_vaddr",40,0,40},{"io_mem_tlb_req_bits_size",2,0,2},{"io_mem_tlb_req_bits_cmd",5,0,5},{"io_mem_tlb_req_bits_prv",2,0,2},{"io_com_retire_late",1,0,1},{"io_com_pc",40,0,40},{"io_com_xcpt",1,0,1},{"io_com_cause",5,0,5},{"io_com_tval",40,0,40},{"io_com_scalar_check_ready",1,0,1},{"io_com_internal_replay",1,0,1},{"io_com_block_all",1,0,1},{"io_resp_valid",1,0,1},{"io_resp_bits_fp",1,0,1},{"io_resp_bits_size",2,0,2},{"io_resp_bits_rd",5,0,5},{"io_resp_bits_data",64,0,64},{"io_set_vstart_valid",1,0,1},{"io_set_vstart_bits",8,0,8},{"io_set_vxsat",1,0,1},{"io_set_vconfig_valid",1,0,1},{"io_set_vconfig_bits_vl",9,0,9},{"io_set_vconfig_bits_vtype_vill",1,0,1},{"io_set_vconfig_bits_vtype_tm",14,0,14},{"io_set_vconfig_bits_vtype_tk",3,0,3},{"io_set_vconfig_bits_vtype_vtwiden",2,0,2},{"io_set_vconfig_bits_vtype_altfmt",1,0,1},{"io_set_vconfig_bits_vtype_vma",1,0,1},{"io_set_vconfig_bits_vtype_vta",1,0,1},{"io_set_vconfig_bits_vtype_vsew",3,0,3},{"io_set_vconfig_bits_vtype_vlmul_sign",1,0,1},{"io_set_vconfig_bits_vtype_vlmul_mag",2,0,2},{"io_set_fflags_valid",1,0,1},{"io_set_fflags_bits",5,0,5},{"io_trap_check_busy",1,0,1},{"io_backend_busy",1,0,1}};
static constexpr Field rocket[]={{"auto_atl_out_a_valid",1,0,1},{"auto_atl_out_a_bits_opcode",3,0,3},{"auto_atl_out_a_bits_param",3,0,3},{"auto_atl_out_a_bits_size",4,0,4},{"auto_atl_out_a_bits_source",6,0,6},{"auto_atl_out_a_bits_address",35,0,35},{"auto_atl_out_a_bits_mask",8,0,8},{"auto_atl_out_a_bits_data",64,0,64},{"auto_atl_out_a_bits_corrupt",1,0,1},{"auto_atl_out_d_ready",1,0,1},{"io_core_ex_ready",1,0,1},{"io_core_mem_block_mem",1,0,1},{"io_core_mem_block_all",1,0,1},{"io_core_wb_replay",1,0,1},{"io_core_wb_retire",1,0,1},{"io_core_wb_inst",32,0,32},{"io_core_wb_pc",40,0,40},{"io_core_wb_xcpt",1,0,1},{"io_core_wb_cause",5,0,5},{"io_core_wb_tval",40,0,40},{"io_core_resp_valid",1,0,1},{"io_core_resp_bits_fp",1,0,1},{"io_core_resp_bits_size",2,0,2},{"io_core_resp_bits_rd",5,0,5},{"io_core_resp_bits_data",64,0,64},{"io_core_set_vstart_valid",1,0,1},{"io_core_set_vstart_bits",8,0,8},{"io_core_set_vxsat",1,0,1},{"io_core_set_vconfig_valid",1,0,1},{"io_core_set_vconfig_bits_vl",9,0,9},{"io_core_set_vconfig_bits_vtype_vill",1,0,1},{"io_core_set_vconfig_bits_vtype_vtwiden",2,0,2},{"io_core_set_vconfig_bits_vtype_altfmt",1,0,1},{"io_core_set_vconfig_bits_vtype_vma",1,0,1},{"io_core_set_vconfig_bits_vtype_vta",1,0,1},{"io_core_set_vconfig_bits_vtype_vsew",3,0,3},{"io_core_set_vconfig_bits_vtype_vlmul_sign",1,0,1},{"io_core_set_vconfig_bits_vtype_vlmul_mag",2,0,2},{"io_core_set_fflags_valid",1,0,1},{"io_core_set_fflags_bits",5,0,5},{"io_core_trap_check_busy",1,0,1},{"io_core_backend_busy",1,0,1},{"io_tlb_req_valid",1,0,1},{"io_tlb_req_bits_vaddr",40,0,40},{"io_tlb_req_bits_size",3,0,3},{"io_tlb_req_bits_cmd",5,0,5},{"io_tlb_req_bits_prv",2,0,2},{"io_dmem_req_valid",1,0,1},{"io_dmem_req_bits_addr",40,0,40},{"io_dmem_req_bits_tag",8,0,8},{"io_dmem_req_bits_cmd",5,0,5},{"io_dmem_req_bits_size",3,0,3},{"io_dmem_req_bits_signed",1,0,1},{"io_dmem_req_bits_dprv",2,0,2},{"io_dmem_req_bits_dv",1,0,1},{"io_dmem_req_bits_phys",1,0,1},{"io_dmem_req_bits_no_alloc",1,0,1},{"io_dmem_req_bits_no_xcpt",1,0,1},{"io_dmem_req_bits_mask",32,0,32},{"io_dmem_s1_data_data_0",256,0,64},{"io_dmem_s1_data_data_1",256,64,64},{"io_dmem_s1_data_data_2",256,128,64},{"io_dmem_s1_data_data_3",256,192,64},{"io_dmem_s1_data_mask",32,0,32},{"io_fp_req_valid",1,0,1},{"io_fp_req_bits_ren3",1,0,1},{"io_fp_req_bits_swap23",1,0,1},{"io_fp_req_bits_typeTagIn",2,0,2},{"io_fp_req_bits_typeTagOut",2,0,2},{"io_fp_req_bits_rm",3,0,3},{"io_fp_req_bits_fmaCmd",2,0,2},{"io_fp_req_bits_in1_0",65,0,64},{"io_fp_req_bits_in1_1",65,64,1},{"io_fp_req_bits_in2_0",65,0,64},{"io_fp_req_bits_in2_1",65,64,1},{"io_fp_req_bits_in3_0",65,0,64},{"io_fp_req_bits_in3_1",65,64,1}};
if(p==Profile::Compute128)return compute;if(p==Profile::Rocket256)return rocket;throw std::invalid_argument("Unknown source Saturn profile");}
}
