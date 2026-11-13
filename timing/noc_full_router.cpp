#include "noc_full_router.hpp"
#include "noc_full_router_identity.hpp"
#include "noc_full_router_contract.hpp"
#include "VNode5.h"
#include "verilated.h"
#include "verilated_save.h"
#include <fstream>
#include <algorithm>
#include <stdexcept>
namespace iris::noc {
// Inspect only the source-bound prefix before touching generated model state.
// VerilatedRestore closes by checking a trailer, so using it for an intentional
// early prefix refusal would replace our diagnostic with a trailer fatal.
class SnapshotPrefix final : public VerilatedDeserialize {
 std::ifstream file_;
 bool filled_=false;
 void fill() override {
  if(filled_)throw std::invalid_argument("Node5 snapshot prefix exhausted");
  file_.read(reinterpret_cast<char*>(m_bufp),bufferSize());auto n=file_.gcount();
  if(n<128)throw std::invalid_argument("Node5 snapshot prefix truncated");
  std::fill(m_bufp+n,m_bufp+bufferSize(),0);m_cp=m_bufp;m_endp=m_bufp+bufferSize();filled_=true;
 }
 public:
 explicit SnapshotPrefix(const std::filesystem::path& p):file_(p,std::ios::binary){
  if(!file_)throw std::invalid_argument("Node5 snapshot unavailable");m_filename=p.string();header();
  std::uint64_t magic=0;std::uint32_t length=0;*this>>magic>>length;
  if(magic!=0x495249534e4f4335ULL||length!=64)throw std::invalid_argument("Node5 snapshot source identity mismatch");
  std::string id(length,'\0');read(id.data(),length);
  if(id!=IRIS_NODE5_SOURCE_ID)throw std::invalid_argument("Node5 snapshot source identity mismatch");
 }
};
struct FullNode5Router::Impl {
 std::unique_ptr<VerilatedContext> context;
 std::unique_ptr<VNode5> model;
 std::uint64_t edge_count=0;
 explicit Impl(std::uint32_t seed):context(std::make_unique<VerilatedContext>()){
  context->threads(1);context->randSeed(seed);context->randReset(2);
  const char* args[]={"native-source-node5","+noc_util_sample_rate=0"};context->commandArgs(2,args);
  model=std::make_unique<VNode5>(context.get());model->clock=0;
 }
};
FullNode5Router::FullNode5Router(std::uint32_t seed):impl_(std::make_unique<Impl>(seed)){}
FullNode5Router::~FullNode5Router()=default;
FullNode5Router::FullNode5Router(FullNode5Router&&) noexcept=default;
FullNode5Router& FullNode5Router::operator=(FullNode5Router&&) noexcept=default;
static void validate(const FullRouterInputs& i){
 for(const auto& f:i.from_network)if(f.valid&&(f.vc>=6||f.payload.words[2]>511||f.flow.vnet>3||f.flow.ingress_node>7||f.flow.ingress_id>3||f.flow.egress_node>7||f.flow.egress_id>7))throw std::invalid_argument("Node5 physical channel field outside elaborated width");
 for(const auto& f:i.from_local)if(f.valid&&(f.payload.words[2]>511||f.egress_id>31))throw std::invalid_argument("Node5 ingress field outside elaborated width");
 for(const auto& c:i.downstream)if((c.credit_return|c.vc_free)>63)throw std::invalid_argument("Node5 credit mask outside six VCs");
 if(!i.reset){for(unsigned n=0;n<2;n++){
  const auto &f=i.from_network[n];if(f.valid){const auto &g=f.flow;unsigned word=f.vc;word=(word<<2)|g.vnet;word=(word<<3)|g.ingress_node;word=(word<<2)|g.ingress_id;word=(word<<3)|g.egress_node;word=(word<<3)|g.egress_id;if(!(n?source_contract::contains(source_contract::network1,word):source_contract::contains(source_contract::network0,word)))throw std::invalid_argument("Node5 flow outside exact elaborated routing table");}
  const auto &local=i.from_local[n];if(local.valid&&!(n?source_contract::contains(source_contract::ingress1,local.egress_id):source_contract::contains(source_contract::ingress0,local.egress_id)))throw std::invalid_argument("Node5 local egress ID outside exact elaborated flow set");
 }}

}
FullRouterOutputs FullNode5Router::step(const FullRouterInputs& i){
 validate(i);auto& m=*impl_->model;m.clock=0;m.reset=i.reset;
// BEGIN GENERATED PORT MAP
m.auto_dest_nodes_in_0_flit_0_valid=i.from_network[0].valid;
m.auto_dest_nodes_in_0_flit_0_bits_head=i.from_network[0].head;
m.auto_dest_nodes_in_0_flit_0_bits_tail=i.from_network[0].tail;
m.auto_dest_nodes_in_0_flit_0_bits_payload[0]=i.from_network[0].payload.words[0];
m.auto_dest_nodes_in_0_flit_0_bits_payload[1]=i.from_network[0].payload.words[1];
m.auto_dest_nodes_in_0_flit_0_bits_payload[2]=i.from_network[0].payload.words[2];
m.auto_dest_nodes_in_0_flit_0_bits_flow_vnet_id=i.from_network[0].flow.vnet;
m.auto_dest_nodes_in_0_flit_0_bits_flow_ingress_node=i.from_network[0].flow.ingress_node;
m.auto_dest_nodes_in_0_flit_0_bits_flow_ingress_node_id=i.from_network[0].flow.ingress_id;
m.auto_dest_nodes_in_0_flit_0_bits_flow_egress_node=i.from_network[0].flow.egress_node;
m.auto_dest_nodes_in_0_flit_0_bits_flow_egress_node_id=i.from_network[0].flow.egress_id;
m.auto_dest_nodes_in_0_flit_0_bits_virt_channel_id=i.from_network[0].vc;
m.auto_ingress_nodes_in_0_flit_valid=i.from_local[0].valid;
m.auto_ingress_nodes_in_0_flit_bits_head=i.from_local[0].head;
m.auto_ingress_nodes_in_0_flit_bits_tail=i.from_local[0].tail;
m.auto_ingress_nodes_in_0_flit_bits_payload[0]=i.from_local[0].payload.words[0];
m.auto_ingress_nodes_in_0_flit_bits_payload[1]=i.from_local[0].payload.words[1];
m.auto_ingress_nodes_in_0_flit_bits_payload[2]=i.from_local[0].payload.words[2];
m.auto_ingress_nodes_in_0_flit_bits_egress_id=i.from_local[0].egress_id;
m.auto_source_nodes_out_0_credit_return=i.downstream[0].credit_return;
m.auto_source_nodes_out_0_vc_free=i.downstream[0].vc_free;
m.auto_dest_nodes_in_1_flit_0_valid=i.from_network[1].valid;
m.auto_dest_nodes_in_1_flit_0_bits_head=i.from_network[1].head;
m.auto_dest_nodes_in_1_flit_0_bits_tail=i.from_network[1].tail;
m.auto_dest_nodes_in_1_flit_0_bits_payload[0]=i.from_network[1].payload.words[0];
m.auto_dest_nodes_in_1_flit_0_bits_payload[1]=i.from_network[1].payload.words[1];
m.auto_dest_nodes_in_1_flit_0_bits_payload[2]=i.from_network[1].payload.words[2];
m.auto_dest_nodes_in_1_flit_0_bits_flow_vnet_id=i.from_network[1].flow.vnet;
m.auto_dest_nodes_in_1_flit_0_bits_flow_ingress_node=i.from_network[1].flow.ingress_node;
m.auto_dest_nodes_in_1_flit_0_bits_flow_ingress_node_id=i.from_network[1].flow.ingress_id;
m.auto_dest_nodes_in_1_flit_0_bits_flow_egress_node=i.from_network[1].flow.egress_node;
m.auto_dest_nodes_in_1_flit_0_bits_flow_egress_node_id=i.from_network[1].flow.egress_id;
m.auto_dest_nodes_in_1_flit_0_bits_virt_channel_id=i.from_network[1].vc;
m.auto_ingress_nodes_in_1_flit_valid=i.from_local[1].valid;
m.auto_ingress_nodes_in_1_flit_bits_head=i.from_local[1].head;
m.auto_ingress_nodes_in_1_flit_bits_tail=i.from_local[1].tail;
m.auto_ingress_nodes_in_1_flit_bits_payload[0]=i.from_local[1].payload.words[0];
m.auto_ingress_nodes_in_1_flit_bits_payload[1]=i.from_local[1].payload.words[1];
m.auto_ingress_nodes_in_1_flit_bits_payload[2]=i.from_local[1].payload.words[2];
m.auto_ingress_nodes_in_1_flit_bits_egress_id=i.from_local[1].egress_id;
m.auto_source_nodes_out_1_credit_return=i.downstream[1].credit_return;
m.auto_source_nodes_out_1_vc_free=i.downstream[1].vc_free;
m.auto_egress_nodes_out_flit_ready=i.local_ready;
m.eval();FullRouterOutputs o{};
o.to_network[0].valid=m.auto_source_nodes_out_0_flit_0_valid;
o.to_network[0].head=m.auto_source_nodes_out_0_flit_0_bits_head;
o.to_network[0].tail=m.auto_source_nodes_out_0_flit_0_bits_tail;
o.to_network[0].payload.words[0]=m.auto_source_nodes_out_0_flit_0_bits_payload[0];
o.to_network[0].payload.words[1]=m.auto_source_nodes_out_0_flit_0_bits_payload[1];
o.to_network[0].payload.words[2]=m.auto_source_nodes_out_0_flit_0_bits_payload[2];
o.to_network[0].flow.vnet=m.auto_source_nodes_out_0_flit_0_bits_flow_vnet_id;
o.to_network[0].flow.ingress_node=m.auto_source_nodes_out_0_flit_0_bits_flow_ingress_node;
o.to_network[0].flow.ingress_id=m.auto_source_nodes_out_0_flit_0_bits_flow_ingress_node_id;
o.to_network[0].flow.egress_node=m.auto_source_nodes_out_0_flit_0_bits_flow_egress_node;
o.to_network[0].flow.egress_id=m.auto_source_nodes_out_0_flit_0_bits_flow_egress_node_id;
o.to_network[0].vc=m.auto_source_nodes_out_0_flit_0_bits_virt_channel_id;
o.local_ready[0]=m.auto_ingress_nodes_in_0_flit_ready;
o.upstream[0].credit_return=m.auto_dest_nodes_in_0_credit_return;
o.upstream[0].vc_free=m.auto_dest_nodes_in_0_vc_free;
o.to_network[1].valid=m.auto_source_nodes_out_1_flit_0_valid;
o.to_network[1].head=m.auto_source_nodes_out_1_flit_0_bits_head;
o.to_network[1].tail=m.auto_source_nodes_out_1_flit_0_bits_tail;
o.to_network[1].payload.words[0]=m.auto_source_nodes_out_1_flit_0_bits_payload[0];
o.to_network[1].payload.words[1]=m.auto_source_nodes_out_1_flit_0_bits_payload[1];
o.to_network[1].payload.words[2]=m.auto_source_nodes_out_1_flit_0_bits_payload[2];
o.to_network[1].flow.vnet=m.auto_source_nodes_out_1_flit_0_bits_flow_vnet_id;
o.to_network[1].flow.ingress_node=m.auto_source_nodes_out_1_flit_0_bits_flow_ingress_node;
o.to_network[1].flow.ingress_id=m.auto_source_nodes_out_1_flit_0_bits_flow_ingress_node_id;
o.to_network[1].flow.egress_node=m.auto_source_nodes_out_1_flit_0_bits_flow_egress_node;
o.to_network[1].flow.egress_id=m.auto_source_nodes_out_1_flit_0_bits_flow_egress_node_id;
o.to_network[1].vc=m.auto_source_nodes_out_1_flit_0_bits_virt_channel_id;
o.local_ready[1]=m.auto_ingress_nodes_in_1_flit_ready;
o.upstream[1].credit_return=m.auto_dest_nodes_in_1_credit_return;
o.upstream[1].vc_free=m.auto_dest_nodes_in_1_vc_free;
o.to_local.valid=m.auto_egress_nodes_out_flit_valid;
o.to_local.head=m.auto_egress_nodes_out_flit_bits_head;
o.to_local.tail=m.auto_egress_nodes_out_flit_bits_tail;
o.to_local.payload.words[0]=m.auto_egress_nodes_out_flit_bits_payload[0];
o.to_local.payload.words[1]=m.auto_egress_nodes_out_flit_bits_payload[1];
o.to_local.payload.words[2]=m.auto_egress_nodes_out_flit_bits_payload[2];
o.va_stalls[0]=m.auto_debug_out_va_stall_0;o.sa_stalls[0]=m.auto_debug_out_sa_stall_0;
o.va_stalls[1]=m.auto_debug_out_va_stall_1;o.sa_stalls[1]=m.auto_debug_out_sa_stall_1;
o.va_stalls[2]=m.auto_debug_out_va_stall_2;o.sa_stalls[2]=m.auto_debug_out_sa_stall_2;
o.va_stalls[3]=m.auto_debug_out_va_stall_3;o.sa_stalls[3]=m.auto_debug_out_sa_stall_3;
m.clock=1;m.eval();m.clock=0;m.eval();++impl_->edge_count;return o;
}
void FullNode5Router::save(const std::filesystem::path& p)const{
 VerilatedSave out;out.open(p.string());out<<std::uint64_t{0x495249534e4f4335ULL}<<std::string(IRIS_NODE5_SOURCE_ID)<<impl_->edge_count<<*impl_->model;out.close();
}
void FullNode5Router::restore(const std::filesystem::path& p){
 SnapshotPrefix prefix(p);
 VerilatedRestore in;in.open(p.string());std::uint64_t magic=0;std::string id;in>>magic>>id;if(magic!=0x495249534e4f4335ULL||id!=IRIS_NODE5_SOURCE_ID)throw std::invalid_argument("Node5 snapshot source identity mismatch");in>>impl_->edge_count>>*impl_->model;in.close();
}
std::uint64_t FullNode5Router::edges()const{return impl_->edge_count;}
const char* FullNode5Router::source_identity(){return IRIS_NODE5_SOURCE_ID;}
} // namespace iris::noc
