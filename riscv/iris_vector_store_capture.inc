// Experimental COM-quarantine proof. CPU/ACK timing is deliberately unchanged.
// This primitive is not an asynchronous vector-store bridge.
namespace {
struct IrisVseCapturedWord {reg_t address;uint32_t value;std::array<uint8_t,4> known;};
struct IrisVseCapture {
 reg_t base;std::vector<iris_definedness::Value<uint32_t>> expected;
 std::vector<IrisVseCapturedWord> words;
 static void append(void*opaque,reg_t address,uint32_t value,const std::array<uint8_t,4>&known){
  auto&c=*static_cast<IrisVseCapture*>(opaque);const auto i=c.words.size();
  if(i>=c.expected.size()||address!=c.base+4*i||value!=c.expected[i].value||known!=c.expected[i].known)
   throw std::runtime_error("IRIS_VSE_CAPTURE_ORIGINAL_HANDLER_INTENT_MISMATCH");
  c.words.push_back({address,value,known});
 }
};
}
void iris_timing_adapter::empirical_vector_store_step(unsigned hart){
 auto*p=cores_[hart];const uint32_t raw=uint32_t(pending_[hart]->fetch.insn.bits());
 const unsigned width=(raw>>12)&7;
 const bool vector_store=(raw&127)==0x27&&(width==0||width>=5);
 if(!profile_.empirical_vector_store_capture||!vector_store){p->step(1);return;}
 auto&vu=p->VU;auto*s=p->get_state();const auto pc=s->pc;
 if(width!=6||!(raw&(1u<<25))||(raw&(7u<<29))||((raw>>26)&7)||((raw>>20)&31)||s->debug_mode)
  throw std::runtime_error("IRIS_VSE_CAPTURE_REQUIRES_UNMASKED_UNITSTRIDE_NF1_VSE32");
 const auto vl=vu.vl->read_defined(pc);const auto start=vu.vstart->read_defined(pc);vu.vtype->read_defined(pc);
 if(vu.vill||vu.vsew!=32||start||!vl||vl>64||vu.vflmul<1||vu.vflmul>8)
  throw std::runtime_error("IRIS_VSE_CAPTURE_REQUIRES_DEFINED_E32_VL1_TO64_VSTART0");
 const unsigned rs1=(raw>>15)&31,vs3=(raw>>7)&31;
 const unsigned lmul=unsigned(vu.vflmul);
 if(float(lmul)!=vu.vflmul||(lmul!=1&&lmul!=2&&lmul!=4&&lmul!=8)||vs3%lmul||vs3+lmul>32||vl>(vu.get_vlen()/32)*lmul)throw std::runtime_error("IRIS_VSE_CAPTURE_REGISTER_GROUP_LEGALITY_REFUSED");
 s->XPR.require_defined(rs1,sizeof(reg_t),{hart,pc,"VSE32-address"});
 const auto base=s->XPR.read_transport(rs1).value;
 auto*mmu=p->get_mmu();IrisVseCapture capture{base,{},{}};
 std::vector<iris_definedness::Value<uint64_t>> before;
 for(unsigned i=0;i<vl;++i){
  if(!mmu->iris_pipeline_store_permitted(base+4*i,4))throw std::runtime_error("IRIS_VSE_CAPTURE_MBARE_DRAM_ADDRESS_REFUSED");
  auto value=vu.read_transport<uint32_t>(vs3,i);
  if(!std::all_of(value.known.begin(),value.known.end(),[](uint8_t b){return b==255;}))throw std::runtime_error("IRIS_VSE_CAPTURE_UNDEFINED_VRF_SOURCE");
  capture.expected.push_back(value);before.push_back(p->iris_frontend_read_beat((base+4*i)&~7ULL));
 }
 const auto retired_before=retired_[hart];
 mmu->iris_begin_store32_capture(&capture,IrisVseCapture::append);
 try {p->step(1);} catch(...){mmu->iris_end_store32_capture();throw;}
 mmu->iris_end_store32_capture();
 // An interrupt may prevent the instruction from running. Preserve that path.
 if(retired_[hart]==retired_before){if(!capture.words.empty())throw std::runtime_error("IRIS_VSE_CAPTURE_NONRETIRED_INTENT");return;}
 if(retired_[hart]!=retired_before+1||capture.words.size()!=vl)throw std::runtime_error("IRIS_VSE_CAPTURE_INCOMPLETE_RETIRED_HANDLER");
 for(unsigned i=0;i<vl;++i){const auto after=p->iris_frontend_read_beat((base+4*i)&~7ULL);if(after.value!=before[i].value||after.known!=before[i].known)throw std::runtime_error("IRIS_VSE_CAPTURE_WROTE_MEMORY_BEFORE_PUBLICATION");}
 // Same-COM publication through the existing typed MMU path. This validates
 // quarantine, not early retirement/VRF port timing/ACK visibility.
 for(const auto&w:capture.words){iris_definedness::Value<uint32_t> v;v.value=w.value;v.known=w.known;mmu->store_transport<uint32_t>(w.address,v);}
 ++vector_store_captured_commands_;vector_store_captured_words_+=vl;
 if(async_trace_)*async_trace_<<"{\"event\":\"VSE32_COM_quarantine_publish\",\"hart\":"<<hart<<",\"pc\":"<<pc<<",\"cycle\":"<<clock_.now()<<",\"address\":"<<base<<",\"words\":"<<vl<<",\"RAM_unchanged_during_original_handler\":true,\"early_COM\":false,\"ACK_timing_qualified\":false}\n";
}
