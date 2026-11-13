// Optional address-history instruction miss service. Numeric code execution
// remains Spike-owned; this is an explicitly empirical tag/queue approximation.
bool iris_timing_adapter::empirical_fetch_ready(unsigned hart,uint64_t pc,unsigned bytes){
 if(!profile_.empirical_icache)return true;
 auto&f=empirical_fetch_[hart];if(f.owner)return false;
 // The physical refill returns cache LINES, not a credit for one PC.
 // Our own pending owner above prevents using early-installed tags.
 if(pc<0x80000000ULL||pc>=0x180000000ULL){++memory_features_[hart]["ICACHE.NON_DRAM_UNQUALIFIED"]["accesses"];return true;}
 if(empirical_cache_->instruction_hit(hart,pc,bytes)){
  const auto d=empirical_cache_->touch_instruction(hart,pc,bytes,clock_.now());auto&stats=memory_features_[hart]["ICACHE.DRAM"];++stats["accesses"];stats["bytes"]+=d.bytes;stats["l1hits"]+=d.l1_hits;return true;
 }
 const auto owner=next_cache_owner_++;auto d=empirical_cache_->begin_instruction({owner,hart,pc,bytes,false,clock_.now()});
 auto&stats=memory_features_[hart]["ICACHE."+std::string(iris::empirical::path_name(d.path))];++stats["accesses"];stats["bytes"]+=d.bytes;stats["l1hits"]+=d.l1_hits;stats["l1misses"]+=d.l1_misses;stats["l2hits"]+=d.l2_hits;stats["l2misses"]+=d.l2_misses;
 double cost=0,interval=1;for(const auto&r:profile_.empirical_cache_rules)if(r.hart==hart){cost=r.l1*d.l1_misses+r.outer*d.l2_misses;interval=r.outer_interval*d.l2_misses;break;}
 for(const auto&r:profile_.empirical_instruction_rules)if(r.hart==hart){cost=r.l1*d.l1_misses+r.outer*d.l2_misses;interval=r.interval*d.l2_misses;break;}
 if(!std::isfinite(cost)||cost>profile_.max_cycles)throw std::runtime_error("IRIS_EMPIRICAL_ICACHE_COST_OUTSIDE_HORIZON");
 if(d.wait_for.empty()&&cost==0){empirical_cache_->complete(owner,clock_.now());f.line=pc/64;return true;}
 iris::Op op{hart,"empirical.icache-refill",d.l2_misses&&(!profile_.empirical_cache_rules.empty()||!profile_.empirical_instruction_rules.empty())?"empirical.outer":"empirical.icache"+std::to_string(hart),uint64_t(std::max(1.0,std::ceil(cost))),uint64_t(std::max(1.0,std::ceil(interval)))};
 op.retires=false;op.pc=pc;op.bytes=64*d.l1_misses;op.issue_period=profile_.harts[hart].divider;
 for(const auto id:d.wait_for){auto at=cache_nodes_.find(id);if(at==cache_nodes_.end())throw std::logic_error("IRIS_EMPIRICAL_ICACHE_PENDING_OWNER_MISSING");op.deps.push_back(at->second);}
 f.owner=owner;f.address=pc;f.bytes=bytes;f.l1_misses=d.l1_misses;f.l2_misses=d.l2_misses;blocked_[hart]=true;op.on_complete=[this,hart,owner,pc]{auto&f=empirical_fetch_[hart];if(f.owner!=owner)throw std::logic_error("IRIS_EMPIRICAL_ICACHE_RESPONSE_OWNER");empirical_cache_->complete(owner,clock_.now());cache_nodes_.erase(owner);f.owner.reset();f.line=pc/64;f.response_ready=false;blocked_[hart]=false;};cache_nodes_[owner]=clock_.issue(std::move(op));return false;
}

void iris_timing_adapter::empirical_fetch_consume(unsigned,uint64_t,unsigned){}
