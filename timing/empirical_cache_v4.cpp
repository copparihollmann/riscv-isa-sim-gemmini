#include "empirical_cache_v4.hpp"
#include <algorithm>
#include <limits>
#include <stdexcept>
#include <set>
namespace iris::empirical {
CacheConfigV4 iris_geometry_v4(){return {{{{64,2,1,64},{64,2,1,64},{64,4,1,64}}},{{{64,2,1,64},{64,2,1,64},{128,2,1,64}}},{512,4,4,64}};}
void CacheHistoryV4::validate_geometry(Geometry g){
 auto power=[](unsigned x){return x && !(x&(x-1));};
 if(!power(g.sets)||!power(g.ways)||!power(g.banks)||!power(g.line_bytes)||g.line_bytes<8||g.sets>65536||g.ways>64||g.banks>64)throw std::invalid_argument("IRIS_EMPIRICAL_CACHE_GEOMETRY");
}
CacheHistoryV4::CacheHistoryV4(CacheConfigV4 c):config_(c){
 validate_geometry(c.l2);l2_.geometry=c.l2;l2_.lines.resize(size_t(c.l2.sets)*c.l2.ways*c.l2.banks);
 for(unsigned h=0;h<3;++h){validate_geometry(c.l1d[h]);if(c.l1d[h].line_bytes!=c.l2.line_bytes)throw std::invalid_argument("IRIS_EMPIRICAL_CACHE_LINE_MISMATCH");l1_[h].geometry=c.l1d[h];l1_[h].lines.resize(size_t(c.l1d[h].sets)*c.l1d[h].ways*c.l1d[h].banks);validate_geometry(c.l1i[h]);if(c.l1i[h].line_bytes!=c.l2.line_bytes)throw std::invalid_argument("IRIS_EMPIRICAL_ICACHE_LINE_MISMATCH");l1i_[h].geometry=c.l1i[h];l1i_[h].lines.resize(size_t(c.l1i[h].sets)*c.l1i[h].ways*c.l1i[h].banks);}
}
void CacheHistoryV4::advance(uint64_t t){if(t<tick_)throw std::invalid_argument("IRIS_EMPIRICAL_CACHE_TIME_REVERSED");tick_=t;}
Path CacheHistoryV4::classify(unsigned h,uint64_t a,uint64_t n,uint64_t&canonical){
 if(h>=3||!n||n>4096||a>std::numeric_limits<uint64_t>::max()-n)throw std::invalid_argument("IRIS_EMPIRICAL_CACHE_ACCESS");
 auto inside=[&](uint64_t b,uint64_t size){return a>=b&&a-b<size&&n<=size-(a-b);};
 canonical=a;
 if(a>=0x70080000ull&&a<0x70100000ull){
  if(h==2)throw std::invalid_argument("IRIS_EMPIRICAL_CACHE_HART2_TCM_ALIAS");
  // The alias wraps every128KiB; crossing its canonical TCM extent is not a
  // single request and must be split by the caller's actual memory protocol.
  canonical=0x70000000ull+h*0x20000ull+(a&0x1ffffull);
  if(n>0x20000ull-(a&0x1ffffull))throw std::invalid_argument("IRIS_EMPIRICAL_CACHE_ALIAS_CROSSING");
  return Path::LocalTCM;
 }
 for(unsigned t=0;t<2;++t)if(inside(0x70000000ull+t*0x20000ull,0x20000ull))return h==t?Path::LocalTCM:Path::RemoteTCM;
 if(inside(0x580000000ull,0x20000ull))return Path::Scratchpad;
 if(inside(0x80000000ull,0x100000000ull))return Path::DRAM;
 // Do not silently classify a partly valid DRAM/TCM transaction as MMIO.
 auto overlaps=[&](uint64_t b,uint64_t size){return a<b+size&&a+n>b;};
 if(overlaps(0x70000000ull,0x40000ull)||overlaps(0x580000000ull,0x20000ull)||overlaps(0x80000000ull,0x100000000ull))throw std::invalid_argument("IRIS_EMPIRICAL_CACHE_REGION_CROSSING");
 return Path::Uncached;
}
unsigned CacheHistoryV4::bank(const Cache&c,uint64_t line){return unsigned(line%c.geometry.banks);}
size_t CacheHistoryV4::set_start(const Cache&c,uint64_t line){return size_t((line/c.geometry.banks)%c.geometry.sets*c.geometry.banks+bank(c,line))*c.geometry.ways;}
CacheHistoryV4::Line*CacheHistoryV4::find(Cache&c,uint64_t line){const size_t at=set_start(c,line);for(unsigned w=0;w<c.geometry.ways;++w)if(c.lines[at+w].valid&&c.lines[at+w].tag==line)return &c.lines[at+w];return nullptr;}
CacheHistoryV4::Line CacheHistoryV4::install(Cache&c,uint64_t line,bool dirty){
 if(age_==std::numeric_limits<uint64_t>::max())throw std::overflow_error("IRIS_EMPIRICAL_CACHE_AGE_HORIZON");
 if(auto*p=find(c,line)){p->age=++age_;p->dirty|=dirty;return {};}
 size_t at=set_start(c,line),slot=at;
 for(unsigned w=0;w<c.geometry.ways;++w){size_t p=at+w;if(!c.lines[p].valid){slot=p;break;}if(c.lines[p].age<c.lines[slot].age)slot=p;}
 Line old=c.lines[slot];c.lines[slot]={line,++age_,true,dirty};return old;
}
void CacheHistoryV4::install_l2(uint64_t line,bool dirty,Delta&d){
 Line evicted=install(l2_,line,dirty);if(!evicted.valid)return;
 bool writeback=evicted.dirty;
 for(auto&cache:l1_)if(auto*p=find(cache,evicted.tag)){writeback|=p->dirty;p->valid=false;++d.coherence_invalidations;}
 if(writeback)++d.l2_dirty_victims;
}
Delta CacheHistoryV4::begin(Access a){return begin_internal(a,false,false);}
Delta CacheHistoryV4::begin_instruction(Access a){if(a.write)throw std::invalid_argument("IRIS_EMPIRICAL_ICACHE_WRITE");return begin_internal(a,true,false);}
Delta CacheHistoryV4::begin_vector(Access a){return begin_internal(a,false,true);}
Delta CacheHistoryV4::begin_internal(Access a,bool instruction,bool vector){
 if(pending_.count(a.id))throw std::invalid_argument("IRIS_EMPIRICAL_CACHE_DUPLICATE_OWNER");
 if(!a.id||a.id<=last_id_)throw std::invalid_argument("IRIS_EMPIRICAL_CACHE_NONMONOTONIC_OWNER");
 uint64_t canonical=0;Path path=classify(a.hart,a.address,a.bytes,canonical);
 if(a.tick<tick_)throw std::invalid_argument("IRIS_EMPIRICAL_CACHE_TIME_REVERSED");
 // Validate full request before mutation (including age-headroom bound).
 const auto first=canonical/config_.l2.line_bytes,last=(canonical+a.bytes-1)/config_.l2.line_bytes;
 if(last-first+1>(std::numeric_limits<uint64_t>::max()-age_)/8)throw std::overflow_error("IRIS_EMPIRICAL_CACHE_AGE_HORIZON");
 advance(a.tick);Delta d;d.path=path;d.canonical_address=canonical;d.bytes=a.bytes;d.lines=last-first+1;
 Pending request{a,path,instruction,{},{},{}};std::set<uint64_t> waits;
 for(uint64_t line=first;line<=last;++line){request.lines.push_back(line);request.banks.push_back(unsigned(line%(path==Path::DRAM?config_.l2.banks:2)));}
 std::set<unsigned> same,other,shared;
 for(const auto&[id,p]:pending_){
  auto domain=[this](Path q,uint64_t line){if(q==Path::DRAM)return uint64_t(4);if(q==Path::Scratchpad)return uint64_t(3);if(q==Path::LocalTCM||q==Path::RemoteTCM)return uint64_t(1+(line*config_.l2.line_bytes-0x70000000ull)/0x20000ull);return uint64_t(0);};
  if(path==Path::Uncached||domain(path,request.lines.front())!=domain(p.path,p.lines.front()))continue;
  if(p.access.hart==a.hart)continue;
  bool overlap=false,samebank=false;
  for(size_t i=0;i<request.lines.size();++i){
   if(std::find(p.lines.begin(),p.lines.end(),request.lines[i])!=p.lines.end())overlap=true;
   if(std::find(p.banks.begin(),p.banks.end(),request.banks[i])!=p.banks.end())samebank=true;
  }
  (samebank?same:other).insert(p.access.hart);
  if(overlap){shared.insert(p.access.hart);waits.insert(id);}
 }
 d.same_bank_contenders=same.size();d.other_bank_contenders=other.size();d.shared_line_contenders=shared.size();
 // Same-hart uncompleted ownership is also a dependency, including identical
 // reads and stores. It is not reported as a multicore contender.
 for(const auto&[id,p]:pending_)for(uint64_t line:request.lines)if(std::find(p.lines.begin(),p.lines.end(),line)!=p.lines.end())waits.insert(id);
 d.wait_for.assign(waits.begin(),waits.end());request.dependencies=d.wait_for;
 if(path==Path::DRAM&&vector){
  for(uint64_t line:request.lines){
   // Direct ATL uncached Get/Put shares L2, not the scalar private Dcache.
   // Dirty owners must preserve untouched bytes before a partial Put.
   for(auto&cache:l1_)if(auto*owner=find(cache,line))if(owner->dirty){++d.dirty_owner_forwards;owner->dirty=false;install_l2(line,true,d);}
   if(find(l2_,line))++d.l2_hits;else ++d.l2_misses;
   install_l2(line,a.write,d);
   if(a.write)for(auto&cache:l1_)if(auto*copy=find(cache,line)){copy->valid=false;++d.coherence_invalidations;}
  }
 }else if(path==Path::DRAM){
  auto&mine=instruction?l1i_[a.hart]:l1_[a.hart];
  for(uint64_t line:request.lines){
   auto*hit=find(mine,line);
   if(hit){++d.l1_hits;install(mine,line,a.write);}
   else{
    ++d.l1_misses;
    for(unsigned h=0;h<3;++h)if(instruction||h!=a.hart)if(auto*owner=find(l1_[h],line))if(owner->dirty){++d.dirty_owner_forwards;owner->dirty=false;install_l2(line,true,d);}
    if(find(l2_,line))++d.l2_hits;else ++d.l2_misses;
    install_l2(line,false,d);
    Line victim=install(mine,line,a.write);
    if(victim.valid&&victim.dirty){++d.l1_dirty_victims;install_l2(victim.tag,true,d);}
   }
   if(a.write)for(unsigned h=0;h<3;++h)if(h!=a.hart)if(auto*p=find(l1_[h],line)){p->valid=false;++d.coherence_invalidations;}
  }
 }
 pending_.emplace(a.id,std::move(request));last_id_=a.id;return d;
}
bool CacheHistoryV4::data_hit(unsigned hart,uint64_t address,uint64_t bytes)const{
 if(hart>=3||!bytes||bytes>4096||address>std::numeric_limits<uint64_t>::max()-bytes)throw std::invalid_argument("IRIS_EMPIRICAL_CACHE_QUERY_ACCESS");
 // This predicts the narrow cacheable DRAM path only. Other addresses return
 // false and retain their existing architectural permission/fault handlers.
 if(address<0x80000000ull||address>=0x180000000ull||bytes>0x180000000ull-address)return false;
 const uint64_t first=address/config_.l2.line_bytes,last=(address+bytes-1)/config_.l2.line_bytes;const Cache&cache=l1_[hart];
 for(uint64_t line=first;line<=last;++line){
  bool hit=false;const size_t at=set_start(cache,line);for(unsigned way=0;way<cache.geometry.ways;++way)if(cache.lines[at+way].valid&&cache.lines[at+way].tag==line){hit=true;break;}
  if(!hit)return false;
  // Timing tags may have been installed at accepted intent. Any pending owner
  // on this line prohibits using a tag as if its response had already arrived.
  for(const auto&[id,p]:pending_)if(std::find(p.lines.begin(),p.lines.end(),line)!=p.lines.end())return false;
 }
 return true;
}
void CacheHistoryV4::complete(uint64_t id,uint64_t t){auto i=pending_.find(id);if(i==pending_.end())throw std::invalid_argument("IRIS_EMPIRICAL_CACHE_COMPLETION_OWNER");if(t<i->second.access.tick||t<tick_)throw std::invalid_argument("IRIS_EMPIRICAL_CACHE_TIME_REVERSED");for(uint64_t dependency:i->second.dependencies)if(pending_.count(dependency))throw std::logic_error("IRIS_EMPIRICAL_CACHE_PREMATURE_DEPENDENT_COMPLETION");advance(t);pending_.erase(i);}
void CacheHistoryV4::fence_i(unsigned hart,uint64_t t){if(hart>=3)throw std::invalid_argument("IRIS_EMPIRICAL_ICACHE_HART");if(t<tick_)throw std::invalid_argument("IRIS_EMPIRICAL_CACHE_TIME_REVERSED");for(const auto&[id,p]:pending_)if(p.access.hart==hart)throw std::logic_error("IRIS_EMPIRICAL_ICACHE_FENCE_WITH_PENDING");advance(t);for(auto&line:l1i_[hart].lines)line={};}
void CacheHistoryV4::reset_timing_tags(uint64_t t){if(!pending_.empty())throw std::logic_error("IRIS_EMPIRICAL_CACHE_RESET_WITH_PENDING");advance(t);for(auto&c:l1_)for(auto&l:c.lines)l={};for(auto&cache:l1i_)for(auto&line:cache.lines)line={};for(auto&l:l2_.lines)l={};age_=0;}
} // namespace iris::empirical
