#include "saturn_storefront_v1.hpp"
#include "VComputeStorefront.h"
#include "verilated.h"
#include <algorithm>
#include <stdexcept>
namespace iris::saturn_storefront {
namespace {
void need(bool value,const char*text){if(!value)throw std::runtime_error(text);}
Bits width_mask(unsigned width){Bits b;for(unsigned n=0;n<width;++n)b.limbs[n/64]|=std::uint64_t(1)<<(n%64);return b;}
struct ContextScope {
  VerilatedContext*previous=Verilated::threadContextp();
  explicit ContextScope(VerilatedContext*context){Verilated::threadContextp(context);}
  ContextScope()=default;
  ~ContextScope(){Verilated::threadContextp(previous);}
};
// Exact named raw ports, generated solely from the frozen extraction catalog.
#include "saturn_storefront_ports.generated.inc"
struct Request {
  Owner owner;bool load=false;std::uint64_t address=0;unsigned mask=0;
  std::array<std::uint8_t,16>data{},known{};
  bool operator==(const Request&)const=default;
};
struct Tracked {Request request;unsigned stage=1;std::uint64_t d_edge=0;std::array<std::uint8_t,16>returned{};};
struct State {
  std::array<std::optional<Tracked>,32>owners;
  std::array<std::uint64_t,32>last_generation{};
  std::optional<Request>blocked_load,blocked_store;
};
bool empty(const State&s){return!s.blocked_load&&!s.blocked_store&&std::none_of(s.owners.begin(),s.owners.end(),[](const auto&o){return bool(o);});}
}
Input concrete(unsigned width,std::uint64_t low){need(width&&width<=256,"IRIS_STOREFRONT_WIDTH");return {Bits{{low,0,0,0}},width_mask(width)};}
struct Model::Impl {
  unsigned hart;Calendar calendar;std::vector<Domain>domains;std::uint64_t epoch=0,edges=0,last_tick=0,prepared_tick=0;
  bool has_tick=false,in_reset=false,reset_seen=false,evaluated=false,prepared=false,held_reset=false;
  std::unique_ptr<VerilatedContext>context;
  std::unique_ptr<VComputeStorefront>raw;
  std::vector<Input>inputs;Outputs outputs;
  std::optional<Owner>load,store;
  State state,next;
  std::vector<Receipt>events,last_events;
  explicit Impl(unsigned h,unsigned seed,const std::vector<std::string>&args,Calendar c,std::vector<Domain>d):hart(h),calendar(c),domains(std::move(d)){
    need(h<2,"IRIS_STOREFRONT_COMPUTE_HART_ONLY");need(c.period_master_ticks==2&&c.phase_master_ticks<2,"IRIS_STOREFRONT_EXPLICIT_COMPUTE_CALENDAR");
    need(!domains.empty(),"IRIS_STOREFRONT_DECLARED_DOMAIN_REQUIRED");std::sort(domains.begin(),domains.end(),[](const auto&a,const auto&b){return a.base<b.base;});std::uint64_t end=0;for(const auto&domain:domains){need(domain.bytes&&domain.base<(std::uint64_t(1)<<35)&&domain.bytes<=(std::uint64_t(1)<<35)-domain.base&&domain.base>=end,"IRIS_STOREFRONT_INVALID_DOMAINS");end=domain.base+domain.bytes;}
    for(const auto&a:args)need(!a.empty()&&a.front()=='+'&&!a.starts_with("+verilator+"),"IRIS_STOREFRONT_SOURCE_PLUSARGS_ONLY");
    ContextScope caller;auto owned=std::make_unique<VerilatedContext>();Verilated::threadContextp(owned.get());owned->threads(1);owned->randSeed(seed);owned->randReset(2);
    std::vector<std::string>strings{"iris-source-compute-storefront"};strings.insert(strings.end(),args.begin(),args.end());std::vector<const char*>argv;for(const auto&a:strings)argv.push_back(a.c_str());owned->commandArgs(argv.size(),argv.data());
    auto model=std::make_unique<VComputeStorefront>(owned.get());model->clock=0;context=std::move(owned);raw=std::move(model);
  }
  ~Impl(){if(!context)return;ContextScope caller;if(caller.previous==context.get())caller.previous=Verilated::defaultContextp();Verilated::threadContextp(context.get());raw.reset();context.reset();}
  const Input&input(std::string_view name)const{return inputs.at(Model::input_index(name));}
  std::uint64_t iv(std::string_view name)const{return input(name).value.limbs[0];}
  void require_known(std::string_view name,unsigned width)const{const auto m=width_mask(width);const auto&v=input(name);for(unsigned n=0;n<4;++n)need((v.known.limbs[n]&m.limbs[n])==m.limbs[n],"IRIS_STOREFRONT_UNKNOWN_REQUIRED_INPUT");}
  std::uint64_t ov(std::string_view name)const{return outputs.words.at(Model::output_index(name)).limbs[0];}
  void event(const Request&r,Phase phase,unsigned source,std::uint64_t tick,const std::array<std::uint8_t,16>*returned=nullptr){Receipt e{r.owner,phase,r.load,source,r.mask,edges,tick,r.address,r.data,r.known};if(returned){e.data=*returned;e.known.fill(255);}events.push_back(e);}
  std::optional<Request>descriptor(bool is_load)const{
    const std::string p=is_load?"io_vec_load_req_":"io_vec_store_req_";if(!iv(p+"valid"))return{};
    auto metadata=is_load?load:store;need(bool(metadata),"IRIS_STOREFRONT_REQUEST_WITHOUT_OWNER");Request r;r.owner=*metadata;r.load=is_load;r.address=iv(p+"bits_addr");r.mask=is_load?65535:iv(p+"bits_mask");
    need(r.owner.hart==hart&&r.owner.epoch==epoch&&r.owner.command&&r.owner.generation&&r.owner.tag<16&&r.owner.tag==iv(p+"bits_tag"),"IRIS_STOREFRONT_OWNER_IDENTITY");
    need(r.address<(std::uint64_t(1)<<35)&&!(r.address&15)&&r.mask,"IRIS_STOREFRONT_PHYSICAL16_ADDRESS_OR_MASK_SCOPE");
    need(std::any_of(domains.begin(),domains.end(),[&](const auto&d){return r.address>=d.base&&r.address-d.base<=d.bytes&&16<=d.bytes-(r.address-d.base);}),"IRIS_STOREFRONT_UNMAPPED_REQUEST");
    if(!is_load){const auto&data=input(p+"bits_data");for(unsigned n=0;n<16;++n)if(r.mask&(1u<<n)){const auto shift=(n%8)*8;r.data[n]=data.value.limbs[n/8]>>shift;r.known[n]=data.known.limbs[n/8]>>shift;need(r.known[n]==255,"IRIS_STOREFRONT_UNKNOWN_STROBED_BYTE");}}
    return r;
  }
};
Model::Model(unsigned hart,unsigned seed,std::vector<std::string>args,Calendar c,std::vector<Domain>d):impl_(std::make_unique<Impl>(hart,seed,args,c,std::move(d))){}
Model::~Model()=default;
std::span<const Field>Model::input_fields(){return input_catalog;}
std::span<const Field>Model::output_fields(){return output_catalog;}
unsigned Model::input_index(std::string_view name){for(unsigned n=0;n<input_catalog.size();++n)if(input_catalog[n].name==name)return n;throw std::invalid_argument("IRIS_STOREFRONT_UNKNOWN_INPUT");}
unsigned Model::output_index(std::string_view name){for(unsigned n=0;n<output_catalog.size();++n)if(output_catalog[n].name==name)return n;throw std::invalid_argument("IRIS_STOREFRONT_UNKNOWN_OUTPUT");}
const char*Model::raw_source_identity(){return "fa3fef57b9606273a207e4a429d81ddda72b115264c09df7468857eb3f07c715";}
void Model::evaluate_control(std::span<const Input>inputs,std::optional<Owner>load,std::optional<Owner>store){
  auto&p=*impl_;p.evaluated=false;p.prepared=false;p.events.clear();need(inputs.size()==input_catalog.size(),"IRIS_STOREFRONT_INPUT_COUNT");
  for(unsigned n=0;n<inputs.size();++n){const auto m=width_mask(input_catalog[n].width);for(unsigned w=0;w<4;++w)need(!(inputs[n].value.limbs[w]&~m.limbs[w])&&!(inputs[n].known.limbs[w]&~m.limbs[w]),"IRIS_STOREFRONT_EXCESS_FIELD_WIDTH");}
  p.inputs.assign(inputs.begin(),inputs.end());p.load=load;p.store=store;
  for(auto name:{"reset","auto_atl_out_a_ready","auto_atl_out_d_valid","io_vec_load_req_valid","io_vec_store_req_valid"})p.require_known(name,1);
  for(bool is_load:{false,true}){const std::string prefix=is_load?"io_vec_load_req_":"io_vec_store_req_";if(p.iv(prefix+"valid")){p.require_known(prefix+"bits_addr",40);p.require_known(prefix+"bits_tag",4);if(!is_load)p.require_known(prefix+"bits_mask",16);}}
  if(p.iv("auto_atl_out_d_valid"))for(auto[name,width]:std::initializer_list<std::pair<const char*,unsigned>>{{"opcode",3},{"param",2},{"size",4},{"source",5},{"sink",4},{"denied",1},{"corrupt",1}})p.require_known("auto_atl_out_d_bits_"+std::string(name),width);
  ContextScope owner(p.context.get());p.raw->clock=0;set_raw_inputs(*p.raw,inputs);p.raw->eval();p.outputs.words=get_raw_outputs(*p.raw);p.held_reset=p.iv("reset");p.outputs.protocol_qualified=p.reset_seen&&!p.held_reset;p.evaluated=true;
}
Outputs Model::sample()const{need(impl_->evaluated,"IRIS_STOREFRONT_STALE_SAMPLE");return impl_->outputs;}
void Model::prepare(std::uint64_t tick){
  auto&p=*impl_;need(p.evaluated,"IRIS_STOREFRONT_STALE_PREPARE");p.prepared=false;p.events.clear();
  try{
    need(tick%p.calendar.period_master_ticks==p.calendar.phase_master_ticks&&(!p.has_tick||(p.last_tick<=~std::uint64_t(0)-p.calendar.period_master_ticks&&tick==p.last_tick+p.calendar.period_master_ticks)),"IRIS_STOREFRONT_STALE_OR_SKIPPED_SOURCE_EDGE");p.next=p.state;
    if(p.held_reset){need(empty(p.state),"IRIS_STOREFRONT_RESET_WITH_OWNED_TRANSACTIONS");need(!p.iv("io_vec_load_req_valid")&&!p.iv("io_vec_store_req_valid")&&!p.iv("auto_atl_out_d_valid"),"IRIS_STOREFRONT_ACTIVE_INPUT_DURING_RESET");p.next=State{};}
    else{
      need(p.reset_seen,"IRIS_STOREFRONT_EXPLICIT_RESET_REQUIRED");
      for(bool is_load:{false,true}){auto r=p.descriptor(is_load);auto&blocked=is_load?p.next.blocked_load:p.next.blocked_store;need(!blocked||(r&&*r==*blocked),"IRIS_STOREFRONT_OFFER_CHANGED_WHILE_BLOCKED");
        const auto ready=p.ov(is_load?"io_vec_load_req_ready":"io_vec_store_req_ready");blocked=r&&!ready?r:std::nullopt;
        if(r&&ready){const unsigned source=r->owner.tag+(is_load?16:0);need(!p.next.owners[source],"IRIS_STOREFRONT_TAG_ALREADY_OWNED");need(r->owner.generation>p.next.last_generation[source],"IRIS_STOREFRONT_STALE_GENERATION");p.next.last_generation[source]=r->owner.generation;p.next.owners[source]=Tracked{*r};p.event(*r,Phase::VMURequest,source,tick);}}
      if(p.ov("auto_atl_out_a_valid")){
        const unsigned source=p.ov("auto_atl_out_a_bits_source");need(source<32&&bool(p.next.owners[source]),"IRIS_STOREFRONT_A_WITHOUT_OWNER");auto&o=*p.next.owners[source];const auto&r=o.request;
        need(o.stage==1&&p.ov("auto_atl_out_a_bits_address")==r.address&&p.ov("auto_atl_out_a_bits_size")==4&&p.ov("auto_atl_out_a_bits_param")==0&&!p.ov("auto_atl_out_a_bits_corrupt"),"IRIS_STOREFRONT_A_METADATA_OWNER");
        need(p.ov("auto_atl_out_a_bits_opcode")==unsigned(r.load?4:1)&&p.ov("auto_atl_out_a_bits_mask")==std::uint64_t(r.mask)<<((r.address&16)?16:0),"IRIS_STOREFRONT_A_MASK_OR_OPCODE");
        if(!r.load){const auto&data=p.outputs.words[output_index("auto_atl_out_a_bits_data")];for(unsigned n=0;n<16;++n)if(r.mask&(1u<<n)){const unsigned byte=n+((r.address&16)?16:0);need(std::uint8_t(data.limbs[byte/8]>>(8*(byte%8)))==r.data[n],"IRIS_STOREFRONT_A_PAYLOAD_VERSION");}}
        if(p.iv("auto_atl_out_a_ready")){o.stage=2;p.event(r,Phase::TileA,source,tick);}}
      if(p.iv("auto_atl_out_d_valid")){
        const unsigned source=p.iv("auto_atl_out_d_bits_source");need(source<32&&bool(p.next.owners[source]),"IRIS_STOREFRONT_D_WITHOUT_OWNER");auto&o=*p.next.owners[source];const auto&r=o.request;
        need(o.stage==2,"IRIS_STOREFRONT_DUPLICATE_OR_EARLY_D");need(p.iv("auto_atl_out_d_bits_opcode")==unsigned(r.load?1:0)&&p.iv("auto_atl_out_d_bits_size")==4&&p.iv("auto_atl_out_d_bits_param")==0,"IRIS_STOREFRONT_D_METADATA_OWNER");need(!p.iv("auto_atl_out_d_bits_denied")&&!p.iv("auto_atl_out_d_bits_corrupt"),"IRIS_STOREFRONT_D_FAULT_UNQUALIFIED");
        if(r.load){const auto&data=p.input("auto_atl_out_d_bits_data");for(unsigned n=0;n<16;++n){const unsigned byte=n+((r.address&16)?16:0),shift=8*(byte%8);need(std::uint8_t(data.known.limbs[byte/8]>>shift)==255,"IRIS_STOREFRONT_UNKNOWN_RETURNED_BYTE");o.returned[n]=data.value.limbs[byte/8]>>shift;}}
        if(p.ov("auto_atl_out_d_ready")){o.stage=3;o.d_edge=p.edges;p.event(r,Phase::TileD,source,tick,r.load?&o.returned:nullptr);}}
      for(bool is_load:{false,true})if(p.ov(is_load?"io_vec_load_resp_valid":"io_vec_store_ack_valid")){
        const unsigned tag=p.ov(is_load?"io_vec_load_resp_bits_tag":"io_vec_store_ack_bits_tag"),source=tag+(is_load?16:0);need(source<32&&bool(p.next.owners[source]),"IRIS_STOREFRONT_RESPONSE_WITHOUT_OWNER");auto&o=*p.next.owners[source];need(o.stage==3&&p.edges>o.d_edge,"IRIS_STOREFRONT_RESPONSE_PHASE_OR_DUPLICATE");
        if(is_load){const auto&data=p.outputs.words[output_index("io_vec_load_resp_bits_data")];for(unsigned n=0;n<16;++n)need(std::uint8_t(data.limbs[n/8]>>(8*(n%8)))==o.returned[n],"IRIS_STOREFRONT_RESPONSE_PAYLOAD_OWNER");}
        p.event(o.request,Phase::VMUResponse,source,tick,is_load?&o.returned:nullptr);p.next.owners[source].reset();}
    }
    p.prepared_tick=tick;p.prepared=true;
  }catch(...){p.evaluated=false;p.prepared=false;p.events.clear();throw;}
}
void Model::commit(){
  auto&p=*impl_;need(p.evaluated&&p.prepared,"IRIS_STOREFRONT_COMMIT_WITHOUT_SETTLED_PREPARE");p.evaluated=false;p.prepared=false;
  ContextScope owner(p.context.get());p.raw->clock=1;p.raw->eval();p.raw->clock=0;p.raw->eval();
  p.state=std::move(p.next);p.last_events=std::move(p.events);if(p.held_reset&&!p.in_reset)++p.epoch;p.in_reset=p.held_reset;p.reset_seen|=p.held_reset;p.last_tick=p.prepared_tick;p.has_tick=true;++p.edges;
}
std::span<const Receipt>Model::last_receipts()const{return impl_->last_events;}
bool Model::drained()const{return impl_->reset_seen&&empty(impl_->state);}
unsigned Model::owned_requests()const{return std::count_if(impl_->state.owners.begin(),impl_->state.owners.end(),[](const auto&o){return bool(o);});}
std::uint64_t Model::reset_epoch()const{return impl_->epoch;}
std::uint64_t Model::committed_source_edges()const{return impl_->edges;}
}
