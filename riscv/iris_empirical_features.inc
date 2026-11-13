// Experimental, instruction-derived empirical features. No benchmark identities.
iris_timing_adapter::Feature iris_timing_adapter::empirical_feature(unsigned hart,const insn_fetch_t&fetch)const{
 Feature f;f.family="scalar.integer";auto instruction=fetch.insn;const uint32_t raw=instruction.bits();const unsigned op=raw&127,f3=(raw>>12)&7;
 auto&v=cores_[hart]->VU;
 const uint64_t beats=(v.vl->read()*v.vsew+(hart==2?255:127))/(hart==2?256:128);
 auto match=[&](uint32_t bits,uint32_t mask){return(raw&mask)==bits;};
 if(match(MATCH_VTMMU_TVV,MASK_VTMMU_TVV)||match(MATCH_VTMMS_TVV,MASK_VTMMS_TVV)){
  f.family="vme.int8";f.work=((v.tm+15)/16)*((v.tn()+15)/16)*v.tk;f.macs=v.tm*v.tn()*v.tk;
 }else if(match(MATCH_VTFMM_TVV,MASK_VTFMM_TVV)||match(MATCH_VTFMM_ALT_TVV,MASK_VTFMM_ALT_TVV)){
  f.family="vme.fp8";f.work=((v.tm+15)/16)*((v.tn()+15)/16)*v.tk;f.macs=v.tm*v.tn()*v.tk;
 }else if(match(MATCH_VTZERO,MASK_VTZERO)){f.family="vme.zero";f.work=profile_.empirical_vme_shape_work?((v.tm+15)/16)*((v.tn()+15)/16):4;
 }else if(match(MATCH_VTMV_T_V,MASK_VTMV_T_V)||match(MATCH_VTMV_V_T,MASK_VTMV_V_T)){
  f.family="vme.row_move";f.work=(v.vl->read()*32+(hart==2?255:127))/(hart==2?256:128);f.bytes=v.vl->read()*4;
 }else if(match(MATCH_VTDISCARD,MASK_VTDISCARD)){f.family="vme.discard";
 }else if(op==0x57&&f3==7){f.family="vector.config";
 }else if(op==0x57){f.family=(f3==1||f3==5)?"rvv.fp"+std::to_string(v.vsew):"rvv.integer";f.work=beats;if(profile_.empirical_async_fadd&&f3==1&&(raw>>26)==0){f.family=v.vsew==16&&v.altfmt?"rvv.fadd.bf16":"rvv.fadd.fp"+std::to_string(v.vsew);if(hart==2)f.work=v.vl->read();}
 }else if(op==0x53||op==0x43||op==0x47||op==0x4b||op==0x4f){
  const unsigned fmt=(raw>>25)&3;f.family=fmt==0?"scalar.fp32":fmt==1?"scalar.fp64":fmt==2?"scalar.fp16":"scalar.fp128";if(profile_.empirical_scalar_fadd&&((raw&0xfe00007f)==0x53||(raw&0xfe00007f)==0x02000053||(raw&0xfe00007f)==0x04000053)){f.family=fmt==0?"scalar.fadd.fp32":fmt==1?"scalar.fadd.fp64":"scalar.fadd.fp16";f.work=1;}
 }else if(op==0x63||op==0x67||op==0x6f||(((raw&3)==1&&(((raw>>13)&7)==5||((raw>>13)&7)==6||((raw>>13)&7)==7))||((raw&3)==2&&((raw>>13)&7)==4&&((raw>>2)&31)==0&&((raw>>7)&31)!=0))){f.family="scalar.branch";
 }else if(op==0x73){f.family="scalar.csr_system";
 }else if(op==0x0f){f.family="scalar.fence";
 }else{
  std::array<uint64_t,32>r{};
  const bool compressed=(raw&3)!=3;const unsigned quadrant=raw&3,cf3=raw>>13;
  const bool possible_memory=compressed?((quadrant==0||quadrant==2)&&(cf3==1||cf3==2||cf3==3||cf3==5||cf3==6||cf3==7)):(op==3||op==0x23||op==7||op==0x27||op==0x2f);
  if(!possible_memory)return f;
  const unsigned base=compressed?(quadrant==0?8+((raw>>7)&7):2):((raw>>15)&31);r[base]=cores_[hart]->get_state()->XPR.read_transport(base).value;
  f.memory=iris::scalar_memory_access(raw,r);
  if(f.memory.decode==iris::MemoryDecode::scalar){
   const auto address=f.memory.address;std::string path="MMIO";
   if(address>=0x70000000&&address<0x70040000){const unsigned owner=(address-0x70000000)/0x20000;path=owner==hart?"LOCAL_TCM":"REMOTE_TCM";}
   else if(address>=0x580000000ULL&&address<0x580020000ULL)path="SCRATCHPAD";
   else if(address>=0x80000000&&address<0x180000000ULL)path="DRAM";
   f.family="memory."+path+(f.memory.kind==iris::AccessKind::store||f.memory.kind==iris::AccessKind::sc?".store":f.memory.kind==iris::AccessKind::amo?".atomic":".load");f.bytes=f.memory.bytes;
  }else if(f.memory.decode==iris::MemoryDecode::vector){f.family=op==7?"memory.vector.load":"memory.vector.store";f.work=beats;f.bytes=v.vl->read()*v.vsew/8;
   const unsigned width=(raw>>12)&7,mop=(raw>>26)&3,lumop=(raw>>20)&31,nf=(raw>>29)+1;
   if(mop==0&&!(raw&(1u<<28))&&(width==0||width>=5)&&(lumop==0||lumop==8||lumop==16)){
    const unsigned eew=width==0?1:1u<<(width-4);const uint64_t bytes=lumop==8?uint64_t(nf)*32:uint64_t(nf)*v.vl->read()*eew;
    if(bytes&&bytes<=4096){f.memory.decode=iris::MemoryDecode::scalar;f.memory.kind=op==7?iris::AccessKind::load:iris::AccessKind::store;f.memory.address=cores_[hart]->get_state()->XPR.read_transport((raw>>15)&31).value;f.memory.bytes=bytes;f.bytes=bytes;f.work=(bytes+(hart==2?31:15))/(hart==2?32:16);f.dlen_beats=f.work;f.atl_beats=(bytes+(hart==2?7:31))/(hart==2?8:32);}
   }else f.family+=".address_pattern_uncalibrated";
  }else f.family="scalar.integer";
 }
 return f;
}
void iris_timing_adapter::empirical_retired(unsigned hart){
 const auto*fetch=completion_fetch(hart);if(!fetch)return;auto retired_insn=fetch->insn;if(profile_.empirical_icache&&uint32_t(retired_insn.bits())==0x0000100f){empirical_cache_->fence_i(hart,clock_.now());if(hart==2&&rocket_packets_)rocket_packet_redirect(cores_[hart]->get_state()->pc,"retired-fence-I",2);empirical_fetch_[hart].line=UINT64_MAX;empirical_fetch_[hart].response_ready=false;++empirical_fetch_[hart].generation;}
 Feature feature=pending_[hart]?pending_[hart]->feature:empirical_feature(hart,*fetch);
 if(completing_pure_){const auto&r=pure_[hart].instructions.at(*completing_pure_);if(r.empirical_load){feature=Feature{};feature.family="memory.DRAM.load";feature.bytes=1u<<r.memory_size;feature.memory={iris::MemoryDecode::scalar,iris::AccessKind::load,r.memory_address,unsigned(feature.bytes)};}}
 if(pending_[hart])++empirical_fallback_counts_[hart][feature.family];
 auto&total=features_[hart][feature.family];++total.instructions;total.work+=feature.work;total.bytes+=feature.bytes;total.macs+=feature.macs;total.dlen_beats+=feature.dlen_beats;total.atl_beats+=feature.atl_beats;
}
void iris_timing_adapter::empirical_write_prefix(const CounterRead&r){
 if(!feature_stream_||(r.csr!=0xb00&&r.csr!=0xc00))return;
 auto&out=*feature_stream_;out<<"{\"schema\":\"iris.empirical.prefix.v1\",\"hart\":"<<r.hart<<",\"sequence\":"<<r.sequence<<",\"value\":"<<r.value<<",\"pc\":"<<r.pc<<",\"raw\":"<<r.raw<<",\"csr\":"<<r.csr<<",\"destination\":"<<r.destination<<",\"result_discarded\":"<<(r.destination==0?"true":"false")<<",\"read_cycle\":"<<r.read_cycle<<",\"baseline_cycles\":";
 if(profile_.empirical_rules.empty()&&profile_.empirical_cache_rules.empty()&&profile_.empirical_instruction_rules.empty()&&profile_.empirical_branch_rules.empty())out<<r.read_cycle;else out<<"null";
 out<<",\"branch_history\":{\"resolved\":"<<empirical_branches_[r.hart].branches<<",\"resolved_mispredicts\":"<<empirical_branches_[r.hart].mispredicts<<"},\"resource_occupancy_scope\":\"global_shared_resources\",\"feature_semantics\":\"architecturally_retired_instruction_features\",\"memory_semantics\":\"accepted_timing_intents\",\"endpoint\":\"get_csr_before_current_instruction_retirement\",\"retired\":"<<r.retired<<",\"features\":{";
 bool first=true;for(const auto&[name,t]:r.features){if(!first)out<<',';first=false;out<<std::quoted(name)<<":{\"instructions\":"<<t.instructions<<",\"work\":"<<t.work<<",\"bytes\":"<<t.bytes<<",\"macs\":"<<t.macs<<",\"dlen_beats\":"<<t.dlen_beats<<",\"atl_beats\":"<<t.atl_beats<<'}';}
 out<<"},\"completed_resource_busy_cycles\":{";first=true;for(const auto&[name,n]:r.busy){if(!first)out<<',';first=false;out<<std::quoted(name)<<':'<<n;}
 out<<"},\"resource_occupancy_prefix\":{";first=true;for(const auto&[name,o]:r.occupancy){if(!first)out<<',';first=false;out<<std::quoted(name)<<":{\"union_cycles\":"<<o.union_cycles<<",\"lane_service_cycles\":"<<o.lane_service_cycles<<'}';}
 out<<"},\"memory\":{";first=true;for(const auto&[name,totals]:r.memory){if(!first)out<<',';first=false;out<<std::quoted(name)<<":{";bool ft=true;for(const auto&[key,n]:totals){if(!ft)out<<',';ft=false;out<<std::quoted(key)<<':'<<n;}out<<'}';}
 out<<"},\"pending_instruction_fetch\":";if(r.pending_fetch){const auto&f=*r.pending_fetch;out<<"{\"owner\":"<<f.owner<<",\"node\":"<<f.node<<",\"address\":"<<f.address<<",\"bytes\":"<<f.bytes<<",\"l1misses\":"<<f.l1_misses<<",\"l2misses\":"<<f.l2_misses<<",\"submitted\":"<<f.submitted<<",\"issued\":"<<(f.issued?"true":"false")<<",\"start\":"<<(f.issued?std::to_string(f.start):"null")<<",\"end\":"<<(f.issued?std::to_string(f.end):"null")<<'}';}else out<<"null";
 out<<",\"instruction_fetch_observation_scope\":"<<std::quoted(frontend_enabled(r.hart)?"source-Icache-acceptedA-until-sampled-eighthD;line-owner-not-current-PC-owner":"empirical-private-Icache-refill-owner")
    <<",\"source_fetch_sampled_beats\":"<<(r.source_fetch_sampled_beats?std::to_string(*r.source_fetch_sampled_beats):"null")
    <<",\"source_fetch_final_D_input_present\":"<<(r.source_fetch_final_input_present?"true":"false")
    <<",\"source_fetch_clock_phase\":";
 if(r.source_fetch_sampled_beats){
  out<<"{\"next_source_edge\":"<<r.source_fetch_next_edge<<",\"source_period\":"<<r.source_fetch_period
     <<",\"last_source_commit_edge\":"<<r.source_fetch_next_edge-r.source_fetch_period
     <<",\"final_graph_completed\":"<<(r.source_fetch_final_graph_completed?"true":"false")<<'}';
 }else out<<"null";
 out<<",\"scalar_fadd_pending\":{\"accepted_live\":"<<r.scalar_fp_accepted<<",\"front_queued\":"<<r.scalar_fp_queued<<",\"next_write_cycle\":"<<r.scalar_fp_next_write<<'}';
 out<<",\"memory_counter_units\":\"accesses=count accepted intents; hits/misses=count64B line probes; bytes=requested bytes including SC attempts\",\"async_compute_pending\":"<<(r.async_pending?"true":"false")<<",\"async_pending_count\":"<<r.async_pending_count<<",\"async_backend_end\":"<<r.async_backend_end<<",\"calibration_identity\":"<<std::quoted(profile_.empirical_identity)<<"}\n";out.flush();if(!out)throw std::runtime_error("IRIS_EMPIRICAL_FEATURE_OUTPUT_FAILED");
}
void iris_timing_adapter::empirical_write_totals(std::ostream&out)const{
 if(profile_.empirical_opu_entry)opu_write_totals(out);
 empirical_store_write_totals(out);write_rocket_packet_json(out);
 if(profile_.empirical_read_overlap)out<<",\"read_overlap_scope\":\"explicit-ordinary-scalar-DRAM-reads;own-copy-ready-at-matching-successful-response;peer-ordinary-read-compatible;writers-atomics-unknowns-coldfills-remain-ordered;approximate-tags-not-RTL-permissions\",\"warm_read_accepts\":"<<empirical_cache_->warm_read_accepts()<<",\"compatible_read_dependencies_omitted\":"<<empirical_cache_->compatible_read_dependencies_omitted();
 if(profile_.empirical_vme_shape_work)out<<",\"vme_work_basis\":{\"zero\":\"active-M-N16x16-subtiles;empty0\",\"MM\":\"unchanged-active-subtiles-times-logicalTK\",\"units\":\"accepted-sequencer-microops-not-latency\",\"source\":\"Saturn536774bd-OuterProductSequencer.scala98/124-126/149-152/277-285\",\"calibrated\":false}";
 out<<",\"load_front_scope\":"<<std::quoted(profile_.empirical_load_front?"aligned-DRAM-L1-hit;latched-MEM-response;precise-COM;intervening-coherence-conservative-fallback;dependent-load-pair-split":"disabled")<<",\"load_front_metrics\":[";for(unsigned h=0;h<empirical_load_metrics_.size();++h){if(h)out<<',';const auto&m=empirical_load_metrics_[h];out<<"{\"accepted\":"<<m.accepted<<",\"hit_responses\":"<<m.hit_responses<<",\"coherence_fallbacks\":"<<m.coherence_fallbacks<<",\"faults\":"<<m.faults<<",\"partial_transports\":"<<m.partial_transports<<",\"discarded_responses\":"<<m.discarded_responses<<'}';}out<<']';
 out<<",\"boundary_retry_ticks\":"<<empirical_boundary_retry_ticks_;
 out<<",\"fast_source_frontend_enabled\":"<<(profile_.saved_shuttle_frontend?"true":"false");
 out<<",\"pending_owned_load_responses\":"<<empirical_load_responses_.size();
 out<<",\"pending_async_backends\":[";for(unsigned h=0;h<empirical_async_.size();++h){if(h)out<<',';out<<(empirical_async_[h]?"true":"false");}out<<']';
 out<<",\"model_kind\":\"experimental_empirical\",\"calibration_identity\":"<<std::quoted(profile_.empirical_identity)<<",\"source_cuts_evaluated\":false,\"full_model_certified\":false,\"timing_2pct_certified\":false,\"branch_prediction_scope\":"<<std::quoted(profile_.saved_shuttle_frontend?"source-derived-32entryBTB-512entryBHT-sixRAS-F0F1F2-FIFO-Icache;harts0/1;hart2-lightweight-fallback":"lightweight_2bit_BHT_target_cache_not_RTL_frontend");
 out<<",\"counter_policy\":"<<std::quoted(profile_.source_counter_clock?"source-ungated-pre-edge-stall-stable-input-spans":"numeric-count-wfi-synthetic");
 out<<",\"async_compute_scope\":"<<std::quoted(profile_.empirical_async?(profile_.empirical_async_fadd?"finite-nonmemory-integer-RVV-VME-FADD;staged-VRF-fflags-knownness-FS;scalarFP-and-CSR-IRQ-drain":"finite-nonmemory-integer-RVV-and-VME-staged-numeric-publication"):"disabled-conservative-instruction-boundaries");
 out<<",\"fadd_scope\":"<<std::quoted(profile_.empirical_async_fadd?"M-mode-vfadd.vv-only;compute-FP8-FP16-BF16-FP32-FP64;Rocket-FP16-FP32-FP64;work=compute-DLENbeats/Rocket-VLelements;unfitted-work-duration;scalarFP-FCSR-IRQ-conservative-drains":"disabled");
 out<<",\"async_handoffs\":[";for(unsigned h=0;h<empirical_async_handoffs_.size();++h){if(h)out<<',';out<<empirical_async_handoffs_[h];}out<<']';
 out<<",\"scalar_fadd_scope\":"<<std::quoted(profile_.empirical_scalar_fadd?"finite-source-HSD-Shuttle-l4-Rocket-l3;late-FPR-local-flags-FS;conservative-IRQ-other-FP-domain-drain;feature-schema-v2":"disabled")<<",\"scalar_fadd_metrics\":[";for(unsigned h=0;h<scalar_fadd_.size();++h){if(h)out<<',';out<<"{\"hart\":"<<h<<",\"accepted\":"<<scalar_fadd_accepted_[h]<<",\"published\":"<<scalar_fadd_published_[h]<<",\"killed\":"<<scalar_fadd_killed_[h]<<",\"peak\":"<<scalar_fadd_peak_[h]<<",\"irq_drain_edges\":"<<scalar_fadd_irq_deferrals_[h]<<",\"pending\":"<<scalar_fadd_pending(h)<<'}';}out<<']';
 out<<",\"async_owner_limit\":"<<(profile_.empirical_async_two_owner?2:1);
 out<<",\"cache_scope\":\"source-geometry-explicit-LRU-approximation; scalar-L1D; unitstride-vector-bypasses-L1D-to-shared-L2; atomic-service-and-writeback-separation-unqualified\"";
 out<<",\"vector_memory_scope\":\"contiguous-span-requested-bytes; compute-ATL32B-Rocket-ATL8B; functional-effects-at-batched-response; common-outer-service-proxy; L2-hit-service-unqualified-without-vector-family-fit\"";
 out<<",\"icache_scope\":"<<std::quoted(profile_.saved_shuttle_frontend?"source-Shuttle-L1I-control-data-RAM-and-accepted-A-eightD;shared-L2-effective-service;Rocket-address-history-fallback":profile_.empirical_icache?"separate-L1I-shared-L2-address-history-refill-proxy":"instruction-cache-service-not-modeled");
 out<<",\"generic_boundary_usage\":[";bool first_hart=true;for(const auto&counts:empirical_fallback_counts_){if(!first_hart)out<<',';first_hart=false;out<<'{';bool f=true;for(const auto&[family,n]:counts){if(!f)out<<',';f=false;out<<std::quoted(family)<<':'<<n;}out<<'}';}out<<']';
 out<<",\"configured_empirical_families\":[";bool first_rule=true;for(const auto&r:profile_.empirical_rules){if(!first_rule)out<<',';first_rule=false;out<<"{\"hart\":"<<r.hart<<",\"family\":"<<std::quoted(r.family)<<",\"status\":"<<std::quoted(r.status)<<",\"source_sha256\":"<<std::quoted(r.source)<<",\"setup\":"<<r.setup<<",\"cycles_per_work\":"<<r.work<<",\"issue_interval\":"<<r.interval<<'}';}out<<']';

 out<<",\"per_hart_features\":[";bool first_h=true;for(const auto&features:features_){if(!first_h)out<<',';first_h=false;out<<'{';bool first=true;for(const auto&[name,t]:features){if(!first)out<<',';first=false;out<<std::quoted(name)<<":{\"instructions\":"<<t.instructions<<",\"work\":"<<t.work<<",\"bytes\":"<<t.bytes<<",\"macs\":"<<t.macs<<",\"dlen_beats\":"<<t.dlen_beats<<",\"atl_beats\":"<<t.atl_beats<<'}';}out<<'}';}out<<']';
 out<<",\"resource_occupancy_prefix\":{";bool first=true;for(const auto&[name,o]:clock_.occupancy_prefix()){if(!first)out<<',';first=false;out<<std::quoted(name)<<":{\"union_cycles\":"<<o.union_cycles<<",\"lane_service_cycles\":"<<o.lane_service_cycles<<'}';}out<<'}';
 out<<",\"per_hart_memory_features\":[";bool fh=true;for(const auto&paths:memory_features_){if(!fh)out<<',';fh=false;out<<'{';bool fp=true;for(const auto&[path,metrics]:paths){if(!fp)out<<',';fp=false;out<<std::quoted(path)<<":{";bool fm=true;for(const auto&[metric,n]:metrics){if(!fm)out<<',';fm=false;out<<std::quoted(metric)<<':'<<n;}out<<'}';}out<<'}';}out<<']';
}

void iris_timing_adapter::empirical_memory_feature(unsigned hart,const iris::empirical::Delta&d,bool write){
 auto&t=memory_features_[hart][iris::empirical::path_name(d.path)];++t["accesses"];++t[write?"writes":"reads"];t["bytes"]+=d.bytes;t["l1misses"]+=d.l1_misses;t["l2misses"]+=d.l2_misses;t["l1hits"]+=d.l1_hits;t["l2hits"]+=d.l2_hits;t["dirtywritebacks"]+=d.l2_dirty_victims;t["l1_dirty_victims"]+=d.l1_dirty_victims;t["same_bank_contenders"]+=d.same_bank_contenders;t["other_bank_contenders"]+=d.other_bank_contenders;t["shared_line_contenders"]+=d.shared_line_contenders;t["dirty_owner_forwards"]+=d.dirty_owner_forwards;t["coherence_invalidations"]+=d.coherence_invalidations;
}
