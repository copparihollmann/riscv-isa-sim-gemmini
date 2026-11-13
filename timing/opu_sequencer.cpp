#include "opu_sequencer.hpp"
#include "opu_sequencer_identity.hpp"
#include "VOPUSequencer.h"
#include "verilated.h"
#include <stdexcept>
namespace iris::opu {
struct IrisOPUSequencer::Impl {
 std::unique_ptr<VerilatedContext> context;std::unique_ptr<VOPUSequencer> model;
 std::uint64_t edge_count=0;bool evaluated=false,reset_seen=false,dispatch_seen=false;
 explicit Impl(std::uint32_t seed):context(std::make_unique<VerilatedContext>()){
  context->threads(1);context->randSeed(seed);context->randReset(2);
  model=std::make_unique<VOPUSequencer>(context.get());model->clock=0;
 }
};
IrisOPUSequencer::IrisOPUSequencer(std::uint32_t seed):impl_(std::make_unique<Impl>(seed)){}
IrisOPUSequencer::~IrisOPUSequencer()=default;
IrisOPUSequencer::IrisOPUSequencer(IrisOPUSequencer&&)noexcept=default;
IrisOPUSequencer& IrisOPUSequencer::operator=(IrisOPUSequencer&&)noexcept=default;
void IrisOPUSequencer::evaluate(const SequencerInputs&i){
 impl_->evaluated=false;auto&m=*impl_->model;
if(i.values[0]>=2ULL)throw std::invalid_argument("OPU field exceeds width: reset");
if(i.values[1]>=2ULL)throw std::invalid_argument("OPU field exceeds width: io_dis_valid");
if(i.values[2]>=4294967296ULL)throw std::invalid_argument("OPU field exceeds width: io_dis_bits_bits");
if(i.values[3]>=512ULL)throw std::invalid_argument("OPU field exceeds width: io_dis_bits_vconfig_vl");
if(i.values[4]>=16384ULL)throw std::invalid_argument("OPU field exceeds width: io_dis_bits_vconfig_vtype_tm");
if(i.values[5]>=8ULL)throw std::invalid_argument("OPU field exceeds width: io_dis_bits_vconfig_vtype_tk");
if(i.values[6]>=2ULL)throw std::invalid_argument("OPU field exceeds width: io_dis_bits_vconfig_vtype_altfmt");
if(i.values[7]>=8ULL)throw std::invalid_argument("OPU field exceeds width: io_dis_bits_vconfig_vtype_vsew");
if(i.values[9]>=32ULL)throw std::invalid_argument("OPU field exceeds width: io_dis_bits_vat");
if(i.values[10]>=8ULL)throw std::invalid_argument("OPU field exceeds width: io_dis_bits_rm");
if(i.values[11]>=4ULL)throw std::invalid_argument("OPU field exceeds width: io_dis_bits_emul");
if(i.values[14]>=32ULL)throw std::invalid_argument("OPU field exceeds width: io_vat_head");
if(i.values[15]>=2ULL)throw std::invalid_argument("OPU field exceeds width: io_rvs1_ready");
if(i.values[16]>=2ULL)throw std::invalid_argument("OPU field exceeds width: io_rvs2_ready");
if(i.values[17]>=2ULL)throw std::invalid_argument("OPU field exceeds width: io_pipe_write_req_available");
const auto bits=i.values[2], sew=i.values[7];
auto key=bits&0xfc00707fULL;
 bool mm=(key==0xf0000077ULL||key==0xf0001077ULL);
 bool mvin=key==0x5c006057ULL;
 bool mvout=(bits&0xfdf0707fULL)==0x41f06057ULL;
 bool zero=(bits&0xfdfff07fULL)==0x41e06057ULL;
 bool discard=(bits&0xfdfff07fULL)==0x41c06057ULL;
if(i.values[1]){
if(i.values[0])throw std::invalid_argument("Dispatch while reset asserted is outside qualified ABI");
if(!impl_->reset_seen)throw std::invalid_argument("Physical reset required before dispatch");
if(!(mm||mvin||mvout||zero||discard)|| (mm&&sew!=0)||((mvin||mvout)&&sew!=2))throw std::invalid_argument("Instruction not accepted by saved OPU dispatcher profile");
if(i.values[3]>32||i.values[4]>32||i.values[5]>4)throw std::invalid_argument("Matrix geometry exceeds source-clamped tile profile");
if(key==0xf0001077ULL&&i.values[10]>4)throw std::invalid_argument("FP8 rounding mode must be resolved legal architectural frm");
}
m.reset=i.values[0];
m.io_dis_valid=i.values[1];
m.io_dis_bits_bits=i.values[2];
m.io_dis_bits_vconfig_vl=i.values[3];
m.io_dis_bits_vconfig_vtype_tm=i.values[4];
m.io_dis_bits_vconfig_vtype_tk=i.values[5];
m.io_dis_bits_vconfig_vtype_altfmt=i.values[6];
m.io_dis_bits_vconfig_vtype_vsew=i.values[7];
m.io_dis_bits_rs1_data=i.values[8];
m.io_dis_bits_vat=i.values[9];
m.io_dis_bits_rm=i.values[10];
m.io_dis_bits_emul=i.values[11];
m.io_older_writes=i.values[12];
m.io_older_reads=i.values[13];
m.io_vat_head=i.values[14];
m.io_rvs1_ready=i.values[15];
m.io_rvs2_ready=i.values[16];
m.io_pipe_write_req_available=i.values[17];
m.clock=0;m.eval();impl_->evaluated=true;
}
SequencerOutputs IrisOPUSequencer::sample()const{
if(!impl_->evaluated)throw std::logic_error("OPU sample requires fresh evaluate");const auto&m=*impl_->model;SequencerOutputs o{};
o.values[0]=m.io_dis_ready;o.defined[0]=impl_->reset_seen&&(true);
o.values[1]=m.io_seq_hazard_valid;o.defined[1]=impl_->reset_seen&&(true);
o.values[2]=m.io_seq_hazard_bits_vat;o.defined[2]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[3]=m.io_seq_hazard_bits_rintent;o.defined[3]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[4]=m.io_seq_hazard_bits_wintent;o.defined[4]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[5]=m.io_vat;o.defined[5]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[6]=m.io_busy;o.defined[6]=impl_->reset_seen&&(true);
o.values[7]=m.io_iss_valid;o.defined[7]=impl_->reset_seen&&(true);
o.values[8]=m.io_iss_bits_mrf_idx_0;o.defined[8]=impl_->reset_seen&&(true);
o.values[9]=m.io_iss_bits_mrf_idx_1;o.defined[9]=impl_->reset_seen&&(true);
o.values[10]=m.io_iss_bits_mrf_idx_2;o.defined[10]=impl_->reset_seen&&(true);
o.values[11]=m.io_iss_bits_mrf_idx_3;o.defined[11]=impl_->reset_seen&&(true);
o.values[12]=m.io_iss_bits_row_idx_0;o.defined[12]=impl_->reset_seen&&(true);
o.values[13]=m.io_iss_bits_row_idx_1;o.defined[13]=impl_->reset_seen&&(true);
o.values[14]=m.io_iss_bits_row_idx_2;o.defined[14]=impl_->reset_seen&&(true);
o.values[15]=m.io_iss_bits_row_idx_3;o.defined[15]=impl_->reset_seen&&(true);
o.values[16]=m.io_iss_bits_col_idx_0;o.defined[16]=impl_->reset_seen&&(true);
o.values[17]=m.io_iss_bits_col_idx_1;o.defined[17]=impl_->reset_seen&&(true);
o.values[18]=m.io_iss_bits_col_idx_2;o.defined[18]=impl_->reset_seen&&(true);
o.values[19]=m.io_iss_bits_col_idx_3;o.defined[19]=impl_->reset_seen&&(true);
o.values[20]=m.io_iss_bits_macc_0;o.defined[20]=impl_->reset_seen&&(true);
o.values[21]=m.io_iss_bits_macc_1;o.defined[21]=impl_->reset_seen&&(true);
o.values[22]=m.io_iss_bits_macc_2;o.defined[22]=impl_->reset_seen&&(true);
o.values[23]=m.io_iss_bits_macc_3;o.defined[23]=impl_->reset_seen&&(true);
o.values[24]=m.io_iss_bits_zero_0;o.defined[24]=impl_->reset_seen&&(true);
o.values[25]=m.io_iss_bits_zero_1;o.defined[25]=impl_->reset_seen&&(true);
o.values[26]=m.io_iss_bits_zero_2;o.defined[26]=impl_->reset_seen&&(true);
o.values[27]=m.io_iss_bits_zero_3;o.defined[27]=impl_->reset_seen&&(true);
o.values[28]=m.io_iss_bits_shift_1;o.defined[28]=impl_->reset_seen&&(true);
o.values[29]=m.io_iss_bits_shift_2;o.defined[29]=impl_->reset_seen&&(true);
o.values[30]=m.io_iss_bits_shift_3;o.defined[30]=impl_->reset_seen&&(true);
o.values[31]=m.io_iss_bits_mvin_0;o.defined[31]=impl_->reset_seen&&(true);
o.values[32]=m.io_iss_bits_mvin_1;o.defined[32]=impl_->reset_seen&&(true);
o.values[33]=m.io_iss_bits_mvin_2;o.defined[33]=impl_->reset_seen&&(true);
o.values[34]=m.io_iss_bits_mvin_3;o.defined[34]=impl_->reset_seen&&(true);
o.values[35]=m.io_iss_bits_row_en_0_0;o.defined[35]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[36]=m.io_iss_bits_row_en_0_1;o.defined[36]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[37]=m.io_iss_bits_row_en_0_2;o.defined[37]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[38]=m.io_iss_bits_row_en_0_3;o.defined[38]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[39]=m.io_iss_bits_row_en_1_0;o.defined[39]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[40]=m.io_iss_bits_row_en_1_1;o.defined[40]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[41]=m.io_iss_bits_row_en_1_2;o.defined[41]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[42]=m.io_iss_bits_row_en_1_3;o.defined[42]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[43]=m.io_iss_bits_row_en_2_0;o.defined[43]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[44]=m.io_iss_bits_row_en_2_1;o.defined[44]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[45]=m.io_iss_bits_row_en_2_2;o.defined[45]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[46]=m.io_iss_bits_row_en_2_3;o.defined[46]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[47]=m.io_iss_bits_row_en_3_0;o.defined[47]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[48]=m.io_iss_bits_row_en_3_1;o.defined[48]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[49]=m.io_iss_bits_row_en_3_2;o.defined[49]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[50]=m.io_iss_bits_row_en_3_3;o.defined[50]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[51]=m.io_iss_bits_mvin_col_0;o.defined[51]=impl_->reset_seen&&(true);
o.values[52]=m.io_iss_bits_mvin_col_1;o.defined[52]=impl_->reset_seen&&(true);
o.values[53]=m.io_iss_bits_mvin_col_2;o.defined[53]=impl_->reset_seen&&(true);
o.values[54]=m.io_iss_bits_mvin_col_3;o.defined[54]=impl_->reset_seen&&(true);
o.values[55]=m.io_iss_bits_col_en_0_0;o.defined[55]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[56]=m.io_iss_bits_col_en_0_1;o.defined[56]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[57]=m.io_iss_bits_col_en_0_2;o.defined[57]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[58]=m.io_iss_bits_col_en_0_3;o.defined[58]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[59]=m.io_iss_bits_col_en_1_0;o.defined[59]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[60]=m.io_iss_bits_col_en_1_1;o.defined[60]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[61]=m.io_iss_bits_col_en_1_2;o.defined[61]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[62]=m.io_iss_bits_col_en_1_3;o.defined[62]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[63]=m.io_iss_bits_col_en_2_0;o.defined[63]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[64]=m.io_iss_bits_col_en_2_1;o.defined[64]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[65]=m.io_iss_bits_col_en_2_2;o.defined[65]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[66]=m.io_iss_bits_col_en_2_3;o.defined[66]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[67]=m.io_iss_bits_col_en_3_0;o.defined[67]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[68]=m.io_iss_bits_col_en_3_1;o.defined[68]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[69]=m.io_iss_bits_col_en_3_2;o.defined[69]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[70]=m.io_iss_bits_col_en_3_3;o.defined[70]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[71]=m.io_iss_bits_mv_en_0;o.defined[71]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[72]=m.io_iss_bits_mv_en_1;o.defined[72]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[73]=m.io_iss_bits_mv_en_2;o.defined[73]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[74]=m.io_iss_bits_mv_en_3;o.defined[74]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[75]=m.io_iss_bits_signed_l;o.defined[75]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[76]=m.io_iss_bits_signed_t;o.defined[76]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[77]=m.io_iss_bits_fp8;o.defined[77]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[78]=m.io_iss_bits_e5m2_l;o.defined[78]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[79]=m.io_iss_bits_e5m2_t;o.defined[79]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[80]=m.io_iss_bits_rm;o.defined[80]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[81]=m.io_rvs1_valid;o.defined[81]=impl_->reset_seen&&(true);
o.values[82]=m.io_rvs1_bits_eg;o.defined[82]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[83]=m.io_rvs1_bits_oldest;o.defined[83]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[84]=m.io_rvs2_valid;o.defined[84]=impl_->reset_seen&&(true);
o.values[85]=m.io_rvs2_bits_eg;o.defined[85]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[86]=m.io_rvs2_bits_oldest;o.defined[86]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[87]=m.io_pipe_write_req_request;o.defined[87]=impl_->reset_seen&&(true);
o.values[88]=m.io_pipe_write_req_fire;o.defined[88]=impl_->reset_seen&&(true);
o.values[89]=m.io_pipe_write_req_bank_sel;o.defined[89]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[90]=m.io_pipe_write_req_pipe_depth;o.defined[90]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[91]=m.io_pipe_write_req_oldest;o.defined[91]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[92]=m.io_tail;o.defined[92]=impl_->reset_seen&&(impl_->dispatch_seen);
o.values[93]=m.io_write_valid;o.defined[93]=impl_->reset_seen&&(true);
o.values[94]=m.io_write_bits;o.defined[94]=impl_->reset_seen&&(bool(m.io_write_valid));
o.values[95]=(std::uint64_t{m.io_write_mask[0]}|(std::uint64_t{m.io_write_mask[1]}<<32));o.defined[95]=impl_->reset_seen&&(bool(m.io_write_valid));
o.values[96]=(std::uint64_t{m.io_write_mask[2]}|(std::uint64_t{m.io_write_mask[3]}<<32));o.defined[96]=impl_->reset_seen&&(bool(m.io_write_valid));
o.values[97]=m.io_write_reg_enable;o.defined[97]=impl_->reset_seen&&(true);
o.values[98]=m.io_wsboard;o.defined[98]=impl_->reset_seen&&(true);
return o;
}
void IrisOPUSequencer::commit(){
 if(!impl_->evaluated)throw std::logic_error("OPU commit requires fresh evaluate");auto&m=*impl_->model;
 if(m.reset){impl_->reset_seen=true;impl_->dispatch_seen=false;}
 else if(m.io_dis_ready&&m.io_dis_valid)impl_->dispatch_seen=true;
 m.clock=1;m.eval();m.clock=0;m.eval();++impl_->edge_count;impl_->evaluated=false;
}
SequencerOutputs IrisOPUSequencer::step(const SequencerInputs&i){evaluate(i);auto o=sample();commit();return o;}
std::uint64_t IrisOPUSequencer::edges()const{return impl_->edge_count;}
const char* IrisOPUSequencer::source_identity(){return IRIS_OPU_SEQUENCER_SOURCE_ID;}
std::span<const SequencerField> IrisOPUSequencer::input_fields(){static constexpr SequencerField f[]={{"reset",1},{"io_dis_valid",1},{"io_dis_bits_bits",32},{"io_dis_bits_vconfig_vl",9},{"io_dis_bits_vconfig_vtype_tm",14},{"io_dis_bits_vconfig_vtype_tk",3},{"io_dis_bits_vconfig_vtype_altfmt",1},{"io_dis_bits_vconfig_vtype_vsew",3},{"io_dis_bits_rs1_data",64},{"io_dis_bits_vat",5},{"io_dis_bits_rm",3},{"io_dis_bits_emul",2},{"io_older_writes",64},{"io_older_reads",64},{"io_vat_head",5},{"io_rvs1_ready",1},{"io_rvs2_ready",1},{"io_pipe_write_req_available",1}};return f;}
std::span<const SequencerField> IrisOPUSequencer::output_fields(){static constexpr SequencerField f[]={{"io_dis_ready",1},{"io_seq_hazard_valid",1},{"io_seq_hazard_bits_vat",5},{"io_seq_hazard_bits_rintent",64},{"io_seq_hazard_bits_wintent",64},{"io_vat",5},{"io_busy",1},{"io_iss_valid",1},{"io_iss_bits_mrf_idx_0",4},{"io_iss_bits_mrf_idx_1",4},{"io_iss_bits_mrf_idx_2",4},{"io_iss_bits_mrf_idx_3",4},{"io_iss_bits_row_idx_0",2},{"io_iss_bits_row_idx_1",2},{"io_iss_bits_row_idx_2",2},{"io_iss_bits_row_idx_3",2},{"io_iss_bits_col_idx_0",2},{"io_iss_bits_col_idx_1",2},{"io_iss_bits_col_idx_2",2},{"io_iss_bits_col_idx_3",2},{"io_iss_bits_macc_0",1},{"io_iss_bits_macc_1",1},{"io_iss_bits_macc_2",1},{"io_iss_bits_macc_3",1},{"io_iss_bits_zero_0",1},{"io_iss_bits_zero_1",1},{"io_iss_bits_zero_2",1},{"io_iss_bits_zero_3",1},{"io_iss_bits_shift_1",1},{"io_iss_bits_shift_2",1},{"io_iss_bits_shift_3",1},{"io_iss_bits_mvin_0",1},{"io_iss_bits_mvin_1",1},{"io_iss_bits_mvin_2",1},{"io_iss_bits_mvin_3",1},{"io_iss_bits_row_en_0_0",1},{"io_iss_bits_row_en_0_1",1},{"io_iss_bits_row_en_0_2",1},{"io_iss_bits_row_en_0_3",1},{"io_iss_bits_row_en_1_0",1},{"io_iss_bits_row_en_1_1",1},{"io_iss_bits_row_en_1_2",1},{"io_iss_bits_row_en_1_3",1},{"io_iss_bits_row_en_2_0",1},{"io_iss_bits_row_en_2_1",1},{"io_iss_bits_row_en_2_2",1},{"io_iss_bits_row_en_2_3",1},{"io_iss_bits_row_en_3_0",1},{"io_iss_bits_row_en_3_1",1},{"io_iss_bits_row_en_3_2",1},{"io_iss_bits_row_en_3_3",1},{"io_iss_bits_mvin_col_0",1},{"io_iss_bits_mvin_col_1",1},{"io_iss_bits_mvin_col_2",1},{"io_iss_bits_mvin_col_3",1},{"io_iss_bits_col_en_0_0",1},{"io_iss_bits_col_en_0_1",1},{"io_iss_bits_col_en_0_2",1},{"io_iss_bits_col_en_0_3",1},{"io_iss_bits_col_en_1_0",1},{"io_iss_bits_col_en_1_1",1},{"io_iss_bits_col_en_1_2",1},{"io_iss_bits_col_en_1_3",1},{"io_iss_bits_col_en_2_0",1},{"io_iss_bits_col_en_2_1",1},{"io_iss_bits_col_en_2_2",1},{"io_iss_bits_col_en_2_3",1},{"io_iss_bits_col_en_3_0",1},{"io_iss_bits_col_en_3_1",1},{"io_iss_bits_col_en_3_2",1},{"io_iss_bits_col_en_3_3",1},{"io_iss_bits_mv_en_0",1},{"io_iss_bits_mv_en_1",1},{"io_iss_bits_mv_en_2",1},{"io_iss_bits_mv_en_3",1},{"io_iss_bits_signed_l",1},{"io_iss_bits_signed_t",1},{"io_iss_bits_fp8",1},{"io_iss_bits_e5m2_l",1},{"io_iss_bits_e5m2_t",1},{"io_iss_bits_rm",3},{"io_rvs1_valid",1},{"io_rvs1_bits_eg",6},{"io_rvs1_bits_oldest",1},{"io_rvs2_valid",1},{"io_rvs2_bits_eg",6},{"io_rvs2_bits_oldest",1},{"io_pipe_write_req_request",1},{"io_pipe_write_req_fire",1},{"io_pipe_write_req_bank_sel",4},{"io_pipe_write_req_pipe_depth",3},{"io_pipe_write_req_oldest",1},{"io_tail",1},{"io_write_valid",1},{"io_write_bits",6},{"io_write_mask",64},{"io_write_mask_hi",64},{"io_write_reg_enable",1},{"io_wsboard",64}};return f;}
}
