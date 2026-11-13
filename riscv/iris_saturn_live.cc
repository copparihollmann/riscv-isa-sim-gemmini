// New finite live source-unit integration; older/native published paths unchanged.
#include "iris_timing_adapter.h"
#include "processor.h"
#include <algorithm>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <set>
namespace {thread_local iris_timing_adapter*saturn_handler_owner=nullptr;
uint64_t width_mask(unsigned width){return width==64?~uint64_t(0):(uint64_t(1)<<width)-1;}
uint64_t transport_mask(const iris_definedness::Value<uint64_t>&value){uint64_t out=0;for(unsigned b=0;b<8;++b)out|=uint64_t(value.known[b])<<(b*8);return out;}
}
void iris_timing_adapter::saturn_initialize(){
 saturn_=std::make_unique<iris_saturn_live_state>();auto&s=*saturn_;s.manifest_path=profile_.saturn_manifest;
 std::ifstream file(s.manifest_path);if(!file)throw std::runtime_error("IRIS_SATURN_ADMISSION_FILE_MISSING");std::string line;bool schema=false,hart=false;
 while(std::getline(file,line)){std::istringstream in(line);std::string key,a,b,extra;in>>key>>a;if(key=="schema"&&a=="iris.saturn.finite_integer_K1.v1"&&!schema)schema=true;else if(key=="hart"&&a=="0"&&!hart)hart=true;else if(key=="elf_sha256"&&a.size()==64&&s.elf_identity.empty())s.elf_identity=a;else if(key=="admission_sha256"&&a.size()==64&&s.manifest_identity.empty())s.manifest_identity=a;else if(key=="command"&&(in>>b)){size_t used=0;auto pc=std::stoull(a,&used,0);if(used!=a.size())throw std::runtime_error("invalid source unit PC");auto raw=std::stoull(b,&used,0);if(used!=b.size()||raw>UINT32_MAX||!s.commands.emplace(pc,raw).second)throw std::runtime_error("invalid source unit encoding");}else throw std::runtime_error("IRIS_SATURN_ADMISSION_SCHEMA");if(in>>extra)throw std::runtime_error("IRIS_SATURN_ADMISSION_TRAILING_FIELD");}
 if(!schema||!hart||s.commands.size()!=9||s.elf_identity.empty()||s.manifest_identity.empty())throw std::runtime_error("IRIS_SATURN_EXACT_NINE_COMMAND_ADMISSION_REQUIRED");
 for(const auto&[pc,raw]:s.commands){const auto op=raw&127,f3=(raw>>12)&7;if(op==7||op==39)throw std::runtime_error("IRIS_SATURN_FIRST_VECTOR_MEMORY_SERVICE_NOT_CONNECTED");if(f3==1||f3==5)throw std::runtime_error("IRIS_SATURN_FIRST_SHARED_FPU_OR_FP_COMPUTE_NOT_ADMITTED");}
 iris::saturn::LiveBridgeCapability cap{s.manifest_identity,{}};cap.inactive_payload=iris::saturn::InactiveInputConvention::SourceQualifiedInactivePayload;for(const auto&[pc,raw]:s.commands)cap.instructions.push_back({~uint32_t(0),raw});
 s.unit=std::make_unique<iris::saturn::SaturnLiveBridge>(iris::saturn::Profile::Compute128,0,profile_.frontend_seed,cap);s.oracle=std::make_unique<iris_saturn_oracle>(*cores_[0]);
 const auto fields=iris::saturn::SaturnTimingCut::input_fields(iris::saturn::Profile::Compute128);for(unsigned i=0;i<fields.size();++i){s.input_fields.emplace(std::string(fields[i].name),i);s.inputs.values.words.push_back(0);s.inputs.known_bits.push_back(width_mask(fields[i].word_width));}for(unsigned i=0;i<iris::saturn::SaturnTimingCut::output_fields(iris::saturn::Profile::Compute128).size();++i)s.output_fields.emplace(std::string(iris::saturn::SaturnTimingCut::output_fields(iris::saturn::Profile::Compute128)[i].name),i);
 // Explicit source component reset reference. These are reset edges, not a
 // shortcut over guest execution; subsequent scrub runs on every core edge.
 s.inputs.values.words.at(s.input_fields.at("reset"))=1;for(unsigned edge=0;edge<2;++edge){s.unit->evaluate(s.inputs);s.outputs=s.unit->sample();s.unit->commit(edge*profile_.harts[0].divider);}s.inputs.values.words.at(s.input_fields.at("reset"))=0;
 clock_.configure_resource("saturn0.RRD-to-EX",1);clock_.configure_resource("saturn0.front-command",1);clock_.configure_resource("saturn0.physical-VRF",4);clock_.configure_resource("saturn0.physical-MRF",256);clock_.configure_resource("saturn0.physical-INT8-MAC",256);
}
void iris_timing_adapter::saturn_prepare(){
 auto&s=*saturn_;if(s.prepared||s.next_edge>clock_.now())return;if(s.next_edge<clock_.now())throw std::logic_error("IRIS_SATURN_SKIPPED_SOURCE_CORE_EDGE");
 auto&real=*cores_[0];if(!s.unit->live_commands().empty()&&real.iris_pipeline_interrupt_exception())throw std::runtime_error("IRIS_SATURN_PENDING_PRECISE_INTERRUPT_UNMODELED");auto set=[&](const std::string&name,uint64_t value,uint64_t known){auto i=s.input_fields.at(name);const auto f=iris::saturn::SaturnTimingCut::input_fields(iris::saturn::Profile::Compute128)[i];s.inputs.values.words[i]=value;s.inputs.known_bits[i]=known&width_mask(f.word_width);};auto full=[&](const std::string&name,uint64_t value){set(name,value,~uint64_t(0));};
 full("io_status_prv",real.get_state()->prv);full("io_resp_ready",1);full("io_mem_kill",0);full("io_ex_fire",0);full("io_ex_valid",0);
 // Knownness is transported, not inferred from numeric zero. The successor
 // wrapper must prove canonicalization of ignored/inactive input payloads.
 const auto&v=real.VU;const bool configured=!v.vill;const auto vk=configured?~uint64_t(0):0;
 set("io_ex_vconfig_vl",v.vl->read(),vk);set("io_ex_vconfig_vtype_vill",v.vill,~uint64_t(0));set("io_ex_vconfig_vtype_tm",v.tm,vk);set("io_ex_vconfig_vtype_tk",v.tk,vk);set("io_ex_vconfig_vtype_vtwiden",v.widen==4?3:v.widen==2?2:v.widen==1?1:0,vk);set("io_ex_vconfig_vtype_altfmt",v.altfmt,vk);set("io_ex_vconfig_vtype_vma",v.vma,vk);set("io_ex_vconfig_vtype_vta",v.vta,vk);unsigned sew=0;for(auto bits=v.vsew;bits>8;bits>>=1)++sew;set("io_ex_vconfig_vtype_vsew",sew,vk);set("io_ex_vconfig_vtype_vlmul_sign",(v.vtype->read()>>2)&1,vk);set("io_ex_vconfig_vtype_vlmul_mag",v.vtype->read()&3,vk);
 set("io_ex_vstart",v.vstart->read(),v.vstart->iris_known_bits());set("io_com_vxrm",v.vxrm->read(),v.vxrm->iris_known_bits());set("io_com_frm",real.get_state()->frm->read(),real.get_state()->frm->iris_known_bits());set("io_mem_frs1",0,0);
 const auto d=profile_.harts[0].divider;
 if(s.command&&!s.command->accepted&&clock_.now()>=s.command->rrd+d){auto&c=*s.command;full("io_ex_valid",1);full("io_ex_uop_inst",c.fetch.insn.bits());full("io_ex_uop_pc",c.pc);for(const auto&field:{std::pair{"io_ex_uop_rs1_data",unsigned((c.fetch.insn.bits()>>15)&31)},std::pair{"io_ex_uop_rs2_data",unsigned((c.fetch.insn.bits()>>20)&31)}}){const auto value=real.get_state()->XPR.read_transport(field.second);set(field.first,value.value,transport_mask(value));}}
 else{set("io_ex_uop_inst",0,0);set("io_ex_uop_pc",0,0);set("io_ex_uop_rs1_data",0,0);set("io_ex_uop_rs2_data",0,0);}
 s.unit->evaluate(s.inputs);s.outputs=s.unit->sample();const bool firing=s.inputs.values.words[s.input_fields.at("io_ex_valid")]&&s.outputs.words[s.output_fields.at("io_ex_ready")];full("io_ex_fire",firing);s.unit->evaluate(s.inputs);s.outputs=s.unit->sample();s.prepared=true;
}
bool iris_timing_adapter::saturn_try_issue(unsigned hart,reg_t pc,const insn_fetch_t&fetch){
 auto&s=*saturn_;auto decoded_insn=fetch.insn;const uint32_t raw=decoded_insn.bits();const auto opcode=raw&127;
 if((raw&0x707f)==0x0f&&hart==0){if(s.outputs.words.at(s.output_fields.at("io_backend_busy"))||s.outputs.words.at(s.output_fields.at("io_trap_check_busy")))return true;}
 if(hart==0&&!s.unit->live_commands().empty()&&opcode==0x73){const auto csr=raw>>20;const bool state_write=((raw>>12)&3)&&((((raw>>12)&3)==1)||((raw>>15)&31));if((((raw>>12)&7)==0)|| (state_write&&(csr==CSR_MSTATUS||csr==CSR_SSTATUS||csr==CSR_MIE||csr==CSR_MTVEC||csr==CSR_SATP)))throw std::runtime_error("IRIS_SATURN_PENDING_CONTEXT_CHANGE_UNMODELED");}
 if(hart==0&&(opcode==7||opcode==39))throw std::runtime_error("IRIS_SATURN_FIRST_VECTOR_MEMORY_SERVICE_NOT_CONNECTED");
 const bool unit=(opcode==0x57&&((raw>>12)&7)!=7)||opcode==0x77||opcode==7||opcode==39;
 if(!unit)return false;
 if(hart!=0)throw std::runtime_error("IRIS_SATURN_FIRST_PROFILE_OTHER_HART_VECTOR_NOT_CONNECTED");
 const auto admitted=s.commands.find(pc);if(admitted==s.commands.end()||admitted->second!=raw)throw std::runtime_error("IRIS_SATURN_ELF_PC_RAW_OUTSIDE_FINITE_ADMISSION");
 if(s.command||pending_[0]||pure_[0].engaged||!pure_[0].packets.empty())throw std::logic_error("IRIS_SATURN_FRONT_ADMISSION_REQUIRES_DRAINED_SCALAR_BOUNDARY");
 if(!frontend_[0].prepared||!frontend_[0].outputs.queue[0].valid||frontend_[0].outputs.queue[0].pc!=pc)throw std::logic_error("IRIS_SATURN_RRD_REQUIRES_ACTUAL_FRONTEND_PARCEL");
 if(cores_[0]->get_state()->prv!=PRV_M||cores_[0]->get_state()->v||!cores_[0]->iris_pipeline_context_safe())throw std::runtime_error("IRIS_SATURN_FIRST_PROFILE_CONTEXT_UNSUPPORTED");
 if(raw==0xf2880077&&cores_[0]->VU.tk!=1)throw std::runtime_error("IRIS_SATURN_PARTIAL_REDUCTION_INTENTS_K_GREATER_THAN_ONE_UNMODELED");
 iris::Op stage{0,"Saturn.RRD-to-EX","saturn0.RRD-to-EX",profile_.harts[0].divider,profile_.harts[0].divider};stage.retires=false;stage.pc=pc;stage.issue_period=profile_.harts[0].divider;if(previous_[0])stage.deps={*previous_[0]};const auto rrd=clock_.issue(std::move(stage));
 s.command=iris_saturn_live_state::Command{pc,fetch,clock_.now(),rrd,{},false,false,((raw>>12)&7)==2&&(raw>>26)==0x10};
 frontend_[0].conservative=frontend_[0].outputs.queue[0];frontend_consume(0,1);pending_[0]=Pending{pc,fetch,{}};blocked_[0]=true;return true;
}
void iris_timing_adapter::saturn_publish(const iris::saturn::OwnershipEvent&e){
 auto&s=*saturn_;if(!e.command||!e.command->caller_node)throw std::runtime_error("IRIS_SATURN_PHYSICAL_PUBLICATION_WITHOUT_CALLER");const auto node=*e.command->caller_node;const auto at=s.intents.find(node);if(at==s.intents.end())throw std::runtime_error("IRIS_SATURN_PHYSICAL_INTENT_OWNER_MISSING");const auto&intent=at->second;auto&v=cores_[0]->VU;
 if(intent.pc!=e.command->pc||intent.instruction!=e.command->instruction)throw std::runtime_error("IRIS_SATURN_PHYSICAL_INTENT_IDENTITY");
 if(e.kind=="VRF_bank_commit"){
  if(!e.element_group||e.data_words.size()!=e.bit_mask.size())throw std::runtime_error("IRIS_SATURN_PHYSICAL_VRF_SCHEMA");const auto offset=*e.element_group*16ULL;auto*data=static_cast<uint8_t*>(v.reg_file);
  for(unsigned w=0;w<e.bit_mask.size();++w)for(unsigned b=0;b<8;++b){const auto mask=uint8_t(e.bit_mask[w]>>(8*b));if(!mask)continue;const auto byte=offset+w*8+b;if(byte>=intent.after.vrf.size())throw std::runtime_error("IRIS_SATURN_PHYSICAL_VRF_RANGE");const auto actual=uint8_t(e.data_words[w]>>(8*b));iris_definedness::require_byte(intent.after.vrf_known.byte(byte),mask,byte,{0,intent.pc,"private-VRF-intent"});if((actual&mask)!=(intent.after.vrf[byte]&mask))throw std::runtime_error("IRIS_SATURN_SOURCE_VRF_PRIVATE_INTENT_MISMATCH pc="+std::to_string(intent.pc)+" byte="+std::to_string(byte));data[byte]=(data[byte]&~mask)|(actual&mask);v.iris_vrf_definedness.write_bits(byte,mask);++s.physical_vrf_bytes;}
 }else if(e.kind.starts_with("MRF_")){
  if(!e.mrf_cell||!e.mrf_entry||e.data_words.size()!=1)throw std::runtime_error("IRIS_SATURN_PHYSICAL_MRF_SCHEMA");const auto cell=*e.mrf_cell,entry=*e.mrf_entry;const auto cluster_row=cell/64,cluster_col=(cell/16)%4,cell_row=(cell/4)%4,cell_col=cell%4;const auto row=16*((entry>>1)&1)+cluster_row+4*cell_row,col=16*(entry&1)+cluster_col+4*cell_col,tile=entry>>2;const auto offset=(tile*1024+row*32+col)*4;uint32_t expected=0;if(offset+4>intent.after.mrf.size())throw std::runtime_error("IRIS_SATURN_PHYSICAL_MRF_RANGE");intent.after.mrf_known.require(offset,4,{0,intent.pc,"private-MRF-intent"});std::memcpy(&expected,intent.after.mrf.data()+offset,4);const auto actual=uint32_t(e.data_words[0]);if(actual!=expected)throw std::runtime_error("IRIS_SATURN_SOURCE_MRF_PRIVATE_INTENT_MISMATCH");std::memcpy(v.mt.data()+offset,&actual,4);v.iris_tile_definedness.define(offset,4);v.iris_initialized.at(offset/4)=1;++s.physical_mrf_cells;
 }else if(e.kind=="scalar_response_complete"){
  if(!intent.scalar||!e.scalar_rd||e.data_words.size()!=1||*e.scalar_rd!=((intent.instruction>>7)&31))throw std::runtime_error("IRIS_SATURN_SCALAR_RESPONSE_OWNER");for(unsigned b=0;b<8;++b)iris_definedness::require_byte(intent.scalar->known[b],255,b,{0,intent.pc,"private-scalar-intent"});if(e.data_words[0]!=intent.scalar->value)throw std::runtime_error("IRIS_SATURN_SOURCE_SCALAR_PRIVATE_INTENT_MISMATCH");cores_[0]->iris_write_xpr_transport(*e.scalar_rd,*intent.scalar);
 }
}
reg_t iris_timing_adapter::saturn_retire_handler(processor_t*p,insn_t insn,reg_t pc){
 if(!saturn_handler_owner||!saturn_handler_owner->saturn_||!saturn_handler_owner->saturn_->command)throw std::logic_error("IRIS_SATURN_ARCHITECTURAL_HANDLER_WITHOUT_OWNER");auto&c=*saturn_handler_owner->saturn_->command;if(c.pc!=pc||c.fetch.insn.bits()!=insn.bits())throw std::logic_error("IRIS_SATURN_ARCHITECTURAL_HANDLER_IDENTITY");p->get_state()->sstatus->dirty(SSTATUS_VS);
 if(c.scalar){iris_definedness::Value<uint64_t>unknown;p->iris_write_xpr_transport((insn.bits()>>7)&31,unknown);}return pc+4;
}
void iris_timing_adapter::saturn_retire(iris::NodeId node){
 auto&s=*saturn_;if(!s.command||s.command->front!=std::optional<iris::NodeId>(node)||s.command->retired||!pending_[0])throw std::logic_error("IRIS_SATURN_FRONT_COM_OWNER");auto&c=*s.command;
 if(cores_[0]->get_state()->pc!=c.pc)throw std::logic_error("IRIS_SATURN_FRONT_COM_PC");if(cores_[0]->iris_pipeline_interrupt_exception())throw std::runtime_error("IRIS_SATURN_PENDING_PRECISE_INTERRUPT_UNMODELED");
 // Whole-instruction functional vector execution here would publish results
 // early. Check the actual architectural COM transition leaves numeric VRF,
 // MRF and their masks unchanged; only owned physical events may publish.
 auto&vu=cores_[0]->VU;std::vector<uint8_t>before_vrf(vu.vlenb*32);std::memcpy(before_vrf.data(),vu.reg_file,before_vrf.size());const auto before_mrf=vu.mt;const auto before_vrf_known=vu.iris_vrf_definedness.read(0,before_vrf.size()),before_mrf_known=vu.iris_tile_definedness.read(0,before_mrf.size());
 const auto before=retired_[0];pending_[0]->fetch.func=&iris_timing_adapter::saturn_retire_handler;pending_[0]->completion_node=node;completing_=0;completing_node_=node;completion_reads_.clear();saturn_handler_owner=this;
 try{cores_[0]->step(1);}catch(...){saturn_handler_owner=nullptr;completion_reads_.clear();completing_node_.reset();completing_.reset();throw;}saturn_handler_owner=nullptr;finish_counter_reads(0,before);completing_node_.reset();completing_.reset();if(retired_[0]!=before+1)throw std::runtime_error("IRIS_SATURN_UNEXPECTED_ARCHITECTURAL_TRAP");if(std::memcmp(before_vrf.data(),vu.reg_file,before_vrf.size())||before_mrf!=vu.mt||before_vrf_known!=vu.iris_vrf_definedness.read(0,before_vrf.size())||before_mrf_known!=vu.iris_tile_definedness.read(0,before_mrf.size()))throw std::runtime_error("IRIS_SATURN_EARLY_COM_NUMERIC_PUBLICATION");++s.counts["COM_numeric_state_unchanged"];frontend_boundary_complete(0,c.pc,c.fetch);pending_[0].reset();c.retired=true;++s.retired;++completions_;clock_.finish_physical(node);previous_[0]=node;
 if(!c.scalar){blocked_[0]=false;s.command.reset();}
}
void iris_timing_adapter::saturn_commit(){
 auto&s=*saturn_;if(!s.prepared)return;const auto now=clock_.now();auto out=[&](const std::string&name){return s.outputs.words.at(s.output_fields.at(name));};
 if(out("io_com_xcpt")||out("io_com_internal_replay")||out("io_com_retire_late")||out("io_com_block_all"))throw std::runtime_error("IRIS_SATURN_FIRST_SOURCE_COM_REPLAY_OR_TRAP_UNMODELED");
 std::optional<iris::saturn::CallerCommand>caller;
 if(s.command&&!s.command->accepted&&s.inputs.values.words[s.input_fields.at("io_ex_valid")]&&out("io_ex_ready")){
  auto&c=*s.command;const auto raw=uint32_t(c.fetch.insn.bits());const auto rs1=cores_[0]->get_state()->XPR.read_transport((raw>>15)&31),rs2=cores_[0]->get_state()->XPR.read_transport((raw>>20)&31);
  const auto node=clock_.accept_physical({0,"source-Saturn-front-command","saturn0.front-command",c.pc,0,0,{c.rrd_node},"source-Saturn-S0-to-PFC-front-permission",true});
  auto intent=s.oracle->preview(*cores_[0],node,c.pc,raw,rs1,rs2);if(s.intents.size()>=64)throw std::runtime_error("IRIS_SATURN_PRIVATE_INTENT_BOUND_REQUIRES_EXACT_LIFETIME_RELEASE");s.intents.emplace(node,std::move(intent));c.front=node;c.accepted=true;pending_[0]->completion_node=node;caller=iris::saturn::CallerCommand{node,c.pc,raw};++s.accepted;
 }
 // Bridge metadata includes its two explicit pre-guest reset edges.
 // Guest graph/counters start at release; this is an origin translation,
 // never an additional source edge or a fitted counter offset.
 auto events=s.unit->commit(now+2*profile_.harts[0].divider,caller);for(const auto&e:events){++s.counts[e.kind];
  if(e.kind=="MEM_kill")throw std::runtime_error("IRIS_SATURN_FIRST_SOURCE_SPECULATIVE_KILL_NOT_INTEGRATED");
  if(e.kind=="VRF_bank_commit"||e.kind.starts_with("MRF_")||e.kind=="scalar_response_complete")saturn_publish(e);
  if(e.kind=="INT8_MAC_edge"||e.kind=="VRF_bank_commit"||e.kind.starts_with("MRF_")){
   if(!e.command)throw std::runtime_error("IRIS_SATURN_GRAPH_WORK_WITHOUT_COMMAND");const bool mac=e.kind=="INT8_MAC_edge",vrf=e.kind=="VRF_bank_commit";const auto bytes=vrf?e.amount/8:mac?0:4;
   clock_.record_physical_edge({0,e.kind,mac?"saturn0.physical-INT8-MAC":vrf?"saturn0.physical-VRF":"saturn0.physical-MRF",e.command->pc,bytes,mac?e.amount:0,{},std::string(iris::saturn::SaturnLiveBridge::component_source_identity())+":"+e.source,true});
  }
  if(e.kind=="PFC_front_permission"){if(!e.command||!e.command->caller_node)throw std::runtime_error("IRIS_SATURN_FRONT_PERMISSION_WITHOUT_OWNER");saturn_retire(*e.command->caller_node);}
  if(e.kind=="scalar_response_complete"){
   if(!s.command||!s.command->retired||!s.command->scalar||s.command->front!=e.command->caller_node)throw std::runtime_error("IRIS_SATURN_SCALAR_RESPONSE_BEFORE_EXPECTED_FRONT_COM");blocked_[0]=false;s.command.reset();
  }
 }
 // Observation-only lifetime release, after all same-edge physical writes.
 // Retain the union with CPU front/scalar-response ownership.
 std::set<iris::NodeId>live;for(const auto&command:s.unit->live_commands())if(command.caller_node)live.insert(*command.caller_node);if(s.command&&s.command->front)live.insert(*s.command->front);for(auto at=s.intents.begin();at!=s.intents.end();)if(!live.count(at->first))at=s.intents.erase(at);else++at;
 s.prepared=false;++s.edges;s.next_edge=now+profile_.harts[0].divider;
}
void iris_timing_adapter::write_saturn_json(std::ostream&out)const{
 if(!profile_.saturn_live)return;const auto&s=*saturn_;out<<",\"saturn_live\":{\"implementation\":\"source-cut-private-numeric-intents-physical-publication\",\"hart\":0,\"manifest\":"<<std::quoted(s.manifest_path)<<",\"admission_identity\":"<<std::quoted(s.manifest_identity)<<",\"declared_ELF_identity\":"<<std::quoted(s.elf_identity)<<",\"source_identity\":"<<std::quoted(iris::saturn::SaturnLiveBridge::component_source_identity())<<",\"edges\":"<<s.edges<<",\"source_accepted_commands\":"<<s.accepted<<",\"architecturally_retired_commands\":"<<s.retired<<",\"physical_VRF_written_bytes\":"<<s.physical_vrf_bytes<<",\"physical_MRF_cells\":"<<s.physical_mrf_cells<<",\"front_command_pending\":"<<(s.command?"true":"false")<<",\"private_intents_retained\":"<<s.intents.size()<<",\"pending_ownership\":{";bool first=true;for(const auto&[name,count]:s.unit->pending().live){if(!first)out<<',';first=false;out<<std::quoted(name)<<':'<<count;}out<<"},\"source_events\":{";first=true;for(const auto&[name,count]:s.counts){if(!first)out<<',';first=false;out<<std::quoted(name)<<':'<<count;}out<<"},\"admission_scope\":\"conservative-drained-scalar-boundary-to-real-unit-EX\",\"memory_scope\":\"explicit-functional-shared-memory-fixture\",\"full_internal_knownness_certified\":false,\"full_three_hart_memory_qualified\":false,\"timing_certified\":false,\"held_out_2pct\":false}";
}
