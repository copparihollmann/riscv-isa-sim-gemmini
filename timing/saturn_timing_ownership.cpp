#include "saturn_timing_ownership.hpp"
#include "saturn_ownership_source_config.hpp"
#include <algorithm>
#include <array>
#include <bit>
#include <deque>
#include <limits>
#include <set>
#include <stdexcept>
namespace iris::saturn {
namespace {
struct Micro{std::uint64_t id;OwnedDispatch owner;};
struct Signal {bool extra;unsigned index,width;};
struct FPCellSignals{Signal stage0,stage1,macc,row,col;};
struct MRFCellSignals{Signal index,macc,fp8,zero,mvin,mvin_data,sum_int,sum_fp8,fp_index;};
struct MemPacket{OwnedDispatch owner;unsigned slot,tag;bool masked,last,ack=false;std::optional<std::uint64_t> address,byte_mask;};
struct TLActor{OwnedDispatch owner;std::uint64_t id,edge,address,bytes;unsigned tag,opcode,size,A_seen=0,D_seen=0,A_total=0,D_total=0;std::uint64_t A_bytes=0;};
struct PipeOwner{Micro micro;unsigned depth;std::uint64_t fu_sel;bool tail;};
struct ExecutionOwners{SourceExecutionConfig config;std::vector<std::optional<PipeOwner>>pipe;std::map<std::string,std::optional<Micro>>iterative;std::optional<Micro>scalar;};
struct FPUActor{Micro micro;std::uint64_t id,edge;};
struct VRFWrite{std::optional<Micro>micro;unsigned eg;std::vector<std::uint64_t>mask;bool scrub=false;};
struct ScalarActor{OwnedCommand command;std::optional<OwnedDispatch>dispatch;std::optional<std::uint64_t>micro;std::uint64_t id,edge;};
std::uint64_t sequence(std::uint64_t&value,const char*name){if(value==std::numeric_limits<std::uint64_t>::max())throw std::overflow_error(std::string("Host ownership generation exhausted: ")+name);return value++;}
}
struct SaturnOwnershipLedger::Impl {
 Profile profile;unsigned hart,VAT_size;std::uint64_t edge=0,epoch=0,next_command=0,next_dispatch=0,next_micro=0;
 bool reset_seen=false,previous_reset=false;
 std::map<std::string,Signal> signals;std::map<std::string,unsigned> inputs,outputs;
 std::map<std::string,std::vector<Signal>> wide;
 std::optional<OwnedCommand> s1,s2,ifc;
 std::vector<std::optional<OwnedDispatch>> VAT;
 std::vector<std::uint64_t> VAT_generation;
 unsigned expected_head=0,expected_tail=0;std::uint16_t expected_debug=0;
 std::map<std::string,std::optional<OwnedDispatch>> seq;
 std::optional<Micro> array_stage;
 std::array<std::optional<Micro>,6> readout;
 std::array<std::optional<Micro>,256> fp0,fp1;
 std::array<FPCellSignals,256> cell_signals;
 std::vector<MRFCellSignals> numeric_cells;
 std::vector<std::optional<OwnedDispatch>> LIQ,SIQ;
 std::map<unsigned,MemPacket> load_tags,store_tags;
 std::deque<MemPacket> store_requests,store_flights;
 std::map<unsigned,TLActor> TL;
 std::uint64_t next_transaction=0;
 unsigned memory_bytes=0,bus_bytes=0,tag_limit=0;
 std::vector<ExecutionOwners> execution;
 std::deque<FPUActor> FPU;
 std::deque<OwnedDispatch> load_responses;
 std::vector<std::optional<OwnedDispatch>> segment_owner;
 std::vector<bool> segment_mode,segment_drained;
 std::vector<std::optional<VRFWrite>> ll_pending;
 std::deque<ScalarActor> scalar_responses;
 std::map<std::string,std::uint64_t> counts;
 Impl(Profile p,unsigned h,std::span<const Field>a,std::span<const Field>b):profile(p),hart(h),VAT_size(p==Profile::Compute128?32:8),VAT(VAT_size),VAT_generation(VAT_size){
  if((p==Profile::Compute128&&h>1)||(p==Profile::Rocket256&&h!=2))throw std::invalid_argument("Ownership profile/hart mismatch");
  for(bool extra:{false,true}){const auto fields=extra?b:a;for(unsigned n=0;n<fields.size();++n){const auto&f=fields[n];const std::string name(f.name);wide[name.substr(0,name.find('@'))].push_back({extra,n,f.word_width});if(f.physical_width>64)continue;if(!signals.emplace(name,Signal{extra,n,f.word_width}).second)throw std::invalid_argument("Duplicate ownership signal");}}
  for(unsigned n=0;n<SaturnTimingCut::input_fields(p).size();++n)inputs.emplace(std::string(SaturnTimingCut::input_fields(p)[n].name),n);
  for(unsigned n=0;n<SaturnTimingCut::output_fields(p).size();++n)outputs.emplace(std::string(SaturnTimingCut::output_fields(p)[n].name),n);
  for(const auto&name:p==Profile::Compute128?std::vector<std::string>{"vu.vls","vu.vss","vu.vps","vu.vxsint","vu.vxsfp","vu.vos"}:std::vector<std::string>{"vu.vls","vu.vss","vu.vps","vu.vxsfp_int"})seq[name]={};
  if(p==Profile::Compute128)for(unsigned cr=0;cr<4;++cr)for(unsigned cc=0;cc<4;++cc)for(unsigned r=0;r<4;++r)for(unsigned c=0;c<4;++c){const unsigned cell=((cr*4+cc)*4+r)*4+c;const auto path="vu.vopu.clusters_"+std::to_string(cr)+"_"+std::to_string(cc)+".cells_"+std::to_string(r)+"_"+std::to_string(c)+".fma.";cell_signals[cell]={signals.at(path+"valid_stage0_pipe_v"),signals.at(path+"io_validout_pipe_v"),signals.at("vu.vopu_ctrl_reg_macc_"+std::to_string(cr)),signals.at("vu.vopu_ctrl_reg_row_en_"+std::to_string(cr)+"_"+std::to_string(r)),signals.at("vu.vopu_ctrl_reg_col_en_"+std::to_string(cc)+"_"+std::to_string(c))};}
  if(p==Profile::Compute128&&wide.contains("vu.vrf.vrf.vrf_0.write_bits_data"))for(unsigned cr=0;cr<4;++cr)for(unsigned cc=0;cc<4;++cc)for(unsigned r=0;r<4;++r)for(unsigned c=0;c<4;++c){const auto path="vu.vopu.clusters_"+std::to_string(cr)+"_"+std::to_string(cc)+".cells_"+std::to_string(r)+"_"+std::to_string(c)+'.';numeric_cells.push_back({signals.at(path+"io_mrf_idx"),signals.at(path+"io_macc"),signals.at(path+"io_fp8"),signals.at(path+"io_zero"),signals.at(path+"io_mvin"),signals.at(path+"io_mvin_data"),signals.at(path+"_sum_int_T_1"),signals.at(path+"sum_fp8"),signals.at(path+"mrf_idx_pipe_pipe_pipe_b")});}
  for(const auto&[name,field]:signals){if(name.starts_with("vmu.liq_valids_"))LIQ.push_back({});if(name.starts_with("vmu.siq_valids_"))SIQ.push_back({});}
  if(LIQ.empty()||SIQ.empty())throw std::invalid_argument("Missing source LSIQ dimensions");
  memory_bytes=signals.at("vmu.io_dmem_store_req_bits_mask").width;
  for(const auto&f:SaturnTimingCut::output_fields(p))if(f.name=="auto_atl_out_a_bits_mask")bus_bytes=f.physical_width;
  const auto tag_bits=signals.at("tl_if.reader.io_req_bits_tag").width;
  if(tag_bits>6||!memory_bytes||!bus_bytes)throw std::invalid_argument("Unsupported source memory interface dimensions");tag_limit=1u<<tag_bits;
  for(const auto&config:p==Profile::Compute128?source_compute_execution_config():source_rocket_execution_config()){ExecutionOwners state{config,std::vector<std::optional<PipeOwner>>(config.stages),{}};for(const auto&fu:config.iterative)state.iterative.emplace(fu.path,std::nullopt);execution.push_back(std::move(state));}
  for(const auto&[name,field]:signals){if(name.starts_with("vmu.lss.segbuf.modes_"))segment_owner.push_back({});if(name.starts_with("vu.vrf.vrf.vrf_")&&name.ends_with(".ll_write_valid"))ll_pending.push_back({});}
  if(segment_owner.empty()||ll_pending.empty())throw std::invalid_argument("Missing source segment/VRF bank dimensions");segment_mode.assign(segment_owner.size(),false);segment_drained.assign(segment_owner.size(),false);
 }
};
SaturnOwnershipLedger::SaturnOwnershipLedger(Profile p,unsigned h,std::span<const Field>a,std::span<const Field>b):impl_(std::make_unique<Impl>(p,h,a,b)){}
SaturnOwnershipLedger::~SaturnOwnershipLedger()=default;
SaturnOwnershipLedger::SaturnOwnershipLedger(SaturnOwnershipLedger&&)noexcept=default;
SaturnOwnershipLedger&SaturnOwnershipLedger::operator=(SaturnOwnershipLedger&&)noexcept=default;
std::uint64_t SaturnOwnershipLedger::edges()const{return impl_->edge;}
const std::map<std::string,std::uint64_t>&SaturnOwnershipLedger::counts()const{return impl_->counts;}
PendingOwnership SaturnOwnershipLedger::pending()const{const auto&s=*impl_;PendingOwnership out;const auto count=[](const auto&items){std::uint64_t n=0;for(const auto&item:items)n+=bool(item);return n;};out.live={{"EX_S1",bool(s.s1)},{"PFC_S2",bool(s.s2)},{"IFC",bool(s.ifc)},{"VAT",count(s.VAT)},{"load_tags",s.load_tags.size()},{"store_tags",s.store_tags.size()},{"store_requests",s.store_requests.size()},{"store_flights",s.store_flights.size()},{"TL",s.TL.size()},{"FPU",s.FPU.size()},{"load_responses",s.load_responses.size()},{"scalar_responses",s.scalar_responses.size()},{"VRF_LL",count(s.ll_pending)},{"VME_readout",count(s.readout)},{"FP8_stage0_cells",count(s.fp0)},{"FP8_stage1_cells",count(s.fp1)}};for(const auto&[name,owner]:s.seq)out.live[name]=bool(owner);for(const auto&unit:s.execution){out.live[unit.config.unit+".pipe"]=count(unit.pipe);out.live[unit.config.unit+".scalar"]=bool(unit.scalar);for(const auto&[name,owner]:unit.iterative)out.live[name]=bool(owner);}return out;}
std::vector<OwnedCommand> SaturnOwnershipLedger::live_commands()const{const auto&s=*impl_;std::map<std::pair<std::uint64_t,std::uint64_t>,OwnedCommand>refs;const auto add=[&](const OwnedCommand&c){const auto[it,inserted]=refs.emplace(std::make_pair(c.reset_epoch,c.sequence),c);if(!inserted&&it->second!=c)throw std::runtime_error("Inconsistent retained command identity");};for(const auto*c:{&s.s1,&s.s2,&s.ifc})if(*c)add(**c);for(const auto&d:s.VAT)if(d)add(d->command);for(const auto&[name,d]:s.seq)if(d)add(d->command);if(s.array_stage)add(s.array_stage->owner.command);for(const auto&items:{&s.readout})for(const auto&m:*items)if(m)add(m->owner.command);for(const auto&items:{&s.fp0,&s.fp1})for(const auto&m:*items)if(m)add(m->owner.command);for(const auto&items:{&s.LIQ,&s.SIQ,&s.segment_owner})for(const auto&d:*items)if(d)add(d->command);for(const auto&items:{&s.load_tags,&s.store_tags})for(const auto&[tag,p]:*items)add(p.owner.command);for(const auto&items:{&s.store_requests,&s.store_flights})for(const auto&p:*items)add(p.owner.command);for(const auto&[source,a]:s.TL)add(a.owner.command);for(const auto&a:s.FPU)add(a.micro.owner.command);for(const auto&d:s.load_responses)add(d.command);for(const auto&a:s.scalar_responses)add(a.command);for(const auto&w:s.ll_pending)if(w&&w->micro)add(w->micro->owner.command);for(const auto&unit:s.execution){for(const auto&p:unit.pipe)if(p)add(p->micro.owner.command);for(const auto&[name,m]:unit.iterative)if(m)add(m->owner.command);if(unit.scalar)add(unit.scalar->owner.command);}std::vector<OwnedCommand>out;for(const auto&[key,c]:refs)out.push_back(c);return out;}
std::vector<OwnershipEvent> SaturnOwnershipLedger::observe(const ReferenceInputs&i,const ReferenceOutputs&o,const ActivitySnapshot&a,const ActivitySnapshot&x,std::optional<CallerCommand>caller){
 auto&s=*impl_;if(a.hart!=s.hart||x.hart!=s.hart||a.source_edge!=s.edge||x.source_edge!=s.edge||!a.uncore_tick||a.uncore_tick!=x.uncore_tick)throw std::invalid_argument("Ownership frame identity/time mismatch");
 if(i.words.size()!=s.inputs.size()||o.words.size()!=s.outputs.size())throw std::invalid_argument("Ownership physical boundary mismatch");
 const auto read=[&](const Signal&d)->std::uint64_t{const auto&words=d.extra?x.words:a.words;if(d.index>=words.size())throw std::invalid_argument("Truncated source ownership metadata");const auto value=words[d.index];if(d.width<64&&value>>d.width)throw std::invalid_argument("Ownership source metadata exceeds physical width");return value;};
 const auto signal=[&](const std::string&name)->std::uint64_t{const auto at=s.signals.find(name);if(at==s.signals.end())throw std::invalid_argument("Unresolved required source ownership signal "+name);return read(at->second);};
 const auto input=[&](const std::string&n){return i.words.at(s.inputs.at(n));};
 const auto output=[&](const std::string&n){return o.words.at(s.outputs.at(n));};
 const auto fire=[&](const std::string&u,const std::string&port){return signal(u+".io_"+port+"_valid")&&signal(u+".io_"+port+"_ready");};
 const auto mask=[&](const std::string&name){std::vector<std::uint64_t>v;const auto at=s.wide.find(name);if(at==s.wide.end())throw std::invalid_argument("Unresolved source write mask "+name);for(const auto&f:at->second)v.push_back(read(f));return v;};
 const auto bit_count=[&](const std::string&name){std::uint64_t bits=0;for(const auto word:mask(name))bits+=std::popcount(word);return bits;};
 std::vector<OwnershipEvent> events;const auto emit=[&](std::string kind,std::string source,std::optional<OwnedCommand>command={},std::optional<OwnedDispatch>dispatch={},std::optional<std::uint64_t>micro={},std::uint64_t amount=0){++s.counts[kind];events.push_back({std::move(kind),std::move(source),s.edge,*a.uncore_tick,std::move(command),std::move(dispatch),micro,amount});};
 if(input("reset")){
  if(caller)throw std::invalid_argument("Caller EX token supplied during source reset");
  if(!s.previous_reset){sequence(s.epoch,"reset epoch");}
  if(!s.previous_reset&&(!s.TL.empty()||!s.FPU.empty()||!s.scalar_responses.empty()))throw std::runtime_error("Source reset with accepted physical transactions needs an explicit reset/abort contract");
  s.reset_seen=true;s.previous_reset=true;s.s1.reset();s.s2.reset();s.ifc.reset();s.expected_head=s.expected_tail=0;s.expected_debug=0;s.VAT.assign(s.VAT_size,{});for(auto&[name,owner]:s.seq)owner.reset();s.array_stage.reset();s.readout={};s.fp0={};s.fp1={};for(auto&owner:s.LIQ)owner.reset();for(auto&owner:s.SIQ)owner.reset();s.load_tags.clear();s.store_tags.clear();s.store_requests.clear();s.store_flights.clear();s.load_responses.clear();for(auto&owner:s.segment_owner)owner.reset();s.segment_mode.assign(s.segment_mode.size(),false);s.segment_drained.assign(s.segment_drained.size(),false);for(auto&owner:s.ll_pending)owner.reset();for(auto&unit:s.execution){unit.scalar.reset();for(auto&owner:unit.pipe)owner.reset();for(auto&[name,owner]:unit.iterative)owner.reset();}sequence(s.edge,"source edge");return events;
 }
 if(!s.reset_seen)throw std::invalid_argument("Ownership ledger requires actual source reset");s.previous_reset=false;
 // Check the continuous source-controlled allocation state; it is not restored
 // into the unit. Generation is host metadata, the real source tag stays small.
 if(signal("dis.debug_id_ctr")!=s.expected_debug||signal("dis.vat_head")!=s.expected_head||signal("dis.vat_tail")!=s.expected_tail)throw std::runtime_error("Dispatcher counter/head/tail lifetime diverged");
 for(unsigned slot=0;slot<s.VAT_size;++slot)if(bool(signal("dis.vat_valids_"+std::to_string(slot)))!=bool(s.VAT[slot]))throw std::runtime_error("Dispatcher VAT occupancy lifetime diverged");
 const bool pfc_valid=signal("vfu.pfc.io_s2_inst_valid");
 if(pfc_valid!=bool(s.s2))throw std::runtime_error("PFC S0/S1kill/S2 ownership discontinuity");
 if(s.s2&&(signal("vfu.pfc.io_s2_pc")!=s.s2->pc||signal("vfu.pfc.io_s2_inst_bits_bits")!=s.s2->instruction))throw std::runtime_error("PFC S2 PC/instruction does not match actual EX owner");
 const bool ifc_busy=signal("vfu.ifc.io_busy");if(ifc_busy!=bool(s.ifc))throw std::runtime_error("IFC ownership/busy lifetime discontinuity");
 if(s.ifc&&signal("vfu.ifc.io_pc")!=s.ifc->pc)throw std::runtime_error("IFC PC owner changed without accepted transfer");
 std::optional<OwnedCommand>current=ifc_busy?s.ifc:s.s2;
 const bool issue_fire=fire("vfu","issue");
 if(issue_fire){if(!current||!current->EX_fired)throw std::runtime_error("Backend issue lacks an accepted un-killed scalar command");if(signal("vfu.io_issue_bits_bits")!=current->instruction)throw std::runtime_error("Frontend issue instruction changed owner");emit("frontend_issue_accept","vfu.io_issue.fire",current);}
 std::optional<OwnedDispatch>allocated;
 for(bool store:{false,true}){auto&queue=store?s.SIQ:s.LIQ;for(unsigned slot=0;slot<queue.size();++slot){const auto prefix=std::string("vmu.")+(store?"siq":"liq");const bool valid=signal(prefix+"_valids_"+std::to_string(slot));if(valid&&!queue[slot])throw std::runtime_error("Source LSIQ slot became active without owned macro enqueue");if(!valid)queue[slot].reset();else if(signal(prefix+"_"+std::to_string(slot)+"_op_debug_id")!=queue[slot]->debug_id)throw std::runtime_error("Live LSIQ debug generation changed");}}
 if(fire("dis","dis")){
  if(!issue_fire||!current)throw std::runtime_error("Dispatcher fire without matching frontend command handshake");
  const auto slot=unsigned(signal("dis.io_dis_bits_vat"));const auto id=signal("dis.io_dis_bits_debug_id");
  if(slot!=s.expected_tail||id!=s.expected_debug||s.VAT.at(slot)||signal("dis.io_dis_bits_bits")!=current->instruction)throw std::runtime_error("Dispatch identity/VAT allocation collision");
  if(s.next_dispatch==std::numeric_limits<std::uint64_t>::max()||s.VAT_generation[slot]==std::numeric_limits<std::uint64_t>::max())throw std::overflow_error("Host dispatch generation exhausted");
  allocated=OwnedDispatch{s.next_dispatch++,s.edge,++s.VAT_generation[slot],slot,std::uint16_t(id),*current};s.VAT[slot]=allocated;emit("dispatch_accept","dis.io_dis.fire",current,allocated);s.expected_debug=std::uint16_t(s.expected_debug+1);s.expected_tail=(s.expected_tail+1)%s.VAT_size;
 }
 if(fire("vmu","enq")){
  if(!allocated||!fire("dis","mem")||signal("vmu.io_enq_bits_debug_id")!=allocated->debug_id)throw std::runtime_error("VMU macro enqueue has no synchronous dispatch owner");const bool store=signal("vmu.io_enq_bits_store");auto&queue=store?s.SIQ:s.LIQ;const auto slot=unsigned(signal(store?"vmu.siq_enq_ptr":"vmu.liq_enq_ptr"));if(slot>=queue.size()||queue[slot])throw std::runtime_error("LSIQ slot reused before source release");queue[slot]=allocated;emit("VMU_macro_accept","vmu.io_enq.fire",allocated->command,allocated);
 }
 // Physical memory packets retain the macro generation after scheduling VAT
 // release. Tags belong to source reservation queues, never just debug IDs.
 const auto packet_event=[&](std::string kind,std::string source,const MemPacket&packet,std::uint64_t address=0,std::uint64_t bytes=0){emit(std::move(kind),std::move(source),packet.owner.command,packet.owner);auto&e=events.back();e.memory_tag=packet.tag;e.address=address;e.bytes=bytes;};
 if(fire("vmu.lifq","reserve")){const auto slot=unsigned(signal("vmu.las.io_lsiq_id")),tag=unsigned(signal("vmu.lifq.io_reserve_bits"));if(slot>=s.LIQ.size()||!s.LIQ[slot]||tag>=s.tag_limit||s.load_tags.contains(tag))throw std::runtime_error("Load reservation tag lacks unique live LIQ generation");MemPacket packet{*s.LIQ[slot],slot,tag,bool(signal("vmu.lifq.io_entry_masked")),bool(signal("vmu.las.io_out_bits_last"))};s.load_tags.emplace(tag,packet);packet_event("VMU_load_tag_reserve","vmu.lifq.io_reserve.fire",packet);}
 if(fire("vmu.store_req_q","enq")){const auto slot=unsigned(signal("vmu.store_req_q.io_enq_bits_sifq_lsiq_id")),tag=unsigned(signal("vmu.store_req_q.io_enq_bits_request_tag"));if(slot>=s.SIQ.size()||!s.SIQ[slot]||tag>=s.tag_limit)throw std::runtime_error("Store packet enqueue lacks live SIQ generation");MemPacket packet{*s.SIQ[slot],slot,tag,bool(signal("vmu.store_req_q.io_enq_bits_sifq_masked")),bool(signal("vmu.store_req_q.io_enq_bits_sifq_last"))};packet.address=signal("vmu.store_req_q.io_enq_bits_request_addr");s.store_requests.push_back(packet);if(!packet.masked){if(s.store_tags.contains(tag))throw std::runtime_error("Store ROB reservation tag reused before source dequeue");s.store_tags.emplace(tag,packet);}packet_event("VMU_store_packet_enqueue","vmu.store_req_q.io_enq.fire",packet,*packet.address);}
 if(fire("vmu","dmem_load_req")){const auto tag=unsigned(signal("vmu.io_dmem_load_req_bits_tag"));auto at=s.load_tags.find(tag);if(at==s.load_tags.end()||at->second.masked)throw std::runtime_error("Internal load request lacks reserved unmasked owner");at->second.address=signal("vmu.io_dmem_load_req_bits_addr");packet_event("VMU_load_request_accept","vmu.io_dmem_load_req.fire",at->second,*at->second.address,s.memory_bytes);}
 if(fire("vmu","dmem_store_req")){if(s.store_requests.empty()||s.store_requests.front().masked||s.store_requests.front().tag!=signal("vmu.io_dmem_store_req_bits_tag")||s.store_requests.front().address!=signal("vmu.io_dmem_store_req_bits_addr"))throw std::runtime_error("Internal store request lacks source queue-head tag/address owner");s.store_tags.at(s.store_requests.front().tag).byte_mask=signal("vmu.io_dmem_store_req_bits_mask");packet_event("VMU_store_request_accept","vmu.io_dmem_store_req.fire",s.store_requests.front(),signal("vmu.io_dmem_store_req_bits_addr"),std::popcount(signal("vmu.io_dmem_store_req_bits_mask")));}
 // A wider internal Put can emit earlier external A beats before its internal
 // req.ready fires on the final beat. Its ROB/queue reservation already owns it.
 if(output("auto_atl_out_a_valid")&&input("auto_atl_out_a_ready")){
  const auto source=unsigned(output("auto_atl_out_a_bits_source")),opcode=unsigned(output("auto_atl_out_a_bits_opcode")),size=unsigned(output("auto_atl_out_a_bits_size"));const bool load=opcode==4;if(opcode!=0&&opcode!=1&&!load)throw std::runtime_error("Unqualified vector ATL opcode");const auto tag=source&(s.tag_limit-1);if(source>=2*s.tag_limit||bool(source&s.tag_limit)!=load)throw std::runtime_error("Vector reader/writer source-ID translation differs from pinned TLXbar");const auto&tags=load?s.load_tags:s.store_tags;const auto owner=tags.find(tag);if(owner==tags.end()||owner->second.masked)throw std::runtime_error("Accepted physical A has no reserved macro owner");const auto address=output("auto_atl_out_a_bits_address");if(size>6||(1ULL<<size)!=s.memory_bytes)throw std::runtime_error("Physical vector request size differs from source mLen");
  auto at=s.TL.find(source);if(at==s.TL.end()){if(!owner->second.address)throw std::runtime_error("Physical A lacks captured source packet address");const auto request_addr=*owner->second.address;if(address!=((request_addr&((1ULL<<35)-1))&~std::uint64_t(s.memory_bytes-1)))throw std::runtime_error("Physical A address lost reserved VMU packet owner");auto packet_mask=owner->second.byte_mask;if(!load&&!packet_mask){if(!signal("vmu.io_dmem_store_req_valid")||signal("vmu.io_dmem_store_req_bits_tag")!=tag||signal("vmu.io_dmem_store_req_bits_addr")!=request_addr)throw std::runtime_error("Physical Put precedes internal acceptance without matching presented source packet");packet_mask=signal("vmu.io_dmem_store_req_bits_mask");}const auto payload_bytes=load?s.memory_bytes:unsigned(std::popcount(*packet_mask));TLActor actor{owner->second.owner,sequence(s.next_transaction,"physical transaction"),s.edge,address,payload_bytes,tag,opcode,size,0,0,load?1u:std::max(1u,s.memory_bytes/s.bus_bytes),load?std::max(1u,s.memory_bytes/s.bus_bytes):1u,0};at=s.TL.emplace(source,actor).first;emit("TL_transaction_accept","auto_atl_out_a.fire",actor.owner.command,actor.owner);auto&e=events.back();e.transaction=actor.id;e.transport_source=source;e.memory_tag=tag;e.address=address;e.bytes=payload_bytes;}
  auto&actor=at->second;if(actor.owner.sequence!=owner->second.owner.sequence||actor.address!=address||actor.opcode!=opcode||actor.size!=size||actor.A_seen>=actor.A_total)throw std::runtime_error("Physical A identifier reused before matching completion");++actor.A_seen;if(!load)actor.A_bytes+=std::popcount(output("auto_atl_out_a_bits_mask"));emit("TL_A_beat","auto_atl_out_a.fire",actor.owner.command,actor.owner);auto&e=events.back();e.transaction=actor.id;e.transport_source=source;e.memory_tag=tag;e.address=address;e.byte_mask=output("auto_atl_out_a_bits_mask");
 }
 if(input("auto_atl_out_d_valid")&&output("auto_atl_out_d_ready")){
  const auto source=unsigned(input("auto_atl_out_d_bits_source"));auto at=s.TL.find(source);if(at==s.TL.end())throw std::runtime_error("Physical D lacks accepted source-owned transaction");auto&actor=at->second;if(input("auto_atl_out_d_bits_size")!=actor.size||input("auto_atl_out_d_bits_opcode")!=(actor.opcode==4?1u:0u)||actor.A_seen!=actor.A_total||actor.D_seen>=actor.D_total)throw std::runtime_error("Physical D contradicts owned request/beat lifetime");++actor.D_seen;emit("TL_D_beat","auto_atl_out_d.fire",actor.owner.command,actor.owner);auto&e=events.back();e.transaction=actor.id;e.transport_source=source;e.memory_tag=actor.tag;e.address=actor.address;if(actor.D_seen==actor.D_total){if(actor.opcode!=4&&actor.A_bytes!=actor.bytes)throw std::runtime_error("Physical Put masks changed source packet byte accounting");emit("TL_transaction_complete","matching final auto_atl_out_d.fire",actor.owner.command,actor.owner);auto&e=events.back();e.transaction=actor.id;e.transport_source=source;e.memory_tag=actor.tag;e.address=actor.address;e.bytes=actor.bytes;s.TL.erase(at);}
 }
 if(signal("vmu.io_dmem_load_resp_valid")){const auto tag=unsigned(signal("vmu.io_dmem_load_resp_bits_tag"));const auto at=s.load_tags.find(tag);if(at==s.load_tags.end()||at->second.masked)throw std::runtime_error("VMU load response lacks source reservation owner");packet_event("VMU_load_response","vmu.io_dmem_load_resp_valid",at->second);}
 if(signal("vmu.io_dmem_store_ack_valid")){const auto tag=unsigned(signal("vmu.io_dmem_store_ack_bits_tag"));auto at=s.store_tags.find(tag);if(at==s.store_tags.end()||at->second.ack)throw std::runtime_error("VMU store acknowledgement lacks unique reserved owner");at->second.ack=true;packet_event("VMU_store_ack","vmu.io_dmem_store_ack_valid",at->second);}
 if(fire("vmu.store_req_q","deq")){if(s.store_requests.empty())throw std::runtime_error("Source store queue dequeue lacks packet owner");auto packet=s.store_requests.front();s.store_requests.pop_front();if(!packet.masked&&!fire("vmu","dmem_store_req"))throw std::runtime_error("Store packet dequeued without physical internal acceptance");s.store_flights.push_back(packet);}
 if(s.store_requests.size()>2)throw std::runtime_error("Source two-entry store request queue exceeded capacity");
 if(fire("vmu.sifq","deq")){if(s.store_flights.empty())throw std::runtime_error("Source SIFQ dequeue lacks owned packet");const auto packet=s.store_flights.front();s.store_flights.pop_front();if(!packet.masked){auto at=s.store_tags.find(packet.tag);if(at==s.store_tags.end()||!at->second.ack||at->second.owner.sequence!=packet.owner.sequence)throw std::runtime_error("Ordered store ROB dequeue lacks matching acknowledgement generation");s.store_tags.erase(at);}packet_event("VMU_store_packet_complete","vmu.sifq.io_deq.fire",packet);}
 if(fire("vmu.lifq","deq")){const auto tag=unsigned(signal("vmu.lifq.deq_ptr_value"));auto at=s.load_tags.find(tag);if(at==s.load_tags.end())throw std::runtime_error("Load order dequeue lacks reserved macro generation");packet_event("VMU_load_packet_complete","vmu.lifq.io_deq.fire",at->second);s.load_tags.erase(at);}
 // The two-entry response queue and configured segment-buffer slots retain
 // full macro generations. The RTL debug ID alone is not a unique owner.
 if(bool(signal("vmu.io_vu_lresp_q.io_deq_valid"))!=!s.load_responses.empty())throw std::runtime_error("Load-response queue occupancy lost macro generation");
 std::optional<OwnedDispatch> delivered_load;
 if(signal("vmu.io_vu_lresp_q.do_deq")){if(s.load_responses.empty())throw std::runtime_error("Load-response dequeue lacks accepted enqueue");delivered_load=s.load_responses.front();s.load_responses.pop_front();emit("VMU_load_response_deliver","vmu.io_vu_lresp_q.do_deq",delivered_load->command,delivered_load);}
 bool segment_busy=false;
 for(unsigned n=0;n<s.segment_owner.size();++n){const bool mode=signal("vmu.lss.segbuf.modes_"+std::to_string(n));if(s.segment_mode[n]&&!mode){if(!s.segment_drained[n])throw std::runtime_error("Segment slot released without accepted source output");s.segment_owner[n].reset();}if(mode&&!s.segment_owner[n])throw std::runtime_error("Segment-buffer output lacks previously accepted input generation");s.segment_mode[n]=mode;s.segment_drained[n]=false;segment_busy|=mode;}
 const auto in_segment=s.segment_owner.size()==1?0u:unsigned(signal("vmu.lss.segbuf.in_sel"));
 const auto out_segment=s.segment_owner.size()==1?0u:unsigned(signal("vmu.lss.segbuf.out_sel"));
 if(in_segment>=s.segment_owner.size()||out_segment>=s.segment_owner.size())throw std::runtime_error("Segment-buffer selector exceeds configured slots");
 if(signal("vmu.lss.segbuf.wrow")){const auto slot=unsigned(signal("vmu.liq_lss_ptr"));if(slot>=s.LIQ.size()||!s.LIQ[slot]||s.segment_mode[in_segment])throw std::runtime_error("Segment-buffer accepted input without writable live LIQ generation");auto&owner=s.segment_owner[in_segment];if(owner&&owner->sequence!=s.LIQ[slot]->sequence)throw std::runtime_error("Segment-buffer partial rows mix distinct macro generations");owner=s.LIQ[slot];emit("VMU_segment_input_accept","vmu.lss.segbuf.wrow!=0 (source-qualified in.fire)",owner->command,owner);}
 if(signal("vmu.io_vu_lresp_q.do_enq")){std::optional<OwnedDispatch>owner;if(segment_busy){owner=s.segment_owner[out_segment];s.segment_drained[out_segment]=true;}else{const auto slot=unsigned(signal("vmu.liq_lss_ptr"));if(slot<s.LIQ.size())owner=s.LIQ[slot];}if(!owner)throw std::runtime_error("Load-response enqueue lacks source segment/LIQ generation");s.load_responses.push_back(*owner);emit("VMU_load_response_enqueue","vmu.io_vu_lresp_q.do_enq",owner->command,owner);}
 if(s.load_responses.size()>2)throw std::runtime_error("Source load-response queue exceeded depth two");
 // Consume old active sequencer identities before installing same-edge accepts.
 std::map<std::string,Micro>issued;
 for(auto&[name,owner]:s.seq){
  const bool valid=signal(name+".valid");
  if(valid&&!owner)throw std::runtime_error("Sequencer became active without an accepted source owner "+name);
  if(!valid&&owner){emit("sequencer_inactive",name+".valid=0",owner->command,owner);owner.reset();}
  if(owner&&signal(name+".io_vat")!=owner->VAT)throw std::runtime_error("Active sequencer VAT generation changed "+name);
  if(owner&&s.signals.contains(name+".inst_debug_id")&&signal(name+".inst_debug_id")!=owner->debug_id)throw std::runtime_error("Sequencer debug ID changed active owner "+name);
  const bool accepted=name=="vu.vos"?signal(name+".io_iss_valid"):fire(name,"iss");
  if(accepted){if(!owner)throw std::runtime_error("Microissue without live sequencer owner");Micro micro{sequence(s.next_micro,"microissue"),*owner};issued.emplace(name,micro);emit("microissue",name+".io_iss.fire",owner->command,owner,micro.id);}
 }
 if(issued.contains("vu.vls")!=bool(delivered_load))throw std::runtime_error("Load microissue and actual response dequeue acceptance differ");
 if(delivered_load&&issued.at("vu.vls").owner.sequence!=delivered_load->sequence)throw std::runtime_error("Load VRF microissue consumed another macro generation");
 std::map<unsigned,VRFWrite> normal_writes,iter_writes;
 std::optional<ScalarActor> scalar_enqueue;
 // Propagate provenance through the exact source finite pipe-valid recurrence.
 // This metadata follows accepted micro-ops; it does not supply pipe state.
 unsigned execution_index=0;
 for(auto&unit:s.execution){const auto&config=unit.config;std::optional<PipeOwner>write_owner;
  for(unsigned n=0;n<unit.pipe.size();++n){const auto prefix=config.unit+".io_pipe_hazards_"+std::to_string(n);if(bool(signal(prefix+"_valid"))!=bool(unit.pipe[n]))throw std::runtime_error("Execution pipe valid lost causal owner "+config.unit);if(unit.pipe[n]){const auto&owner=*unit.pipe[n];if(signal(prefix+"_bits_vat")!=owner.micro.owner.VAT)throw std::runtime_error("Execution pipe VAT changed generation "+config.unit);if(owner.depth==n){if(write_owner)throw std::runtime_error("Multiple source pipe completions share a write slot");write_owner=owner;}}}
  if(signal(config.unit+".io_pipe_write_valid")){if(!write_owner)throw std::runtime_error("RVV pipe write lacks accepted micro-op provenance");const auto&m=write_owner->micro;emit("RVV_pipe_write_port",config.unit+".io_pipe_write_valid",m.owner.command,m.owner,m.id,bit_count(config.unit+".io_pipe_write_bits_mask"));const auto eg=s.profile==Profile::Compute128?unsigned(signal("vu.vrf.io_pipe_writes_"+std::to_string(execution_index)+"_bits_eg")):unsigned(signal("vu.vrf.vrf.vrf_0.write_bits_eg"));normal_writes.emplace(execution_index,VRFWrite{m,eg,mask(config.unit+".io_pipe_write_bits_mask")});}
  if(signal(config.unit+".io_acc_write_valid")){if(!write_owner)throw std::runtime_error("RVV reduction feedback lacks accepted pipe owner");const auto&m=write_owner->micro;emit("RVV_acc_feedback",config.unit+".io_acc_write_valid",m.owner.command,m.owner,m.id);}
  if(execution_index==0){const auto mask_unit=config.unit+".fus_3";if(bool(signal(mask_unit+".scalar_wb_busy"))!=bool(unit.scalar))throw std::runtime_error("Scalar vector-result valid lost actual MaskUnit pipe owner");const bool scalar_fire=fire(config.unit,"scalar_write");if(scalar_fire){if(!unit.scalar||!fire(mask_unit,"scalar_write")||scalar_enqueue)throw std::runtime_error("Backend scalar response lacks unique accepted MaskUnit owner");const auto&m=*unit.scalar;if(signal(mask_unit+".io_scalar_write_bits_rd")!=((m.owner.command.instruction>>7)&31))throw std::runtime_error("MaskUnit scalar response destination differs from owner instruction");scalar_enqueue=ScalarActor{m.owner.command,m.owner,m.id,sequence(s.next_transaction,"physical transaction"),s.edge};emit("scalar_response_accept",config.unit+".io_scalar_write.fire",m.owner.command,m.owner,m.id);events.back().transaction=scalar_enqueue->id;unit.scalar.reset();}
   if(!unit.pipe.empty()&&unit.pipe[0]&&(unit.pipe[0]->fu_sel&(1ULL<<3))&&unit.pipe[0]->tail){const auto&m=unit.pipe[0]->micro;const auto raw=m.owner.command.instruction,funct3=(raw>>12)&7;const bool scalar_op=funct3==1||(funct3==2&&!((raw>>28)&1));if(scalar_op&&!scalar_fire){if(unit.scalar)throw std::runtime_error("MaskUnit tail overwrites an undelivered scalar-result owner");unit.scalar=m;}}
  }
  if(s.profile==Profile::Rocket256){
   // Shared scalar FMA source request is its actual pipe0 valid; responses are
   // returned by the single source FPU port in order, also checked against the
   // original final-stage FU token. No fixed response delay is generated here.
   if(output("io_fp_req_valid")&&input("io_fp_req_ready")){if(unit.pipe.empty()||!unit.pipe[0]||!(unit.pipe[0]->fu_sel&(1ULL<<7)))throw std::runtime_error("Shared FPU request lacks actual pipe0 FMA owner");const auto&m=unit.pipe[0]->micro;FPUActor actor{m,sequence(s.next_transaction,"physical transaction"),s.edge};s.FPU.push_back(actor);emit("shared_FPU_accept","io_fp_req.fire",m.owner.command,m.owner,m.id);events.back().transaction=actor.id;}
   if(input("io_fp_resp_valid")){if(s.FPU.empty()||!write_owner||!(write_owner->fu_sel&(1ULL<<7))||write_owner->micro.id!=s.FPU.front().micro.id)throw std::runtime_error("Shared FPU response lacks matching source final-stage owner");const auto actor=s.FPU.front();s.FPU.pop_front();const auto&m=actor.micro;emit("shared_FPU_complete","io_fp_resp_valid + source final FU pipe token",m.owner.command,m.owner,m.id);events.back().transaction=actor.id;}
  }
  unsigned iterative_writes=0;
  for(auto&[name,owner]:unit.iterative){if(fire(name,"write")){if(!owner)throw std::runtime_error("Iterative FU write lacks accepted micro-op owner "+name);const auto&m=*owner;emit("RVV_iter_write_port",name+".io_write.fire",m.owner.command,m.owner,m.id,bit_count(config.unit+".io_iter_write_bits_mask"));const auto eg=s.profile==Profile::Compute128?unsigned(signal("vu.vrf.io_iter_writes_"+std::to_string(execution_index)+"_bits_eg")):unsigned(signal("vu.vrf.vrf.ll_arb.io_out_bits_eg"));iter_writes.emplace(execution_index,VRFWrite{m,eg,mask(config.unit+".io_iter_write_bits_mask")});owner.reset();++iterative_writes;}}
  if(iterative_writes>1||bool(iterative_writes)!=fire(config.unit,"iter_write"))throw std::runtime_error("Iterative output arbiter ownership does not match actual accepted write");
  const bool accepted=fire(config.unit,"iss");const auto micro=issued.find(config.sequencer);if(accepted!=(micro!=issued.end()))throw std::runtime_error("Execution-unit accept differs from matching source sequencer microissue");
  std::optional<PipeOwner>next;const auto fu=accepted?signal(config.unit+".io_iss_bits_fu_sel"):0;
  if(accepted){if(signal(config.unit+".io_iss_bits_vat")!=micro->second.owner.VAT)throw std::runtime_error("Execution-unit accepted wrong VAT generation");if(fu&config.pipe_mask){const auto depth=unsigned(signal(config.unit+".io_iss_bits_pipe_depth"));if(depth>=unit.pipe.size())throw std::runtime_error("Source pipe depth exceeds configured finite pipeline");next=PipeOwner{micro->second,depth,fu,bool(signal(config.unit+".io_iss_bits_tail"))};}}
  for(auto&[name,owner]:unit.iterative){const auto index=std::stoul(name.substr(name.rfind('_')+1));if(accepted&&(fu&(1ULL<<index))){if(owner)throw std::runtime_error("Iterative FU accepted a second owner before write completion");owner=micro->second;}}
  for(unsigned n=unit.pipe.size()-1;n>0;--n)unit.pipe[n]=unit.pipe[n-1]&&unit.pipe[n-1]->depth!=n-1?unit.pipe[n-1]:std::nullopt;unit.pipe[0]=next;
  ++execution_index;
 }
 // Scheduling release is not physical completion. Preserve copied owner tokens
 // in real pipelines after the finite VAT slot has become reusable.
 bool head_advance=s.expected_head!=signal("dis.vat_tail")&&!s.VAT[s.expected_head];
 for(unsigned n=0;n<(s.profile==Profile::Compute128?5u:3u);++n){const auto prefix="dis.io_vat_release_"+std::to_string(n);if(!signal(prefix+"_valid"))continue;const auto slot=unsigned(signal(prefix+"_bits"));if(slot>=s.VAT_size||!s.VAT[slot]||(allocated&&slot==allocated->VAT))throw std::runtime_error("VAT release without a live old generation");auto owner=*s.VAT[slot];emit("VAT_release","dis.io_vat_release_"+std::to_string(n),owner.command,owner);if(slot==s.expected_head)head_advance=true;s.VAT[slot].reset();}
 if(head_advance)s.expected_head=(s.expected_head+1)%s.VAT_size;
 if(s.profile==Profile::Compute128){
  unsigned readout_bits=0;for(unsigned n=0;n<6;++n)if(s.readout[n])readout_bits|=1u<<n;if(signal("vu.vos.mvout_valids")!=readout_bits)throw std::runtime_error("VME readout owner stages diverged from actual source valid stages");
  if(signal("vu.vos.io_write_valid")){if(!s.readout[5])throw std::runtime_error("VME VRF write without readout owner");const auto&m=*s.readout[5];emit("VME_VRF_write","vu.vos.io_write_valid",m.owner.command,m.owner,m.id,bit_count("vu.vos.io_write_mask"));normal_writes.emplace(2,VRFWrite{m,unsigned(signal("vu.vrf.io_pipe_writes_2_bits_eg")),mask("vu.vos.io_write_mask")});}
  std::map<std::uint64_t,std::pair<Micro,std::uint64_t>>completions;std::array<std::optional<Micro>,256>next_fp0{};unsigned MACs=0;
  for(unsigned cell=0;cell<256;++cell){const auto&cs=s.cell_signals[cell];if(bool(read(cs.stage0))!=bool(s.fp0[cell])||bool(read(cs.stage1))!=bool(s.fp1[cell]))throw std::runtime_error("Physical FP8 valid tail lost causal owner");if(s.fp1[cell]){const auto&m=*s.fp1[cell];auto[it,inserted]=completions.try_emplace(m.id,std::make_pair(m,0));++it->second.second;}const bool active=read(cs.macc)&&read(cs.row)&&read(cs.col);if(active){if(!s.array_stage)throw std::runtime_error("Array MAC lacks preceding accepted VME microissue");++MACs;if(signal("vu.vopu_ctrl_reg_fp8"))next_fp0[cell]=s.array_stage;}}
  if(MACs){const auto&m=*s.array_stage;emit(signal("vu.vopu_ctrl_reg_fp8")?"FP8_MAC_accept":"INT8_MAC_edge","vu.vopu physical cell enables",m.owner.command,m.owner,m.id,MACs);}
  for(const auto&[id,row]:completions){const auto&[m,count]=row;emit("FP8_MAC_complete","physical cell fma.io_validout_pipe_v",m.owner.command,m.owner,m.id,count);}
  for(unsigned cell=0;cell<s.numeric_cells.size();++cell){const auto&n=s.numeric_cells[cell];const bool fp=bool(s.fp1[cell]);const unsigned current=read(n.index),delayed=fp?unsigned(read(n.fp_index)):0;
   const auto write=[&](const char*kind,const Micro&m,unsigned entry,std::uint64_t value){if(entry>=16)throw std::runtime_error("Physical MRF index exceeds source register file");emit(kind,"OuterProductCell per-entry write priority",m.owner.command,m.owner,m.id,1);auto&e=events.back();e.mrf_cell=cell;e.mrf_entry=entry;e.bit_mask={0xffffffffULL};e.data_words={value};};
   if(fp)write("MRF_FP8_commit",*s.fp1[cell],delayed,read(n.sum_fp8));
   const bool integer=read(n.macc)&&!read(n.fp8),zero=read(n.zero),move=read(n.mvin);
   if((integer||zero||move)&&(!fp||current!=delayed)){if(!s.array_stage)throw std::runtime_error("Physical MRF write lacks preceding VME microissue owner");write(integer?"MRF_INT8_commit":zero?"MRF_zero_commit":"MRF_mvin_commit",*s.array_stage,current,integer?read(n.sum_int):zero?0:read(n.mvin_data));}
  }
  s.fp1=s.fp0;s.fp0=next_fp0;
  for(unsigned n=5;n>0;--n)s.readout[n]=s.readout[n-1];s.readout[0].reset();
  if(signal("vu.vos._mvout_valids_T_1")){const auto at=issued.find("vu.vos");if(at==issued.end())throw std::runtime_error("VME readout injection lacks accepted microissue");const unsigned stage=signal("vu.vos.tss_idx")&3;if(s.readout[stage])throw std::runtime_error("VME readout owner collision; unresolved source scheduling boundary");s.readout[stage]=at->second;}
  s.array_stage=issued.contains("vu.vos")?std::optional<Micro>(issued.at("vu.vos")):std::nullopt;
 }
 // RegisterFileBank's normal write is combinational on this edge. Only its
 // low-latency input has a one-entry holding buffer. Follow the real priority
 // and accepted payload, preserving provenance across normal-write conflicts.
 const unsigned banks=s.ll_pending.size(),ll_ports=s.execution.size()+2;
 for(unsigned bank=0;bank<banks;++bank){
  const auto path="vu.vrf.vrf.vrf_"+std::to_string(bank);
  const bool normal=signal(path+".io_write_valid"),old_ll=signal(path+".ll_write_valid");
  if(old_ll!=bool(s.ll_pending[bank]))throw std::runtime_error("VRF LL buffer valid lost accepted owner");
  if(old_ll&&(signal(path+".ll_write_bits_eg")!=s.ll_pending[bank]->eg/banks||mask(path+".ll_write_bits_mask")!=s.ll_pending[bank]->mask))throw std::runtime_error("VRF LL buffered payload changed owner");
  std::optional<VRFWrite>normal_owner;
  for(const auto&[port,w]:normal_writes)if(w.eg%banks==bank){if(normal_owner)throw std::runtime_error("Two source normal-write owners collide on VRF bank");normal_owner=w;}
  if(normal!=bool(normal_owner))throw std::runtime_error("VRF physical normal port lacks matching producer");
  std::optional<unsigned>selected;unsigned selected_eg=0;
  for(unsigned port=0;port<ll_ports;++port){const auto global="vu.vrf.vrf.io_ll_writes_"+std::to_string(port);if(!signal(global+"_valid"))continue;const auto eg=(s.profile==Profile::Rocket256&&port==2)?unsigned(signal("vu.vrf.vrf.ll_arb.io_out_bits_eg")):unsigned(signal(global+"_bits_eg"));if(eg%banks==bank){selected=port;selected_eg=eg;break;}}
  const bool ll_valid=signal(path+".io_ll_write_valid"),ll_ready=signal(path+".io_ll_write_ready");
  if(ll_valid!=bool(selected)||ll_ready!=(!normal||!old_ll))throw std::runtime_error("VRF LL arbiter acceptance differs from source bank priority");
  std::optional<VRFWrite>incoming;
  if(ll_valid&&ll_ready){
   if(signal(path+".io_ll_write_bits_eg")!=selected_eg/banks)throw std::runtime_error("VRF LL arbiter selected another element group");
   if(*selected==0){auto bits=mask(path+".write_bits_mask");std::fill(bits.begin(),bits.end(),~0ULL);incoming=VRFWrite{{},selected_eg,std::move(bits),true};}
   else if(*selected==1){if(!issued.contains("vu.vls")||!delivered_load)throw std::runtime_error("VRF load LL accept lacks delivered macro/micro owner");incoming=VRFWrite{issued.at("vu.vls"),selected_eg,mask("vu.vrf.vrf.io_ll_writes_1_bits_mask")};}
   else{const auto at=iter_writes.find(*selected-2);if(at==iter_writes.end())throw std::runtime_error("VRF iterative LL accept lacks accepted FU owner");incoming=at->second;}
   if(incoming->eg!=selected_eg)throw std::runtime_error("VRF LL producer element group differs from selected bank payload");
   const auto&m=incoming->micro;emit(incoming->scrub?"VRF_scrub_accept":"VRF_LL_accept",path+".io_ll_write.fire",m?std::optional<OwnedCommand>(m->owner.command):std::nullopt,m?std::optional<OwnedDispatch>(m->owner):std::nullopt,m?std::optional<std::uint64_t>(m->id):std::nullopt);events.back().bank=bank;events.back().element_group=incoming->eg;events.back().bit_mask=incoming->mask;
  }
  const auto physical=normal?normal_owner:old_ll?s.ll_pending[bank]:incoming;
  if(bool(signal(path+".write_valid"))!=bool(physical))throw std::runtime_error("VRF physical commit lacks accepted normal/buffered/LL owner");
  if(physical){if(signal(path+".write_bits_eg")!=physical->eg/banks||mask(path+".write_bits_mask")!=physical->mask)throw std::runtime_error("VRF physical commit target/mask lost producer owner");const auto&m=physical->micro;std::uint64_t count=0;for(auto word:physical->mask)count+=std::popcount(word);emit(physical->scrub?"VRF_scrub_commit":"VRF_bank_commit",path+".write_valid",m?std::optional<OwnedCommand>(m->owner.command):std::nullopt,m?std::optional<OwnedDispatch>(m->owner):std::nullopt,m?std::optional<std::uint64_t>(m->id):std::nullopt,count);events.back().bank=bank;events.back().element_group=physical->eg;events.back().bit_mask=physical->mask;if(s.wide.contains(path+".write_bits_data")){events.back().data_words=mask(path+".write_bits_data");for(unsigned n=0;n<events.back().data_words.size();++n)events.back().data_words[n]&=physical->mask.at(n);}}
  if(normal){if(!old_ll)s.ll_pending[bank]=incoming;}else s.ll_pending[bank]=old_ll?incoming:std::nullopt;
 }
 // Both configured integrations use a real depth-two scalar-response queue.
 // A zero-VL dispatcher response bypasses VAT; it still has the exact accepted
 // frontend command and must not borrow the preceding backend instruction PC.
 const bool backend_scalar=fire("scalar_arb","in_0"),zero_scalar=fire("scalar_arb","in_1");
 if(backend_scalar!=bool(scalar_enqueue)||backend_scalar&&zero_scalar)throw std::runtime_error("Integration scalar-response arbiter lost source ownership");
 if(zero_scalar){if(!issue_fire||!current||!fire("dis","scalar_resp")||scalar_enqueue)throw std::runtime_error("Zero-VL scalar response lacks actual frontend command");scalar_enqueue=ScalarActor{*current,{},{},sequence(s.next_transaction,"physical transaction"),s.edge};emit("scalar_response_accept","scalar_arb.io_in_1.fire (dispatcher zero-VL)",current);events.back().transaction=scalar_enqueue->id;}
 const std::string response=s.profile==Profile::Compute128?"io_resp":"io_core_resp";
 if(bool(output(response+"_valid"))!=!s.scalar_responses.empty())throw std::runtime_error("Scalar response queue occupancy lost accepted command");
 if(output(response+"_valid")&&input(response+"_ready")){const auto owner=s.scalar_responses.front();s.scalar_responses.pop_front();if(output(response+"_bits_rd")!=((owner.command.instruction>>7)&31)||s.edge<=owner.edge)throw std::runtime_error("Physical scalar response destination/latency contradicts accepted owner");emit("scalar_response_complete",response+".fire",owner.command,owner.dispatch,owner.micro);events.back().transaction=owner.id;events.back().scalar_rd=output(response+"_bits_rd");events.back().data_words={output(response+"_bits_data")};events.back().bit_mask={~0ULL};}
 if(scalar_enqueue)s.scalar_responses.push_back(*scalar_enqueue);
 if(s.scalar_responses.size()>2)throw std::runtime_error("Source scalar-response queue exceeded depth two");
 for(auto&[name,owner]:s.seq){
  if(fire(name,"dis")){const auto slot=unsigned(signal(name+".io_dis_bits_vat"));if(slot>=s.VAT_size||!s.VAT[slot])throw std::runtime_error("Sequencer accept lacks live dispatch generation "+name);const auto next=*s.VAT[slot];if(signal(name+".io_dis_bits_bits")!=next.command.instruction)throw std::runtime_error("Sequencer instruction does not match dispatch owner "+name);if(s.signals.contains(name+".io_dis_bits_debug_id")&&signal(name+".io_dis_bits_debug_id")!=next.debug_id)throw std::runtime_error("Sequencer accepted wrong debug generation "+name);owner=next;emit("sequencer_accept",name+".io_dis.fire",next.command,next);}
 }
 if(signal("vfu.ifc.io_in_valid")){if(!s.s2||!s.s2->EX_fired||ifc_busy||signal("vfu.ifc.io_in_bits_pc")!=s.s2->pc)throw std::runtime_error("IFC replay transfer lacks exact PFC S2 owner");s.ifc=s.s2;emit("IFC_owner_transfer","vfu.ifc.io_in_valid",s.ifc);}
 else if(ifc_busy&&(signal("vfu.ifc.io_retire")||signal("vfu.ifc.io_xcpt_valid"))){emit("IFC_front_end","vfu.ifc.io_retire/xcpt_valid",s.ifc);s.ifc.reset();}
 if(s.s2&&signal("vfu.pfc.io_s2_retire"))emit("PFC_front_permission","vfu.pfc.io_s2_retire",s.s2);
 const bool kill=input(s.profile==Profile::Compute128?"io_mem_kill":"io_core_killm")||(s.profile==Profile::Compute128&&s.s1&&!s.s1->EX_fired);
 if(s.s1&&kill)emit("MEM_kill","source PFC S1 kill",s.s1);
 s.s2=kill?std::nullopt:s.s1;
 std::optional<OwnedCommand>next;
 if(signal("vfu.pfc.io_s0_in_valid")){
  const auto pc=input(s.profile==Profile::Compute128?"io_ex_uop_pc":"io_core_ex_pc");const auto raw=std::uint32_t(input(s.profile==Profile::Compute128?"io_ex_uop_inst":"io_core_ex_inst"));const bool fired=s.profile==Profile::Rocket256||input("io_ex_fire");
  if(!input(s.profile==Profile::Compute128?"io_ex_valid":"io_core_ex_valid")||!output(s.profile==Profile::Compute128?"io_ex_ready":"io_core_ex_ready"))throw std::runtime_error("PFC S0 accept contradicts physical EX boundary");
  if(caller&&(caller->pc!=pc||caller->instruction!=raw))throw std::invalid_argument("Caller command metadata does not match accepted source EX");
  next=OwnedCommand{s.hart,s.epoch,sequence(s.next_command,"command"),s.edge,pc,raw,fired,caller?std::optional<std::uint64_t>(caller->node):std::nullopt};emit("EX_candidate","vfu.pfc.io_s0_in_valid",next);if(fired)emit("EX_fire","physical EX fire",next);
 }else if(caller)throw std::invalid_argument("Caller node supplied without actual accepted EX command");
 s.s1=next;sequence(s.edge,"source edge");return events;
}
}
