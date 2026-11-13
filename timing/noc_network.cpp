#include "noc_network.hpp"
#include "noc_network_identity.hpp"
#include "VNoCNetwork.h"
#include "verilated.h"
#include "verilated_save.h"
#include <algorithm>
#include <fstream>
#include <stdexcept>
namespace iris::noc {
namespace {
class NetworkSnapshotPrefix final : public VerilatedDeserialize {
 std::ifstream file_;bool filled_=false;
 void fill()override{
  if(filled_)throw std::invalid_argument("Network snapshot prefix exhausted");
  file_.read(reinterpret_cast<char*>(m_bufp),bufferSize());auto n=file_.gcount();
  if(n<128)throw std::invalid_argument("Network snapshot prefix truncated");
  std::fill(m_bufp+n,m_bufp+bufferSize(),0);m_cp=m_bufp;m_endp=m_bufp+bufferSize();filled_=true;
 }
 public:
 explicit NetworkSnapshotPrefix(const std::filesystem::path& p):file_(p,std::ios::binary){
  if(!file_)throw std::invalid_argument("Network snapshot unavailable");m_filename=p.string();header();
  std::uint64_t magic=0;std::uint32_t size=0;*this>>magic>>size;
  if(magic!=0x495249534e455431ULL||size!=64)throw std::invalid_argument("Network snapshot source identity mismatch");
  std::string id(size,'\0');read(id.data(),size);if(id!=IRIS_NETWORK_SOURCE_ID)throw std::invalid_argument("Network snapshot source identity mismatch");
 }
};
}
struct IrisNoCNetwork::Impl {
 std::unique_ptr<VerilatedContext> context;
 std::unique_ptr<VNoCNetwork> model;
 std::uint64_t edge_count=0;
 bool evaluated=false;
 explicit Impl(std::uint32_t seed):context(std::make_unique<VerilatedContext>()){
  context->threads(1);context->randSeed(seed);context->randReset(2);
  const char* args[]={"iris-source-network","+noc_util_sample_rate=0"};context->commandArgs(2,args);
  model=std::make_unique<VNoCNetwork>(context.get());model->clock=0;
 }
};
IrisNoCNetwork::IrisNoCNetwork(std::uint32_t seed):impl_(std::make_unique<Impl>(seed)){}
IrisNoCNetwork::~IrisNoCNetwork()=default;
IrisNoCNetwork::IrisNoCNetwork(IrisNoCNetwork&&)noexcept=default;
IrisNoCNetwork& IrisNoCNetwork::operator=(IrisNoCNetwork&&)noexcept=default;
void IrisNoCNetwork::evaluate(const NetworkInputs& i){
 impl_->evaluated=false;auto& m=*impl_->model;m.clock=0;
// BEGIN GENERATED INPUT MAP
if(i.values[0]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _cbus_auto_bus_xing_in_a_ready");
if(i.values[1]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _cbus_auto_bus_xing_in_d_bits_corrupt");
if(i.values[3]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _cbus_auto_bus_xing_in_d_bits_denied");
if(i.values[4]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _cbus_auto_bus_xing_in_d_bits_opcode");
if(i.values[5]>=4ULL)throw std::invalid_argument("Physical NoC field exceeds width: _cbus_auto_bus_xing_in_d_bits_param");
if(i.values[6]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _cbus_auto_bus_xing_in_d_bits_sink");
if(i.values[7]>=16ULL)throw std::invalid_argument("Physical NoC field exceeds width: _cbus_auto_bus_xing_in_d_bits_size");
if(i.values[8]>=1024ULL)throw std::invalid_argument("Physical NoC field exceeds width: _cbus_auto_bus_xing_in_d_bits_source");
if(i.values[9]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _cbus_auto_bus_xing_in_d_valid");
if(i.values[10]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_0_a_ready");
if(i.values[11]>=8589934592ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_0_b_bits_address");
if(i.values[12]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_0_b_bits_corrupt");
if(i.values[14]>=256ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_0_b_bits_mask");
if(i.values[15]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_0_b_bits_opcode");
if(i.values[16]>=4ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_0_b_bits_param");
if(i.values[17]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_0_b_bits_size");
if(i.values[18]>=1024ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_0_b_bits_source");
if(i.values[19]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_0_b_valid");
if(i.values[20]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_0_c_ready");
if(i.values[21]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_0_d_bits_corrupt");
if(i.values[23]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_0_d_bits_denied");
if(i.values[24]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_0_d_bits_opcode");
if(i.values[25]>=4ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_0_d_bits_param");
if(i.values[26]>=4ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_0_d_bits_sink");
if(i.values[27]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_0_d_bits_size");
if(i.values[28]>=1024ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_0_d_bits_source");
if(i.values[29]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_0_d_valid");
if(i.values[30]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_0_e_ready");
if(i.values[31]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_1_a_ready");
if(i.values[32]>=8589934592ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_1_b_bits_address");
if(i.values[33]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_1_b_bits_corrupt");
if(i.values[35]>=256ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_1_b_bits_mask");
if(i.values[36]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_1_b_bits_opcode");
if(i.values[37]>=4ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_1_b_bits_param");
if(i.values[38]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_1_b_bits_size");
if(i.values[39]>=1024ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_1_b_bits_source");
if(i.values[40]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_1_b_valid");
if(i.values[41]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_1_c_ready");
if(i.values[42]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_1_d_bits_corrupt");
if(i.values[44]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_1_d_bits_denied");
if(i.values[45]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_1_d_bits_opcode");
if(i.values[46]>=4ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_1_d_bits_param");
if(i.values[47]>=4ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_1_d_bits_sink");
if(i.values[48]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_1_d_bits_size");
if(i.values[49]>=1024ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_1_d_bits_source");
if(i.values[50]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_1_d_valid");
if(i.values[51]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_1_e_ready");
if(i.values[52]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_2_a_ready");
if(i.values[53]>=8589934592ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_2_b_bits_address");
if(i.values[54]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_2_b_bits_corrupt");
if(i.values[56]>=256ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_2_b_bits_mask");
if(i.values[57]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_2_b_bits_opcode");
if(i.values[58]>=4ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_2_b_bits_param");
if(i.values[59]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_2_b_bits_size");
if(i.values[60]>=1024ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_2_b_bits_source");
if(i.values[61]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_2_b_valid");
if(i.values[62]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_2_c_ready");
if(i.values[63]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_2_d_bits_corrupt");
if(i.values[65]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_2_d_bits_denied");
if(i.values[66]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_2_d_bits_opcode");
if(i.values[67]>=4ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_2_d_bits_param");
if(i.values[68]>=4ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_2_d_bits_sink");
if(i.values[69]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_2_d_bits_size");
if(i.values[70]>=1024ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_2_d_bits_source");
if(i.values[71]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_2_d_valid");
if(i.values[72]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_2_e_ready");
if(i.values[73]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_3_a_ready");
if(i.values[74]>=8589934592ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_3_b_bits_address");
if(i.values[75]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_3_b_bits_corrupt");
if(i.values[77]>=256ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_3_b_bits_mask");
if(i.values[78]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_3_b_bits_opcode");
if(i.values[79]>=4ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_3_b_bits_param");
if(i.values[80]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_3_b_bits_size");
if(i.values[81]>=1024ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_3_b_bits_source");
if(i.values[82]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_3_b_valid");
if(i.values[83]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_3_c_ready");
if(i.values[84]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_3_d_bits_corrupt");
if(i.values[86]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_3_d_bits_denied");
if(i.values[87]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_3_d_bits_opcode");
if(i.values[88]>=4ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_3_d_bits_param");
if(i.values[89]>=4ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_3_d_bits_sink");
if(i.values[90]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_3_d_bits_size");
if(i.values[91]>=1024ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_3_d_bits_source");
if(i.values[92]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_3_d_valid");
if(i.values[93]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _coh_wrapper_auto_coherent_jbar_anon_in_3_e_ready");
if(i.values[94]>=34359738368ULL)throw std::invalid_argument("Physical NoC field exceeds width: _fbus_auto_bus_xing_out_a_bits_address");
if(i.values[95]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _fbus_auto_bus_xing_out_a_bits_corrupt");
if(i.values[97]>=256ULL)throw std::invalid_argument("Physical NoC field exceeds width: _fbus_auto_bus_xing_out_a_bits_mask");
if(i.values[98]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _fbus_auto_bus_xing_out_a_bits_opcode");
if(i.values[99]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _fbus_auto_bus_xing_out_a_bits_param");
if(i.values[100]>=16ULL)throw std::invalid_argument("Physical NoC field exceeds width: _fbus_auto_bus_xing_out_a_bits_size");
if(i.values[101]>=512ULL)throw std::invalid_argument("Physical NoC field exceeds width: _fbus_auto_bus_xing_out_a_bits_source");
if(i.values[102]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _fbus_auto_bus_xing_out_a_valid");
if(i.values[103]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _fbus_auto_bus_xing_out_d_ready");
if(i.values[104]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_buffer_1_auto_in_a_ready");
if(i.values[105]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_buffer_1_auto_in_d_bits_corrupt");
if(i.values[107]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_buffer_1_auto_in_d_bits_denied");
if(i.values[108]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_buffer_1_auto_in_d_bits_opcode");
if(i.values[109]>=4ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_buffer_1_auto_in_d_bits_param");
if(i.values[110]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_buffer_1_auto_in_d_bits_sink");
if(i.values[111]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_buffer_1_auto_in_d_bits_size");
if(i.values[112]>=1024ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_buffer_1_auto_in_d_bits_source");
if(i.values[113]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_buffer_1_auto_in_d_valid");
if(i.values[114]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_buffer_auto_in_a_ready");
if(i.values[115]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_buffer_auto_in_d_bits_corrupt");
if(i.values[117]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_buffer_auto_in_d_bits_denied");
if(i.values[118]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_buffer_auto_in_d_bits_opcode");
if(i.values[119]>=4ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_buffer_auto_in_d_bits_param");
if(i.values[120]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_buffer_auto_in_d_bits_sink");
if(i.values[121]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_buffer_auto_in_d_bits_size");
if(i.values[122]>=1024ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_buffer_auto_in_d_bits_source");
if(i.values[123]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_buffer_auto_in_d_valid");
if(i.values[124]>=34359738368ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_from_rockettile_auto_tl_out_a_bits_address");
if(i.values[125]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_from_rockettile_auto_tl_out_a_bits_corrupt");
if(i.values[127]>=256ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_from_rockettile_auto_tl_out_a_bits_mask");
if(i.values[128]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_from_rockettile_auto_tl_out_a_bits_opcode");
if(i.values[129]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_from_rockettile_auto_tl_out_a_bits_param");
if(i.values[130]>=16ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_from_rockettile_auto_tl_out_a_bits_size");
if(i.values[131]>=128ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_from_rockettile_auto_tl_out_a_bits_source");
if(i.values[132]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_from_rockettile_auto_tl_out_a_valid");
if(i.values[133]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_from_rockettile_auto_tl_out_b_ready");
if(i.values[134]>=34359738368ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_from_rockettile_auto_tl_out_c_bits_address");
if(i.values[135]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_from_rockettile_auto_tl_out_c_bits_corrupt");
if(i.values[137]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_from_rockettile_auto_tl_out_c_bits_opcode");
if(i.values[138]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_from_rockettile_auto_tl_out_c_bits_param");
if(i.values[139]>=16ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_from_rockettile_auto_tl_out_c_bits_size");
if(i.values[140]>=128ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_from_rockettile_auto_tl_out_c_bits_source");
if(i.values[141]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_from_rockettile_auto_tl_out_c_valid");
if(i.values[142]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_from_rockettile_auto_tl_out_d_ready");
if(i.values[143]>=16ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_from_rockettile_auto_tl_out_e_bits_sink");
if(i.values[144]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_from_rockettile_auto_tl_out_e_valid");
if(i.values[145]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_to_shuttle_tile_1_auto_tl_in_a_ready");
if(i.values[146]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_to_shuttle_tile_1_auto_tl_in_d_bits_corrupt");
if(i.values[148]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_to_shuttle_tile_1_auto_tl_in_d_bits_denied");
if(i.values[149]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_to_shuttle_tile_1_auto_tl_in_d_bits_opcode");
if(i.values[150]>=4ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_to_shuttle_tile_1_auto_tl_in_d_bits_param");
if(i.values[151]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_to_shuttle_tile_1_auto_tl_in_d_bits_sink");
if(i.values[152]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_to_shuttle_tile_1_auto_tl_in_d_bits_size");
if(i.values[153]>=1024ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_to_shuttle_tile_1_auto_tl_in_d_bits_source");
if(i.values[154]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_to_shuttle_tile_1_auto_tl_in_d_valid");
if(i.values[155]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_to_shuttle_tile_auto_tl_in_a_ready");
if(i.values[156]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_to_shuttle_tile_auto_tl_in_d_bits_corrupt");
if(i.values[158]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_to_shuttle_tile_auto_tl_in_d_bits_denied");
if(i.values[159]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_to_shuttle_tile_auto_tl_in_d_bits_opcode");
if(i.values[160]>=4ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_to_shuttle_tile_auto_tl_in_d_bits_param");
if(i.values[161]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_to_shuttle_tile_auto_tl_in_d_bits_sink");
if(i.values[162]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_to_shuttle_tile_auto_tl_in_d_bits_size");
if(i.values[163]>=1024ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_to_shuttle_tile_auto_tl_in_d_bits_source");
if(i.values[164]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_coupler_to_shuttle_tile_auto_tl_in_d_valid");
if(i.values[165]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _sbus_fixedClockNode_auto_anon_out_0_reset");
if(i.values[166]>=34359738368ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_1_auto_tl_master_clock_xing_out_a_bits_address");
if(i.values[167]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_1_auto_tl_master_clock_xing_out_a_bits_corrupt");
if(i.values[169]>=256ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_1_auto_tl_master_clock_xing_out_a_bits_mask");
if(i.values[170]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_1_auto_tl_master_clock_xing_out_a_bits_opcode");
if(i.values[171]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_1_auto_tl_master_clock_xing_out_a_bits_param");
if(i.values[172]>=16ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_1_auto_tl_master_clock_xing_out_a_bits_size");
if(i.values[173]>=64ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_1_auto_tl_master_clock_xing_out_a_bits_source");
if(i.values[174]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_1_auto_tl_master_clock_xing_out_a_valid");
if(i.values[175]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_1_auto_tl_master_clock_xing_out_b_ready");
if(i.values[176]>=34359738368ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_1_auto_tl_master_clock_xing_out_c_bits_address");
if(i.values[177]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_1_auto_tl_master_clock_xing_out_c_bits_corrupt");
if(i.values[179]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_1_auto_tl_master_clock_xing_out_c_bits_opcode");
if(i.values[180]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_1_auto_tl_master_clock_xing_out_c_bits_param");
if(i.values[181]>=16ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_1_auto_tl_master_clock_xing_out_c_bits_size");
if(i.values[182]>=64ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_1_auto_tl_master_clock_xing_out_c_bits_source");
if(i.values[183]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_1_auto_tl_master_clock_xing_out_c_valid");
if(i.values[184]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_1_auto_tl_master_clock_xing_out_d_ready");
if(i.values[185]>=16ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_1_auto_tl_master_clock_xing_out_e_bits_sink");
if(i.values[186]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_1_auto_tl_master_clock_xing_out_e_valid");
if(i.values[187]>=34359738368ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_auto_tl_master_clock_xing_out_a_bits_address");
if(i.values[188]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_auto_tl_master_clock_xing_out_a_bits_corrupt");
if(i.values[190]>=256ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_auto_tl_master_clock_xing_out_a_bits_mask");
if(i.values[191]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_auto_tl_master_clock_xing_out_a_bits_opcode");
if(i.values[192]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_auto_tl_master_clock_xing_out_a_bits_param");
if(i.values[193]>=16ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_auto_tl_master_clock_xing_out_a_bits_size");
if(i.values[194]>=64ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_auto_tl_master_clock_xing_out_a_bits_source");
if(i.values[195]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_auto_tl_master_clock_xing_out_a_valid");
if(i.values[196]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_auto_tl_master_clock_xing_out_b_ready");
if(i.values[197]>=34359738368ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_auto_tl_master_clock_xing_out_c_bits_address");
if(i.values[198]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_auto_tl_master_clock_xing_out_c_bits_corrupt");
if(i.values[200]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_auto_tl_master_clock_xing_out_c_bits_opcode");
if(i.values[201]>=8ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_auto_tl_master_clock_xing_out_c_bits_param");
if(i.values[202]>=16ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_auto_tl_master_clock_xing_out_c_bits_size");
if(i.values[203]>=64ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_auto_tl_master_clock_xing_out_c_bits_source");
if(i.values[204]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_auto_tl_master_clock_xing_out_c_valid");
if(i.values[205]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_auto_tl_master_clock_xing_out_d_ready");
if(i.values[206]>=16ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_auto_tl_master_clock_xing_out_e_bits_sink");
if(i.values[207]>=2ULL)throw std::invalid_argument("Physical NoC field exceeds width: _tile_prci_domain_auto_tl_master_clock_xing_out_e_valid");
m.i_0=i.values[0];
m.i_1=i.values[1];
m.i_2=i.values[2];
m.i_3=i.values[3];
m.i_4=i.values[4];
m.i_5=i.values[5];
m.i_6=i.values[6];
m.i_7=i.values[7];
m.i_8=i.values[8];
m.i_9=i.values[9];
m.i_10=i.values[10];
m.i_11=i.values[11];
m.i_12=i.values[12];
m.i_13=i.values[13];
m.i_14=i.values[14];
m.i_15=i.values[15];
m.i_16=i.values[16];
m.i_17=i.values[17];
m.i_18=i.values[18];
m.i_19=i.values[19];
m.i_20=i.values[20];
m.i_21=i.values[21];
m.i_22=i.values[22];
m.i_23=i.values[23];
m.i_24=i.values[24];
m.i_25=i.values[25];
m.i_26=i.values[26];
m.i_27=i.values[27];
m.i_28=i.values[28];
m.i_29=i.values[29];
m.i_30=i.values[30];
m.i_31=i.values[31];
m.i_32=i.values[32];
m.i_33=i.values[33];
m.i_34=i.values[34];
m.i_35=i.values[35];
m.i_36=i.values[36];
m.i_37=i.values[37];
m.i_38=i.values[38];
m.i_39=i.values[39];
m.i_40=i.values[40];
m.i_41=i.values[41];
m.i_42=i.values[42];
m.i_43=i.values[43];
m.i_44=i.values[44];
m.i_45=i.values[45];
m.i_46=i.values[46];
m.i_47=i.values[47];
m.i_48=i.values[48];
m.i_49=i.values[49];
m.i_50=i.values[50];
m.i_51=i.values[51];
m.i_52=i.values[52];
m.i_53=i.values[53];
m.i_54=i.values[54];
m.i_55=i.values[55];
m.i_56=i.values[56];
m.i_57=i.values[57];
m.i_58=i.values[58];
m.i_59=i.values[59];
m.i_60=i.values[60];
m.i_61=i.values[61];
m.i_62=i.values[62];
m.i_63=i.values[63];
m.i_64=i.values[64];
m.i_65=i.values[65];
m.i_66=i.values[66];
m.i_67=i.values[67];
m.i_68=i.values[68];
m.i_69=i.values[69];
m.i_70=i.values[70];
m.i_71=i.values[71];
m.i_72=i.values[72];
m.i_73=i.values[73];
m.i_74=i.values[74];
m.i_75=i.values[75];
m.i_76=i.values[76];
m.i_77=i.values[77];
m.i_78=i.values[78];
m.i_79=i.values[79];
m.i_80=i.values[80];
m.i_81=i.values[81];
m.i_82=i.values[82];
m.i_83=i.values[83];
m.i_84=i.values[84];
m.i_85=i.values[85];
m.i_86=i.values[86];
m.i_87=i.values[87];
m.i_88=i.values[88];
m.i_89=i.values[89];
m.i_90=i.values[90];
m.i_91=i.values[91];
m.i_92=i.values[92];
m.i_93=i.values[93];
m.i_94=i.values[94];
m.i_95=i.values[95];
m.i_96=i.values[96];
m.i_97=i.values[97];
m.i_98=i.values[98];
m.i_99=i.values[99];
m.i_100=i.values[100];
m.i_101=i.values[101];
m.i_102=i.values[102];
m.i_103=i.values[103];
m.i_104=i.values[104];
m.i_105=i.values[105];
m.i_106=i.values[106];
m.i_107=i.values[107];
m.i_108=i.values[108];
m.i_109=i.values[109];
m.i_110=i.values[110];
m.i_111=i.values[111];
m.i_112=i.values[112];
m.i_113=i.values[113];
m.i_114=i.values[114];
m.i_115=i.values[115];
m.i_116=i.values[116];
m.i_117=i.values[117];
m.i_118=i.values[118];
m.i_119=i.values[119];
m.i_120=i.values[120];
m.i_121=i.values[121];
m.i_122=i.values[122];
m.i_123=i.values[123];
m.i_124=i.values[124];
m.i_125=i.values[125];
m.i_126=i.values[126];
m.i_127=i.values[127];
m.i_128=i.values[128];
m.i_129=i.values[129];
m.i_130=i.values[130];
m.i_131=i.values[131];
m.i_132=i.values[132];
m.i_133=i.values[133];
m.i_134=i.values[134];
m.i_135=i.values[135];
m.i_136=i.values[136];
m.i_137=i.values[137];
m.i_138=i.values[138];
m.i_139=i.values[139];
m.i_140=i.values[140];
m.i_141=i.values[141];
m.i_142=i.values[142];
m.i_143=i.values[143];
m.i_144=i.values[144];
m.i_145=i.values[145];
m.i_146=i.values[146];
m.i_147=i.values[147];
m.i_148=i.values[148];
m.i_149=i.values[149];
m.i_150=i.values[150];
m.i_151=i.values[151];
m.i_152=i.values[152];
m.i_153=i.values[153];
m.i_154=i.values[154];
m.i_155=i.values[155];
m.i_156=i.values[156];
m.i_157=i.values[157];
m.i_158=i.values[158];
m.i_159=i.values[159];
m.i_160=i.values[160];
m.i_161=i.values[161];
m.i_162=i.values[162];
m.i_163=i.values[163];
m.i_164=i.values[164];
m.i_165=i.values[165];
m.i_166=i.values[166];
m.i_167=i.values[167];
m.i_168=i.values[168];
m.i_169=i.values[169];
m.i_170=i.values[170];
m.i_171=i.values[171];
m.i_172=i.values[172];
m.i_173=i.values[173];
m.i_174=i.values[174];
m.i_175=i.values[175];
m.i_176=i.values[176];
m.i_177=i.values[177];
m.i_178=i.values[178];
m.i_179=i.values[179];
m.i_180=i.values[180];
m.i_181=i.values[181];
m.i_182=i.values[182];
m.i_183=i.values[183];
m.i_184=i.values[184];
m.i_185=i.values[185];
m.i_186=i.values[186];
m.i_187=i.values[187];
m.i_188=i.values[188];
m.i_189=i.values[189];
m.i_190=i.values[190];
m.i_191=i.values[191];
m.i_192=i.values[192];
m.i_193=i.values[193];
m.i_194=i.values[194];
m.i_195=i.values[195];
m.i_196=i.values[196];
m.i_197=i.values[197];
m.i_198=i.values[198];
m.i_199=i.values[199];
m.i_200=i.values[200];
m.i_201=i.values[201];
m.i_202=i.values[202];
m.i_203=i.values[203];
m.i_204=i.values[204];
m.i_205=i.values[205];
m.i_206=i.values[206];
m.i_207=i.values[207];
m.eval();impl_->evaluated=true;
}
NetworkOutputs IrisNoCNetwork::sample()const{
if(!impl_->evaluated)throw std::logic_error("Network sample requires evaluate in this edge");
const auto &m=*impl_->model;NetworkOutputs o{};
o.values[0]=m.o_0;
o.values[1]=m.o_1;
o.values[2]=m.o_2;
o.values[3]=m.o_3;
o.values[4]=m.o_4;
o.values[5]=m.o_5;
o.values[6]=m.o_6;
o.values[7]=m.o_7;
o.values[8]=m.o_8;
o.values[9]=m.o_9;
o.values[10]=m.o_10;
o.values[11]=m.o_11;
o.values[12]=m.o_12;
o.values[13]=m.o_13;
o.values[14]=m.o_14;
o.values[15]=m.o_15;
o.values[16]=m.o_16;
o.values[17]=m.o_17;
o.values[18]=m.o_18;
o.values[19]=m.o_19;
o.values[20]=m.o_20;
o.values[21]=m.o_21;
o.values[22]=m.o_22;
o.values[23]=m.o_23;
o.values[24]=m.o_24;
o.values[25]=m.o_25;
o.values[26]=m.o_26;
o.values[27]=m.o_27;
o.values[28]=m.o_28;
o.values[29]=m.o_29;
o.values[30]=m.o_30;
o.values[31]=m.o_31;
o.values[32]=m.o_32;
o.values[33]=m.o_33;
o.values[34]=m.o_34;
o.values[35]=m.o_35;
o.values[36]=m.o_36;
o.values[37]=m.o_37;
o.values[38]=m.o_38;
o.values[39]=m.o_39;
o.values[40]=m.o_40;
o.values[41]=m.o_41;
o.values[42]=m.o_42;
o.values[43]=m.o_43;
o.values[44]=m.o_44;
o.values[45]=m.o_45;
o.values[46]=m.o_46;
o.values[47]=m.o_47;
o.values[48]=m.o_48;
o.values[49]=m.o_49;
o.values[50]=m.o_50;
o.values[51]=m.o_51;
o.values[52]=m.o_52;
o.values[53]=m.o_53;
o.values[54]=m.o_54;
o.values[55]=m.o_55;
o.values[56]=m.o_56;
o.values[57]=m.o_57;
o.values[58]=m.o_58;
o.values[59]=m.o_59;
o.values[60]=m.o_60;
o.values[61]=m.o_61;
o.values[62]=m.o_62;
o.values[63]=m.o_63;
o.values[64]=m.o_64;
o.values[65]=m.o_65;
o.values[66]=m.o_66;
o.values[67]=m.o_67;
o.values[68]=m.o_68;
o.values[69]=m.o_69;
o.values[70]=m.o_70;
o.values[71]=m.o_71;
o.values[72]=m.o_72;
o.values[73]=m.o_73;
o.values[74]=m.o_74;
o.values[75]=m.o_75;
o.values[76]=m.o_76;
o.values[77]=m.o_77;
o.values[78]=m.o_78;
o.values[79]=m.o_79;
o.values[80]=m.o_80;
o.values[81]=m.o_81;
o.values[82]=m.o_82;
o.values[83]=m.o_83;
o.values[84]=m.o_84;
o.values[85]=m.o_85;
o.values[86]=m.o_86;
o.values[87]=m.o_87;
o.values[88]=m.o_88;
o.values[89]=m.o_89;
o.values[90]=m.o_90;
o.values[91]=m.o_91;
o.values[92]=m.o_92;
o.values[93]=m.o_93;
o.values[94]=m.o_94;
o.values[95]=m.o_95;
o.values[96]=m.o_96;
o.values[97]=m.o_97;
o.values[98]=m.o_98;
o.values[99]=m.o_99;
o.values[100]=m.o_100;
o.values[101]=m.o_101;
o.values[102]=m.o_102;
o.values[103]=m.o_103;
o.values[104]=m.o_104;
o.values[105]=m.o_105;
o.values[106]=m.o_106;
o.values[107]=m.o_107;
o.values[108]=m.o_108;
o.values[109]=m.o_109;
o.values[110]=m.o_110;
o.values[111]=m.o_111;
o.values[112]=m.o_112;
o.values[113]=m.o_113;
o.values[114]=m.o_114;
o.values[115]=m.o_115;
o.values[116]=m.o_116;
o.values[117]=m.o_117;
o.values[118]=m.o_118;
o.values[119]=m.o_119;
o.values[120]=m.o_120;
o.values[121]=m.o_121;
o.values[122]=m.o_122;
o.values[123]=m.o_123;
o.values[124]=m.o_124;
o.values[125]=m.o_125;
o.values[126]=m.o_126;
o.values[127]=m.o_127;
o.values[128]=m.o_128;
o.values[129]=m.o_129;
o.values[130]=m.o_130;
o.values[131]=m.o_131;
o.values[132]=m.o_132;
o.values[133]=m.o_133;
o.values[134]=m.o_134;
o.values[135]=m.o_135;
o.values[136]=m.o_136;
o.values[137]=m.o_137;
o.values[138]=m.o_138;
o.values[139]=m.o_139;
o.values[140]=m.o_140;
o.values[141]=m.o_141;
o.values[142]=m.o_142;
o.values[143]=m.o_143;
o.values[144]=m.o_144;
o.values[145]=m.o_145;
o.values[146]=m.o_146;
o.values[147]=m.o_147;
o.values[148]=m.o_148;
o.values[149]=m.o_149;
o.values[150]=m.o_150;
o.values[151]=m.o_151;
o.values[152]=m.o_152;
o.values[153]=m.o_153;
o.values[154]=m.o_154;
o.values[155]=m.o_155;
o.values[156]=m.o_156;
o.values[157]=m.o_157;
o.values[158]=m.o_158;
o.values[159]=m.o_159;
o.values[160]=m.o_160;
o.values[161]=m.o_161;
o.values[162]=m.o_162;
o.values[163]=m.o_163;
o.values[164]=m.o_164;
o.values[165]=m.o_165;
o.values[166]=m.o_166;
o.values[167]=m.o_167;
o.values[168]=m.o_168;
o.values[169]=m.o_169;
o.values[170]=m.o_170;
o.values[171]=m.o_171;
o.values[172]=m.o_172;
o.values[173]=m.o_173;
o.values[174]=m.o_174;
o.values[175]=m.o_175;
o.values[176]=m.o_176;
o.values[177]=m.o_177;
o.values[178]=m.o_178;
o.values[179]=m.o_179;
o.values[180]=m.o_180;
o.values[181]=m.o_181;
o.values[182]=m.o_182;
o.values[183]=m.o_183;
o.values[184]=m.o_184;
o.values[185]=m.o_185;
o.values[186]=m.o_186;
o.values[187]=m.o_187;
o.values[188]=m.o_188;
o.values[189]=m.o_189;
o.values[190]=m.o_190;
o.values[191]=m.o_191;
o.values[192]=m.o_192;
o.values[193]=m.o_193;
o.values[194]=m.o_194;
o.values[195]=m.o_195;
o.values[196]=m.o_196;
o.values[197]=m.o_197;
o.values[198]=m.o_198;
o.values[199]=m.o_199;
o.values[200]=m.o_200;
o.values[201]=m.o_201;
o.values[202]=m.o_202;
o.values[203]=m.o_203;
o.values[204]=m.o_204;
o.values[205]=m.o_205;
o.values[206]=m.o_206;
o.values[207]=m.o_207;
o.values[208]=m.o_208;
o.values[209]=m.o_209;
o.values[210]=m.o_210;
o.values[211]=m.o_211;
o.values[212]=m.o_212;
o.values[213]=m.o_213;
o.values[214]=m.o_214;
o.values[215]=m.o_215;
o.values[216]=m.o_216;
o.values[217]=m.o_217;
o.values[218]=m.o_218;
o.values[219]=m.o_219;
o.values[220]=m.o_220;
o.values[221]=m.o_221;
o.values[222]=m.o_222;
o.values[223]=m.o_223;
o.values[224]=m.o_224;
o.values[225]=m.o_225;
o.values[226]=m.o_226;
o.values[227]=m.o_227;
o.values[228]=m.o_228;
o.values[229]=m.o_229;
o.values[230]=m.o_230;
o.values[231]=m.o_231;
o.values[232]=m.o_232;
o.values[233]=m.o_233;
o.values[234]=m.o_234;
o.values[235]=m.o_235;
o.values[236]=m.o_236;
o.values[237]=m.o_237;
o.values[238]=m.o_238;
o.values[239]=m.o_239;
o.values[240]=m.o_240;
o.values[241]=m.o_241;
o.values[242]=m.o_242;
o.values[243]=m.o_243;
o.values[244]=m.o_244;
o.values[245]=m.o_245;
o.values[246]=m.o_246;
o.values[247]=m.o_247;
o.values[248]=m.o_248;
o.values[249]=m.o_249;
o.values[250]=m.o_250;
o.values[251]=m.o_251;
o.values[252]=m.o_252;
o.values[253]=m.o_253;
o.values[254]=m.o_254;
o.values[255]=m.o_255;
o.values[256]=m.o_256;
o.values[257]=m.o_257;
o.values[258]=m.o_258;
o.values[259]=m.o_259;
o.values[260]=m.o_260;
o.values[261]=m.o_261;
o.values[262]=m.o_262;
o.values[263]=m.o_263;
o.values[264]=m.o_264;
o.values[265]=m.o_265;
o.values[266]=m.o_266;
o.values[267]=m.o_267;
o.values[268]=m.o_268;
o.values[269]=m.o_269;
o.values[270]=m.o_270;
o.values[271]=m.o_271;
o.values[272]=m.o_272;
o.values[273]=m.o_273;
o.values[274]=m.o_274;
o.values[275]=m.o_275;
o.values[276]=m.o_276;
o.values[277]=m.o_277;
o.values[278]=m.o_278;
o.values[279]=m.o_279;
o.values[280]=m.o_280;
o.values[281]=m.o_281;
o.values[282]=m.o_282;
o.values[283]=m.o_283;
o.values[284]=m.o_284;
o.values[285]=m.o_285;
o.values[286]=m.o_286;
o.values[287]=m.o_287;
o.values[288]=m.o_288;
o.values[289]=m.o_289;
o.values[290]=m.o_290;
o.values[291]=m.o_291;
o.values[292]=m.o_292;
o.values[293]=m.o_293;
o.values[294]=m.o_294;
return o;
}
void IrisNoCNetwork::commit(){
if(!impl_->evaluated)throw std::logic_error("Network commit requires fresh evaluate");
auto &m=*impl_->model;m.clock=1;m.eval();m.clock=0;m.eval();++impl_->edge_count;impl_->evaluated=false;
}
NetworkOutputs IrisNoCNetwork::step(const NetworkInputs &i){evaluate(i);auto o=sample();commit();return o;}
void IrisNoCNetwork::save(const std::filesystem::path& p)const{
 if(impl_->evaluated||!impl_->edge_count)throw std::logic_error("Network snapshot requires a committed edge boundary");
 VerilatedSave out;out.open(p.string());out<<std::uint64_t{0x495249534e455431ULL}<<std::string(IRIS_NETWORK_SOURCE_ID)<<impl_->edge_count<<*impl_->model;out.close();
}
void IrisNoCNetwork::restore(const std::filesystem::path& p){
 if(impl_->evaluated)throw std::logic_error("Network restore during pending evaluated edge");NetworkSnapshotPrefix prefix(p);
 VerilatedRestore in;in.open(p.string());std::uint64_t magic;std::string id;in>>magic>>id>>impl_->edge_count>>*impl_->model;in.close();impl_->evaluated=false;
}
std::uint64_t IrisNoCNetwork::edges()const{return impl_->edge_count;}
const char* IrisNoCNetwork::source_identity(){return IRIS_NETWORK_SOURCE_ID;}
std::span<const NetworkField> IrisNoCNetwork::input_fields(){
static constexpr NetworkField fields[]={
{"_cbus_auto_bus_xing_in_a_ready",1},
{"_cbus_auto_bus_xing_in_d_bits_corrupt",1},
{"_cbus_auto_bus_xing_in_d_bits_data",64},
{"_cbus_auto_bus_xing_in_d_bits_denied",1},
{"_cbus_auto_bus_xing_in_d_bits_opcode",3},
{"_cbus_auto_bus_xing_in_d_bits_param",2},
{"_cbus_auto_bus_xing_in_d_bits_sink",1},
{"_cbus_auto_bus_xing_in_d_bits_size",4},
{"_cbus_auto_bus_xing_in_d_bits_source",10},
{"_cbus_auto_bus_xing_in_d_valid",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_a_ready",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_b_bits_address",33},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_b_bits_corrupt",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_b_bits_data",64},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_b_bits_mask",8},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_b_bits_opcode",3},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_b_bits_param",2},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_b_bits_size",3},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_b_bits_source",10},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_b_valid",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_c_ready",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_d_bits_corrupt",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_d_bits_data",64},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_d_bits_denied",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_d_bits_opcode",3},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_d_bits_param",2},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_d_bits_sink",2},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_d_bits_size",3},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_d_bits_source",10},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_d_valid",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_0_e_ready",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_a_ready",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_b_bits_address",33},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_b_bits_corrupt",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_b_bits_data",64},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_b_bits_mask",8},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_b_bits_opcode",3},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_b_bits_param",2},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_b_bits_size",3},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_b_bits_source",10},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_b_valid",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_c_ready",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_d_bits_corrupt",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_d_bits_data",64},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_d_bits_denied",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_d_bits_opcode",3},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_d_bits_param",2},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_d_bits_sink",2},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_d_bits_size",3},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_d_bits_source",10},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_d_valid",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_1_e_ready",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_a_ready",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_b_bits_address",33},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_b_bits_corrupt",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_b_bits_data",64},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_b_bits_mask",8},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_b_bits_opcode",3},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_b_bits_param",2},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_b_bits_size",3},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_b_bits_source",10},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_b_valid",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_c_ready",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_d_bits_corrupt",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_d_bits_data",64},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_d_bits_denied",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_d_bits_opcode",3},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_d_bits_param",2},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_d_bits_sink",2},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_d_bits_size",3},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_d_bits_source",10},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_d_valid",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_2_e_ready",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_a_ready",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_b_bits_address",33},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_b_bits_corrupt",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_b_bits_data",64},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_b_bits_mask",8},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_b_bits_opcode",3},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_b_bits_param",2},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_b_bits_size",3},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_b_bits_source",10},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_b_valid",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_c_ready",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_d_bits_corrupt",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_d_bits_data",64},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_d_bits_denied",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_d_bits_opcode",3},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_d_bits_param",2},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_d_bits_sink",2},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_d_bits_size",3},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_d_bits_source",10},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_d_valid",1},
{"_coh_wrapper_auto_coherent_jbar_anon_in_3_e_ready",1},
{"_fbus_auto_bus_xing_out_a_bits_address",35},
{"_fbus_auto_bus_xing_out_a_bits_corrupt",1},
{"_fbus_auto_bus_xing_out_a_bits_data",64},
{"_fbus_auto_bus_xing_out_a_bits_mask",8},
{"_fbus_auto_bus_xing_out_a_bits_opcode",3},
{"_fbus_auto_bus_xing_out_a_bits_param",3},
{"_fbus_auto_bus_xing_out_a_bits_size",4},
{"_fbus_auto_bus_xing_out_a_bits_source",9},
{"_fbus_auto_bus_xing_out_a_valid",1},
{"_fbus_auto_bus_xing_out_d_ready",1},
{"_sbus_buffer_1_auto_in_a_ready",1},
{"_sbus_buffer_1_auto_in_d_bits_corrupt",1},
{"_sbus_buffer_1_auto_in_d_bits_data",64},
{"_sbus_buffer_1_auto_in_d_bits_denied",1},
{"_sbus_buffer_1_auto_in_d_bits_opcode",3},
{"_sbus_buffer_1_auto_in_d_bits_param",2},
{"_sbus_buffer_1_auto_in_d_bits_sink",1},
{"_sbus_buffer_1_auto_in_d_bits_size",3},
{"_sbus_buffer_1_auto_in_d_bits_source",10},
{"_sbus_buffer_1_auto_in_d_valid",1},
{"_sbus_buffer_auto_in_a_ready",1},
{"_sbus_buffer_auto_in_d_bits_corrupt",1},
{"_sbus_buffer_auto_in_d_bits_data",64},
{"_sbus_buffer_auto_in_d_bits_denied",1},
{"_sbus_buffer_auto_in_d_bits_opcode",3},
{"_sbus_buffer_auto_in_d_bits_param",2},
{"_sbus_buffer_auto_in_d_bits_sink",1},
{"_sbus_buffer_auto_in_d_bits_size",3},
{"_sbus_buffer_auto_in_d_bits_source",10},
{"_sbus_buffer_auto_in_d_valid",1},
{"_sbus_coupler_from_rockettile_auto_tl_out_a_bits_address",35},
{"_sbus_coupler_from_rockettile_auto_tl_out_a_bits_corrupt",1},
{"_sbus_coupler_from_rockettile_auto_tl_out_a_bits_data",64},
{"_sbus_coupler_from_rockettile_auto_tl_out_a_bits_mask",8},
{"_sbus_coupler_from_rockettile_auto_tl_out_a_bits_opcode",3},
{"_sbus_coupler_from_rockettile_auto_tl_out_a_bits_param",3},
{"_sbus_coupler_from_rockettile_auto_tl_out_a_bits_size",4},
{"_sbus_coupler_from_rockettile_auto_tl_out_a_bits_source",7},
{"_sbus_coupler_from_rockettile_auto_tl_out_a_valid",1},
{"_sbus_coupler_from_rockettile_auto_tl_out_b_ready",1},
{"_sbus_coupler_from_rockettile_auto_tl_out_c_bits_address",35},
{"_sbus_coupler_from_rockettile_auto_tl_out_c_bits_corrupt",1},
{"_sbus_coupler_from_rockettile_auto_tl_out_c_bits_data",64},
{"_sbus_coupler_from_rockettile_auto_tl_out_c_bits_opcode",3},
{"_sbus_coupler_from_rockettile_auto_tl_out_c_bits_param",3},
{"_sbus_coupler_from_rockettile_auto_tl_out_c_bits_size",4},
{"_sbus_coupler_from_rockettile_auto_tl_out_c_bits_source",7},
{"_sbus_coupler_from_rockettile_auto_tl_out_c_valid",1},
{"_sbus_coupler_from_rockettile_auto_tl_out_d_ready",1},
{"_sbus_coupler_from_rockettile_auto_tl_out_e_bits_sink",4},
{"_sbus_coupler_from_rockettile_auto_tl_out_e_valid",1},
{"_sbus_coupler_to_shuttle_tile_1_auto_tl_in_a_ready",1},
{"_sbus_coupler_to_shuttle_tile_1_auto_tl_in_d_bits_corrupt",1},
{"_sbus_coupler_to_shuttle_tile_1_auto_tl_in_d_bits_data",64},
{"_sbus_coupler_to_shuttle_tile_1_auto_tl_in_d_bits_denied",1},
{"_sbus_coupler_to_shuttle_tile_1_auto_tl_in_d_bits_opcode",3},
{"_sbus_coupler_to_shuttle_tile_1_auto_tl_in_d_bits_param",2},
{"_sbus_coupler_to_shuttle_tile_1_auto_tl_in_d_bits_sink",1},
{"_sbus_coupler_to_shuttle_tile_1_auto_tl_in_d_bits_size",3},
{"_sbus_coupler_to_shuttle_tile_1_auto_tl_in_d_bits_source",10},
{"_sbus_coupler_to_shuttle_tile_1_auto_tl_in_d_valid",1},
{"_sbus_coupler_to_shuttle_tile_auto_tl_in_a_ready",1},
{"_sbus_coupler_to_shuttle_tile_auto_tl_in_d_bits_corrupt",1},
{"_sbus_coupler_to_shuttle_tile_auto_tl_in_d_bits_data",64},
{"_sbus_coupler_to_shuttle_tile_auto_tl_in_d_bits_denied",1},
{"_sbus_coupler_to_shuttle_tile_auto_tl_in_d_bits_opcode",3},
{"_sbus_coupler_to_shuttle_tile_auto_tl_in_d_bits_param",2},
{"_sbus_coupler_to_shuttle_tile_auto_tl_in_d_bits_sink",1},
{"_sbus_coupler_to_shuttle_tile_auto_tl_in_d_bits_size",3},
{"_sbus_coupler_to_shuttle_tile_auto_tl_in_d_bits_source",10},
{"_sbus_coupler_to_shuttle_tile_auto_tl_in_d_valid",1},
{"_sbus_fixedClockNode_auto_anon_out_0_reset",1},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_a_bits_address",35},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_a_bits_corrupt",1},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_a_bits_data",64},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_a_bits_mask",8},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_a_bits_opcode",3},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_a_bits_param",3},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_a_bits_size",4},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_a_bits_source",6},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_a_valid",1},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_b_ready",1},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_c_bits_address",35},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_c_bits_corrupt",1},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_c_bits_data",64},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_c_bits_opcode",3},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_c_bits_param",3},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_c_bits_size",4},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_c_bits_source",6},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_c_valid",1},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_d_ready",1},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_e_bits_sink",4},
{"_tile_prci_domain_1_auto_tl_master_clock_xing_out_e_valid",1},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_a_bits_address",35},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_a_bits_corrupt",1},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_a_bits_data",64},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_a_bits_mask",8},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_a_bits_opcode",3},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_a_bits_param",3},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_a_bits_size",4},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_a_bits_source",6},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_a_valid",1},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_b_ready",1},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_c_bits_address",35},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_c_bits_corrupt",1},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_c_bits_data",64},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_c_bits_opcode",3},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_c_bits_param",3},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_c_bits_size",4},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_c_bits_source",6},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_c_valid",1},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_d_ready",1},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_e_bits_sink",4},
{"_tile_prci_domain_auto_tl_master_clock_xing_out_e_valid",1}
};return fields;
}
std::span<const NetworkField> IrisNoCNetwork::output_fields(){
static constexpr NetworkField fields[]={
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_1_io_tilelink_a_ready",1},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_1_io_tilelink_c_ready",1},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_1_io_tilelink_d_bits_corrupt",1},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_1_io_tilelink_d_bits_data",64},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_1_io_tilelink_d_bits_denied",1},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_1_io_tilelink_d_bits_opcode",3},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_1_io_tilelink_d_bits_param",2},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_1_io_tilelink_d_bits_sink",4},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_1_io_tilelink_d_bits_size",4},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_1_io_tilelink_d_bits_source",10},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_1_io_tilelink_d_valid",1},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_2_io_tilelink_a_ready",1},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_2_io_tilelink_c_ready",1},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_2_io_tilelink_d_bits_corrupt",1},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_2_io_tilelink_d_bits_data",64},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_2_io_tilelink_d_bits_denied",1},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_2_io_tilelink_d_bits_opcode",3},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_2_io_tilelink_d_bits_param",2},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_2_io_tilelink_d_bits_sink",4},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_2_io_tilelink_d_bits_size",4},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_2_io_tilelink_d_bits_source",10},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_2_io_tilelink_d_valid",1},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_3_io_tilelink_a_ready",1},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_3_io_tilelink_c_ready",1},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_3_io_tilelink_d_bits_corrupt",1},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_3_io_tilelink_d_bits_data",64},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_3_io_tilelink_d_bits_denied",1},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_3_io_tilelink_d_bits_opcode",3},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_3_io_tilelink_d_bits_param",2},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_3_io_tilelink_d_bits_sink",4},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_3_io_tilelink_d_bits_size",4},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_3_io_tilelink_d_bits_source",10},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_3_io_tilelink_d_valid",1},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_io_tilelink_a_ready",1},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_io_tilelink_d_bits_corrupt",1},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_io_tilelink_d_bits_data",64},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_io_tilelink_d_bits_denied",1},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_io_tilelink_d_bits_opcode",3},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_io_tilelink_d_bits_param",2},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_io_tilelink_d_bits_sink",4},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_io_tilelink_d_bits_size",4},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_io_tilelink_d_bits_source",10},
{"_sbus_system_bus_noc_acd_noc_nif_master_acd_io_tilelink_d_valid",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_1_io_tilelink_a_bits_address",35},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_1_io_tilelink_a_bits_corrupt",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_1_io_tilelink_a_bits_data",64},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_1_io_tilelink_a_bits_mask",8},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_1_io_tilelink_a_bits_opcode",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_1_io_tilelink_a_bits_param",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_1_io_tilelink_a_bits_size",4},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_1_io_tilelink_a_bits_source",10},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_1_io_tilelink_a_valid",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_1_io_tilelink_c_bits_address",35},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_1_io_tilelink_c_bits_corrupt",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_1_io_tilelink_c_bits_data",64},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_1_io_tilelink_c_bits_opcode",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_1_io_tilelink_c_bits_param",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_1_io_tilelink_c_bits_size",4},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_1_io_tilelink_c_bits_source",10},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_1_io_tilelink_c_valid",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_1_io_tilelink_d_ready",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_2_io_tilelink_a_bits_address",35},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_2_io_tilelink_a_bits_corrupt",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_2_io_tilelink_a_bits_data",64},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_2_io_tilelink_a_bits_mask",8},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_2_io_tilelink_a_bits_opcode",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_2_io_tilelink_a_bits_param",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_2_io_tilelink_a_bits_size",4},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_2_io_tilelink_a_bits_source",10},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_2_io_tilelink_a_valid",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_2_io_tilelink_c_bits_address",35},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_2_io_tilelink_c_bits_corrupt",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_2_io_tilelink_c_bits_data",64},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_2_io_tilelink_c_bits_opcode",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_2_io_tilelink_c_bits_param",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_2_io_tilelink_c_bits_size",4},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_2_io_tilelink_c_bits_source",10},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_2_io_tilelink_c_valid",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_2_io_tilelink_d_ready",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_3_io_tilelink_a_bits_address",35},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_3_io_tilelink_a_bits_corrupt",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_3_io_tilelink_a_bits_data",64},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_3_io_tilelink_a_bits_mask",8},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_3_io_tilelink_a_bits_opcode",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_3_io_tilelink_a_bits_param",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_3_io_tilelink_a_bits_size",4},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_3_io_tilelink_a_bits_source",10},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_3_io_tilelink_a_valid",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_3_io_tilelink_c_bits_address",35},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_3_io_tilelink_c_bits_corrupt",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_3_io_tilelink_c_bits_data",64},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_3_io_tilelink_c_bits_opcode",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_3_io_tilelink_c_bits_param",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_3_io_tilelink_c_bits_size",4},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_3_io_tilelink_c_bits_source",10},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_3_io_tilelink_c_valid",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_3_io_tilelink_d_ready",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_4_io_tilelink_a_bits_address",35},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_4_io_tilelink_a_bits_corrupt",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_4_io_tilelink_a_bits_data",64},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_4_io_tilelink_a_bits_mask",8},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_4_io_tilelink_a_bits_opcode",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_4_io_tilelink_a_bits_param",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_4_io_tilelink_a_bits_size",4},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_4_io_tilelink_a_bits_source",10},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_4_io_tilelink_a_valid",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_4_io_tilelink_c_bits_address",35},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_4_io_tilelink_c_bits_corrupt",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_4_io_tilelink_c_bits_data",64},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_4_io_tilelink_c_bits_opcode",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_4_io_tilelink_c_bits_param",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_4_io_tilelink_c_bits_size",4},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_4_io_tilelink_c_bits_source",10},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_4_io_tilelink_c_valid",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_4_io_tilelink_d_ready",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_5_io_tilelink_a_bits_address",35},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_5_io_tilelink_a_bits_corrupt",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_5_io_tilelink_a_bits_data",64},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_5_io_tilelink_a_bits_mask",8},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_5_io_tilelink_a_bits_opcode",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_5_io_tilelink_a_bits_param",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_5_io_tilelink_a_bits_size",4},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_5_io_tilelink_a_bits_source",10},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_5_io_tilelink_a_valid",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_5_io_tilelink_d_ready",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_6_io_tilelink_a_bits_address",35},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_6_io_tilelink_a_bits_corrupt",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_6_io_tilelink_a_bits_data",64},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_6_io_tilelink_a_bits_mask",8},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_6_io_tilelink_a_bits_opcode",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_6_io_tilelink_a_bits_param",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_6_io_tilelink_a_bits_size",4},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_6_io_tilelink_a_bits_source",10},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_6_io_tilelink_a_valid",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_6_io_tilelink_d_ready",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_7_io_tilelink_a_bits_address",35},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_7_io_tilelink_a_bits_corrupt",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_7_io_tilelink_a_bits_data",64},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_7_io_tilelink_a_bits_mask",8},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_7_io_tilelink_a_bits_opcode",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_7_io_tilelink_a_bits_param",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_7_io_tilelink_a_bits_size",4},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_7_io_tilelink_a_bits_source",10},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_7_io_tilelink_a_valid",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_7_io_tilelink_d_ready",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_8_io_tilelink_a_bits_address",35},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_8_io_tilelink_a_bits_corrupt",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_8_io_tilelink_a_bits_data",64},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_8_io_tilelink_a_bits_mask",8},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_8_io_tilelink_a_bits_opcode",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_8_io_tilelink_a_bits_param",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_8_io_tilelink_a_bits_size",4},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_8_io_tilelink_a_bits_source",10},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_8_io_tilelink_a_valid",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_8_io_tilelink_d_ready",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_io_tilelink_a_bits_address",35},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_io_tilelink_a_bits_corrupt",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_io_tilelink_a_bits_data",64},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_io_tilelink_a_bits_mask",8},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_io_tilelink_a_bits_opcode",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_io_tilelink_a_bits_param",3},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_io_tilelink_a_bits_size",4},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_io_tilelink_a_bits_source",10},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_io_tilelink_a_valid",1},
{"_sbus_system_bus_noc_acd_noc_nif_slave_acd_io_tilelink_d_ready",1},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_1_auto_routers_debug_out_sa_stall_0",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_1_auto_routers_debug_out_sa_stall_1",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_1_auto_routers_debug_out_sa_stall_2",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_1_auto_routers_debug_out_sa_stall_3",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_1_auto_routers_debug_out_va_stall_0",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_1_auto_routers_debug_out_va_stall_1",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_1_auto_routers_debug_out_va_stall_2",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_1_auto_routers_debug_out_va_stall_3",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_2_auto_routers_debug_out_sa_stall_0",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_2_auto_routers_debug_out_sa_stall_1",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_2_auto_routers_debug_out_sa_stall_2",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_2_auto_routers_debug_out_sa_stall_3",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_2_auto_routers_debug_out_sa_stall_4",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_2_auto_routers_debug_out_sa_stall_5",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_2_auto_routers_debug_out_va_stall_0",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_2_auto_routers_debug_out_va_stall_1",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_2_auto_routers_debug_out_va_stall_2",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_2_auto_routers_debug_out_va_stall_3",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_2_auto_routers_debug_out_va_stall_4",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_2_auto_routers_debug_out_va_stall_5",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_3_auto_routers_debug_out_sa_stall_0",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_3_auto_routers_debug_out_sa_stall_1",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_3_auto_routers_debug_out_sa_stall_2",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_3_auto_routers_debug_out_sa_stall_3",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_3_auto_routers_debug_out_sa_stall_4",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_3_auto_routers_debug_out_va_stall_0",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_3_auto_routers_debug_out_va_stall_1",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_3_auto_routers_debug_out_va_stall_2",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_3_auto_routers_debug_out_va_stall_3",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_3_auto_routers_debug_out_va_stall_4",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_4_auto_routers_debug_out_sa_stall_0",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_4_auto_routers_debug_out_sa_stall_1",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_4_auto_routers_debug_out_sa_stall_2",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_4_auto_routers_debug_out_sa_stall_4",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_4_auto_routers_debug_out_va_stall_0",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_4_auto_routers_debug_out_va_stall_1",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_4_auto_routers_debug_out_va_stall_2",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_4_auto_routers_debug_out_va_stall_4",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_5_auto_routers_debug_out_sa_stall_0",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_5_auto_routers_debug_out_sa_stall_1",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_5_auto_routers_debug_out_sa_stall_2",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_5_auto_routers_debug_out_sa_stall_3",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_5_auto_routers_debug_out_va_stall_0",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_5_auto_routers_debug_out_va_stall_1",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_5_auto_routers_debug_out_va_stall_2",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_5_auto_routers_debug_out_va_stall_3",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_6_auto_routers_debug_out_sa_stall_0",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_6_auto_routers_debug_out_sa_stall_1",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_6_auto_routers_debug_out_va_stall_0",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_6_auto_routers_debug_out_va_stall_1",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_auto_routers_debug_out_sa_stall_0",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_auto_routers_debug_out_sa_stall_1",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_auto_routers_debug_out_sa_stall_2",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_auto_routers_debug_out_sa_stall_3",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_auto_routers_debug_out_sa_stall_4",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_auto_routers_debug_out_va_stall_0",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_auto_routers_debug_out_va_stall_1",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_auto_routers_debug_out_va_stall_2",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_auto_routers_debug_out_va_stall_3",3},
{"_sbus_system_bus_noc_acd_noc_noc_router_sink_domain_auto_routers_debug_out_va_stall_4",3},
{"_sbus_system_bus_noc_be_noc_nif_master_be_1_io_tilelink_b_bits_address",35},
{"_sbus_system_bus_noc_be_noc_nif_master_be_1_io_tilelink_b_bits_corrupt",1},
{"_sbus_system_bus_noc_be_noc_nif_master_be_1_io_tilelink_b_bits_data",64},
{"_sbus_system_bus_noc_be_noc_nif_master_be_1_io_tilelink_b_bits_mask",8},
{"_sbus_system_bus_noc_be_noc_nif_master_be_1_io_tilelink_b_bits_opcode",3},
{"_sbus_system_bus_noc_be_noc_nif_master_be_1_io_tilelink_b_bits_param",2},
{"_sbus_system_bus_noc_be_noc_nif_master_be_1_io_tilelink_b_bits_size",4},
{"_sbus_system_bus_noc_be_noc_nif_master_be_1_io_tilelink_b_bits_source",10},
{"_sbus_system_bus_noc_be_noc_nif_master_be_1_io_tilelink_b_valid",1},
{"_sbus_system_bus_noc_be_noc_nif_master_be_1_io_tilelink_e_ready",1},
{"_sbus_system_bus_noc_be_noc_nif_master_be_2_io_tilelink_b_bits_address",35},
{"_sbus_system_bus_noc_be_noc_nif_master_be_2_io_tilelink_b_bits_corrupt",1},
{"_sbus_system_bus_noc_be_noc_nif_master_be_2_io_tilelink_b_bits_data",64},
{"_sbus_system_bus_noc_be_noc_nif_master_be_2_io_tilelink_b_bits_mask",8},
{"_sbus_system_bus_noc_be_noc_nif_master_be_2_io_tilelink_b_bits_opcode",3},
{"_sbus_system_bus_noc_be_noc_nif_master_be_2_io_tilelink_b_bits_param",2},
{"_sbus_system_bus_noc_be_noc_nif_master_be_2_io_tilelink_b_bits_size",4},
{"_sbus_system_bus_noc_be_noc_nif_master_be_2_io_tilelink_b_bits_source",10},
{"_sbus_system_bus_noc_be_noc_nif_master_be_2_io_tilelink_b_valid",1},
{"_sbus_system_bus_noc_be_noc_nif_master_be_2_io_tilelink_e_ready",1},
{"_sbus_system_bus_noc_be_noc_nif_master_be_3_io_tilelink_b_bits_address",35},
{"_sbus_system_bus_noc_be_noc_nif_master_be_3_io_tilelink_b_bits_corrupt",1},
{"_sbus_system_bus_noc_be_noc_nif_master_be_3_io_tilelink_b_bits_data",64},
{"_sbus_system_bus_noc_be_noc_nif_master_be_3_io_tilelink_b_bits_mask",8},
{"_sbus_system_bus_noc_be_noc_nif_master_be_3_io_tilelink_b_bits_opcode",3},
{"_sbus_system_bus_noc_be_noc_nif_master_be_3_io_tilelink_b_bits_param",2},
{"_sbus_system_bus_noc_be_noc_nif_master_be_3_io_tilelink_b_bits_size",4},
{"_sbus_system_bus_noc_be_noc_nif_master_be_3_io_tilelink_b_bits_source",10},
{"_sbus_system_bus_noc_be_noc_nif_master_be_3_io_tilelink_b_valid",1},
{"_sbus_system_bus_noc_be_noc_nif_master_be_3_io_tilelink_e_ready",1},
{"_sbus_system_bus_noc_be_noc_nif_slave_be_1_io_tilelink_b_ready",1},
{"_sbus_system_bus_noc_be_noc_nif_slave_be_1_io_tilelink_e_bits_sink",4},
{"_sbus_system_bus_noc_be_noc_nif_slave_be_1_io_tilelink_e_valid",1},
{"_sbus_system_bus_noc_be_noc_nif_slave_be_2_io_tilelink_b_ready",1},
{"_sbus_system_bus_noc_be_noc_nif_slave_be_2_io_tilelink_e_bits_sink",4},
{"_sbus_system_bus_noc_be_noc_nif_slave_be_2_io_tilelink_e_valid",1},
{"_sbus_system_bus_noc_be_noc_nif_slave_be_3_io_tilelink_b_ready",1},
{"_sbus_system_bus_noc_be_noc_nif_slave_be_3_io_tilelink_e_bits_sink",4},
{"_sbus_system_bus_noc_be_noc_nif_slave_be_3_io_tilelink_e_valid",1},
{"_sbus_system_bus_noc_be_noc_nif_slave_be_4_io_tilelink_b_ready",1},
{"_sbus_system_bus_noc_be_noc_nif_slave_be_4_io_tilelink_e_bits_sink",4},
{"_sbus_system_bus_noc_be_noc_nif_slave_be_4_io_tilelink_e_valid",1},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_1_auto_routers_debug_out_sa_stall_0",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_1_auto_routers_debug_out_va_stall_0",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_2_auto_routers_debug_out_sa_stall_0",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_2_auto_routers_debug_out_sa_stall_1",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_2_auto_routers_debug_out_sa_stall_2",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_2_auto_routers_debug_out_sa_stall_3",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_2_auto_routers_debug_out_sa_stall_4",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_2_auto_routers_debug_out_va_stall_0",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_2_auto_routers_debug_out_va_stall_1",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_2_auto_routers_debug_out_va_stall_2",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_2_auto_routers_debug_out_va_stall_3",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_2_auto_routers_debug_out_va_stall_4",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_3_auto_routers_debug_out_sa_stall_0",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_3_auto_routers_debug_out_sa_stall_1",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_3_auto_routers_debug_out_va_stall_0",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_3_auto_routers_debug_out_va_stall_1",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_4_auto_routers_debug_out_sa_stall_0",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_4_auto_routers_debug_out_va_stall_0",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_5_auto_routers_debug_out_sa_stall_0",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_5_auto_routers_debug_out_sa_stall_1",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_5_auto_routers_debug_out_va_stall_0",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_5_auto_routers_debug_out_va_stall_1",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_6_auto_routers_debug_out_sa_stall_0",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_6_auto_routers_debug_out_va_stall_0",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_auto_routers_debug_out_sa_stall_0",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_auto_routers_debug_out_sa_stall_1",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_auto_routers_debug_out_va_stall_0",2},
{"_sbus_system_bus_noc_be_noc_noc_router_sink_domain_auto_routers_debug_out_va_stall_1",2}
};return fields;
}
}
