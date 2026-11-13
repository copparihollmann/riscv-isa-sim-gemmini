// First live ownership increment.  The only enabled service is explicitly
// SYNTHETIC-DIRECTED-TEST-ONLY.  No source TL/VMU timing is represented here.
namespace {
struct IrisVseBoundaryCapture {
 reg_t base;std::vector<iris_definedness::Value<uint32_t>> expected;
 unsigned captured=0;
 static void append(void*opaque,reg_t address,uint32_t value,const std::array<uint8_t,4>&known){
  auto&c=*static_cast<IrisVseBoundaryCapture*>(opaque);const auto i=c.captured;
  if(i>=c.expected.size()||address!=c.base+4*i||value!=c.expected[i].value||known!=c.expected[i].known)
   throw std::logic_error("IRIS_VSE_BOUNDARY_ORIGINAL_HANDLER_INTENT_MISMATCH");
  ++c.captured;
 }
};
}
struct iris_timing_adapter::VseBoundaryCommand {
 iris::vse_boundary::Identity owner;reg_t base;unsigned vs3,lmul,next_word=0,ACKs=0,releases=0;
 Cycle COM;std::vector<iris_definedness::Value<uint32_t>>words;
 std::vector<iris_definedness::Value<uint64_t>>before_memory;
 std::vector<uint8_t>physical_vrf;std::vector<uint8_t>physical_known;
 std::optional<uint64_t>cache_owner;bool tick_scheduled=false;
};
bool iris_timing_adapter::vse_boundary_live(unsigned h)const{return h<2&&bool(vse_boundary_commands_[h]);}
void iris_timing_adapter::vse_boundary_environment()const{
 if(!profile_.vse_boundary_test)return;
 const unsigned h=profile_.vse_boundary_hart;if(!vse_boundary_live(h))return;
 auto fail=[&](const char*name){const auto&c=*vse_boundary_commands_[h];throw std::runtime_error(std::string(name)+" hart="+std::to_string(h)+" pc="+std::to_string(c.owner.pc)+" raw="+std::to_string(c.owner.raw));};
 if(cores_[h]->get_state()->mstatus->read()&MSTATUS_MIE)fail("IRIS_VSE_BOUNDARY_GLOBAL_IRQ_ENABLE_UNSUPPORTED");
 for(unsigned p=0;p<cores_.size();++p){const auto*s=cores_[p]->get_state();if(s->mip->read()&s->mie->read())fail("IRIS_VSE_BOUNDARY_PENDING_IRQ_UNSUPPORTED");if(p!=h&&!cores_[p]->is_waiting_for_interrupt())fail("IRIS_VSE_BOUNDARY_PEER_NOT_QUIET");}
}
void iris_timing_adapter::vse_boundary_step(unsigned h){
 auto*p=cores_[h];const auto pc=pending_[h]->pc;const uint32_t raw=uint32_t(pending_[h]->fetch.insn.bits());
 const auto width=(raw>>12)&7;const bool vector_store=(raw&127)==0x27&&(width==0||width>=5);
 if(!profile_.vse_boundary_test||!vector_store){p->step(1);return;}
 auto&v=p->VU;auto*s=p->get_state();
 auto fail=[&](const char*name){throw std::runtime_error(std::string(name)+" hart="+std::to_string(h)+" pc="+std::to_string(pc)+" raw="+std::to_string(raw)+" VL="+std::to_string(v.vl->read())+" SEW="+std::to_string(v.vsew)+" LMUL="+std::to_string(v.vflmul));};
 if(h!=profile_.vse_boundary_hart||h>=2)fail("IRIS_VSE_BOUNDARY_ACTIVE_HART_REFUSED");
 if(width!=6||!(raw&(1u<<25))||(raw&(7u<<29))||((raw>>26)&7)||((raw>>20)&31)||s->debug_mode)
  fail("IRIS_VSE_BOUNDARY_REQUIRES_UNMASKED_UNITSTRIDE_NF1_VSE32");
 const auto vl=v.vl->read_defined(pc),start=v.vstart->read_defined(pc);v.vtype->read_defined(pc);
 if(v.vill||v.vsew!=32||start||!vl||vl>64||v.vflmul<1||v.vflmul>8)fail("IRIS_VSE_BOUNDARY_GEOMETRY_UNSUPPORTED");
 const unsigned rs1=(raw>>15)&31,vs3=(raw>>7)&31,lmul=unsigned(v.vflmul);
 if(float(lmul)!=v.vflmul||(lmul!=1&&lmul!=2&&lmul!=4&&lmul!=8)||vs3%lmul||vs3+lmul>32||vl>(v.get_vlen()/32)*lmul)
  fail("IRIS_VSE_BOUNDARY_REGISTER_GROUP_UNSUPPORTED");
 s->XPR.require_defined(rs1,sizeof(reg_t),{h,pc,"VSE-live-boundary-address"});const auto base=s->XPR.read_transport(rs1).value;
 if(base%16||vl*4>0x180000000ull||base>0x180000000ull-vl*4)fail("IRIS_VSE_BOUNDARY_FINITE_ADDRESS_ALIGNMENT");
 auto c=std::make_shared<VseBoundaryCommand>();c->owner={h,1,++vse_boundary_serial_,pc,raw};c->base=base;c->vs3=vs3;c->lmul=lmul;c->COM=clock_.now();
 c->physical_vrf.resize(v.vlenb*32);std::memcpy(c->physical_vrf.data(),v.reg_file,c->physical_vrf.size());c->physical_known=v.iris_vrf_definedness.read(0,c->physical_vrf.size());
 auto*mmu=p->get_mmu();IrisVseBoundaryCapture capture{base,{}};
 for(unsigned i=0;i<vl;++i){
  if(!mmu->iris_pipeline_store_permitted(base+4*i,4))fail("IRIS_VSE_BOUNDARY_MBARE_DRAM_ADDRESS_REFUSED");
  const auto value=v.read_transport<uint32_t>(vs3,i);
  if(!std::all_of(value.known.begin(),value.known.end(),[](uint8_t b){return b==255;}))fail("IRIS_VSE_BOUNDARY_UNDEFINED_VRF_SOURCE");
  capture.expected.push_back(value);c->before_memory.push_back(p->iris_frontend_read_beat((base+4*i)&~7ULL));
 }
 if(vse_boundary_live(h)||!vse_boundary_ledgers_[h].empty())fail("IRIS_VSE_BOUNDARY_PREVIOUS_OWNER_NOT_DRAINED");
 vse_boundary_commands_[h]=c;
 try{vse_boundary_environment();}catch(...){vse_boundary_commands_[h].reset();throw;}
 const auto retired_before=retired_[h];mmu->iris_begin_vse_boundary_capture(&capture,IrisVseBoundaryCapture::append);
 try{p->step(1);}catch(...){mmu->iris_end_vse_boundary_capture();vse_boundary_commands_[h].reset();throw;}
 mmu->iris_end_vse_boundary_capture();
 if(retired_[h]==retired_before){vse_boundary_commands_[h].reset();if(capture.captured)fail("IRIS_VSE_BOUNDARY_NONRETIRED_MEMORY_INTENT");return;}
 if(retired_[h]!=retired_before+1||capture.captured!=vl)fail("IRIS_VSE_BOUNDARY_INCOMPLETE_ORIGINAL_HANDLER");
 if(std::memcmp(v.reg_file,c->physical_vrf.data(),c->physical_vrf.size())||v.iris_vrf_definedness.read(0,c->physical_vrf.size())!=c->physical_known)
  fail("IRIS_VSE_BOUNDARY_STORE_HANDLER_CHANGED_VRF");
 for(unsigned i=0;i<vl;++i){const auto after=p->iris_frontend_read_beat((base+4*i)&~7ULL);if(after.value!=c->before_memory[i].value||after.known!=c->before_memory[i].known)fail("IRIS_VSE_BOUNDARY_EARLY_RAM_PUBLICATION");}
 c->words=std::move(capture.expected);c->cache_owner=pending_[h]->cache_owner;pending_[h]->cache_owner.reset();++vse_boundary_commands_total_;
 if(async_trace_)*async_trace_<<"{\"event\":\"VSE_boundary_checked_COM\",\"backend\":\"synthetic-directed-test-only\",\"hart\":"<<h<<",\"epoch\":1,\"command\":"<<c->owner.command<<",\"pc\":"<<pc<<",\"raw\":"<<raw<<",\"cycle\":"<<clock_.now()<<",\"base\":"<<base<<",\"VL\":"<<vl<<",\"SEW\":32,\"LMUL\":"<<lmul<<",\"vs3\":"<<vs3<<",\"words\":"<<vl<<",\"RAM_unchanged_during_handler\":true,\"CPU_VMU_phase_qualified\":false}\n";
 vse_boundary_schedule(h);
}
void iris_timing_adapter::vse_boundary_schedule(unsigned h){
 auto c=vse_boundary_commands_[h];if(!c||c->tick_scheduled||c->next_word==c->words.size())return;
 c->tick_scheduled=true;const auto d=profile_.harts[h].divider;
 iris::Op op{h,"synthetic-test.VSE.ingress-edge","test.VSE.tick"+std::to_string(h),d,1};op.retires=false;op.issue_period=d;op.pc=c->owner.pc;
 op.on_complete=[this,h,c]{if(vse_boundary_commands_[h]!=c)throw std::logic_error("IRIS_VSE_BOUNDARY_TICK_OWNER_LOST");c->tick_scheduled=false;vse_boundary_tick(h);vse_boundary_schedule(h);};clock_.issue(std::move(op));
}
void iris_timing_adapter::vse_boundary_tick(unsigned h){
 auto c=vse_boundary_commands_[h];vse_boundary_environment();auto&ledger=vse_boundary_ledgers_[h];const auto d=profile_.harts[h].divider;
 if(const auto request=ledger.request()){
  const auto r=*request;ledger.accepted(r.token);++vse_boundary_requests_total_;
  if(async_trace_)*async_trace_<<"{\"event\":\"VSE_boundary_synthetic_request_accept\",\"hart\":"<<h<<",\"command\":"<<c->owner.command<<",\"tag\":"<<r.token.tag<<",\"generation\":"<<r.token.generation<<",\"cycle\":"<<clock_.now()<<",\"address\":"<<r.address<<",\"source_request_bytes\":16,\"enabled_bytes\":"<<4*r.words<<",\"TL_handshake_claim\":false}\n";
  const auto delay=profile_.vse_boundary_ack+((r.token.tag&1)?0:3); // explicit synthetic out-of-order response stimulus
  iris::Op ack{h,"synthetic-test.VSE.matching-response","test.VSE.ACK"+std::to_string(h),delay*d,1};ack.retires=false;ack.issue_period=d;ack.pc=c->owner.pc;ack.bytes=4*r.words;
  ack.on_complete=[this,h,c,r]{vse_boundary_ack(h,c,r.token.tag,r.token.generation);};clock_.issue(std::move(ack));
 }
 if(c->next_word<c->words.size()&&ledger.reserve_ready()){
  auto&v=cores_[h]->VU;
  if(std::memcmp(v.reg_file,c->physical_vrf.data(),c->physical_vrf.size())||v.iris_vrf_definedness.read(0,c->physical_vrf.size())!=c->physical_known)
   throw std::logic_error("IRIS_VSE_BOUNDARY_PHYSICAL_VRF_LEASE_VERSION_CHANGED");
  iris::vse_boundary::Request r;r.owner=c->owner;r.first_word=c->next_word;r.words=std::min<unsigned>(4,c->words.size()-c->next_word);r.address=c->base+4*c->next_word;r.last=c->next_word+r.words==c->words.size();r.mask=uint16_t((uint32_t(1)<<(4*r.words))-1);
  for(unsigned i=0;i<r.words;++i){const auto&w=c->words[r.first_word+i];for(unsigned b=0;b<4;++b){r.data[4*i+b]=uint8_t(w.value>>(8*b));r.known[4*i+b]=w.known[b];}}
  r=ledger.reserve(r);c->next_word+=r.words;
  if(async_trace_)*async_trace_<<"{\"event\":\"VSE_boundary_reserve\",\"hart\":"<<h<<",\"command\":"<<c->owner.command<<",\"tag\":"<<r.token.tag<<",\"generation\":"<<r.token.generation<<",\"cycle\":"<<clock_.now()<<",\"first_word\":"<<r.first_word<<",\"words\":"<<r.words<<",\"last\":"<<(r.last?"true":"false")<<",\"VRF_value_and_known_lease_checked\":true}\n";
 }
 // A final request reserved above still needs its separately owned accept edge.
 if(c->next_word==c->words.size()&&ledger.request()){
  c->tick_scheduled=true;iris::Op tick{h,"synthetic-test.VSE.final-request-edge","test.VSE.tick"+std::to_string(h),d,1};tick.retires=false;tick.issue_period=d;tick.pc=c->owner.pc;tick.on_complete=[this,h,c]{c->tick_scheduled=false;vse_boundary_tick(h);};clock_.issue(std::move(tick));
 }
}
void iris_timing_adapter::vse_boundary_ack(unsigned h,const std::shared_ptr<VseBoundaryCommand>&c,unsigned tag,uint64_t generation){
 if(vse_boundary_commands_[h]!=c)throw std::logic_error("IRIS_VSE_BOUNDARY_ACK_COMMAND_OWNER_LOST");vse_boundary_environment();auto&ledger=vse_boundary_ledgers_[h];const auto r=ledger.acknowledge({tag,generation});
 for(unsigned i=0;i<r.words;++i){const auto wi=r.first_word+i;const auto address=c->base+4*wi;const auto current=cores_[h]->iris_frontend_read_beat(address&~7ULL);const auto shift=(address&7)*8;const auto&before=c->before_memory[wi];
  if(uint32_t(current.value>>shift)!=uint32_t(before.value>>shift)||!std::equal(current.known.begin()+shift/8,current.known.begin()+shift/8+4,before.known.begin()+shift/8))throw std::logic_error("IRIS_VSE_BOUNDARY_CONFLICTING_RAM_WRITE_BEFORE_RESPONSE");
  cores_[h]->get_mmu()->store_transport<uint32_t>(address,c->words[wi]);
 }
 ++c->ACKs;++vse_boundary_ACKs_total_;
 if(async_trace_)*async_trace_<<"{\"event\":\"VSE_boundary_synthetic_response_publish\",\"hart\":"<<h<<",\"command\":"<<c->owner.command<<",\"tag\":"<<tag<<",\"generation\":"<<generation<<",\"cycle\":"<<clock_.now()<<",\"bytes\":"<<4*r.words<<",\"coherent_visibility_claim\":false}\n";
 while(const auto released=ledger.release()){
  ++c->releases;++vse_boundary_releases_total_;
  if(async_trace_)*async_trace_<<"{\"event\":\"VSE_boundary_ordered_SIFQ_release\",\"hart\":"<<h<<",\"command\":"<<c->owner.command<<",\"tag\":"<<released->token.tag<<",\"generation\":"<<released->token.generation<<",\"cycle\":"<<clock_.now()<<",\"last\":"<<(released->last?"true":"false")<<"}\n";
  if(released->last){
   const auto requests=(c->words.size()+3)/4;if(!ledger.empty()||c->next_word!=c->words.size()||c->ACKs!=requests||c->releases!=requests)throw std::logic_error("IRIS_VSE_BOUNDARY_PREMATURE_SIQ_RELEASE");
   if(c->cache_owner){empirical_cache_->complete(*c->cache_owner,clock_.now(),true);cache_nodes_.erase(*c->cache_owner);c->cache_owner.reset();}
   vse_boundary_commands_[h].reset();++vse_boundary_completed_total_;
  }
 }
}
void iris_timing_adapter::vse_boundary_totals(std::ostream&out)const{
 if(!profile_.vse_boundary_test)return;
 out<<",\"VSE_live_boundary\":{\"backend\":\"synthetic-directed-test-only\",\"product_System_backend_available\":false,\"active_hart\":"<<profile_.vse_boundary_hart<<",\"commands\":"<<vse_boundary_commands_total_<<",\"completed\":"<<vse_boundary_completed_total_<<",\"source_requests\":"<<vse_boundary_requests_total_<<",\"ACKs\":"<<vse_boundary_ACKs_total_<<",\"ordered_releases\":"<<vse_boundary_releases_total_<<",\"pending\":"<<(vse_boundary_live(0)||vse_boundary_live(1)?"true":"false")<<",\"CPU_VMU_phase_qualified\":false,\"physical_memory_timing_qualified\":false,\"coherent_visibility_qualified\":false}";
}
