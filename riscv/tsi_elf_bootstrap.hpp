#ifndef SPIKE_TIMING_TSI_ELF_BOOTSTRAP_HPP
#define SPIKE_TIMING_TSI_ELF_BOOTSTRAP_HPP
#include <algorithm>
#include <array>
#include <cstdint>
#include <fstream>
#include <limits>
#include <iterator>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace spike_timing {
// Address-only replay of selected FESVR ELF64 EXEC -> memif(4,1024) -> TSI.
// Data bytes cannot affect line identity: clear_chunk and write_chunk use the
// same ordered 1024-byte decomposition. Edge RMW writes visit the same line.
// Default mode refuses replacement-dependent contents. A separately reviewed
// serialized TSI64 directory contract can instead replay every Get/Put. It does
// not model FireSim boot, +loadmem, other payloads or a CPU's private caches.
struct TsiElfBootstrap {
  struct Chunk { std::uint64_t address,bytes; };
  struct Transaction { std::uint64_t address,bytes; bool write; };
  // Count consecutive TSI beats without retaining one history object per
  // beat. Iteration still visits every original Get/Put in the original order;
  // this is software storage compression, never one aggregate cache request.
  class DirectoryTransactions {
    struct Run {Transaction first;std::uint64_t count;};
    std::vector<Run>runs_;std::uint64_t count_=0;
   public:
    void push_back(Transaction event){
      if(count_==UINT64_MAX)throw std::invalid_argument("loader directory count overflow");
      if(!runs_.empty()){
        auto&last=runs_.back();
        if(last.first.write==event.write&&last.first.bytes==event.bytes&&
           last.count<=(UINT64_MAX-last.first.address)/8&&last.first.address+last.count*8==event.address){
          ++last.count;++count_;return;
        }
      }
      // At most one ordered discontinuity per memif chunk/edge. A malicious
      // ELF cannot grow the representation beyond the existing chunk bound.
      if(runs_.size()>=(1<<20))throw std::invalid_argument("loader bootstrap directory-run bound exceeded");
      runs_.push_back({event,1});++count_;
    }
    std::uint64_t size()const{return count_;}
    std::size_t stored_runs()const{return runs_.size();}
    Transaction operator[](std::uint64_t index)const{
      for(const auto&run:runs_){if(index<run.count)return {run.first.address+index*8,run.first.bytes,run.first.write};index-=run.count;}
      throw std::out_of_range("loader directory transaction index");
    }
    class Iterator {
      const DirectoryTransactions*owner_;std::size_t run_;std::uint64_t offset_;
     public:
      using iterator_category=std::input_iterator_tag;
      using value_type=Transaction;using difference_type=std::ptrdiff_t;using pointer=void;using reference=Transaction;
      Iterator(const DirectoryTransactions*owner,std::size_t run,std::uint64_t offset=0):owner_(owner),run_(run),offset_(offset){}
      Transaction operator*()const{const auto&r=owner_->runs_.at(run_);return {r.first.address+offset_*8,r.first.bytes,r.first.write};}
      Iterator&operator++(){if(++offset_==owner_->runs_.at(run_).count){++run_;offset_=0;}return *this;}
      bool operator==(const Iterator&other)const{return owner_==other.owner_&&run_==other.run_&&offset_==other.offset_;}
      bool operator!=(const Iterator&other)const{return !(*this==other);}
    };
    Iterator begin()const{return {this,0};}Iterator end()const{return {this,runs_.size()};}
  };
  std::vector<Chunk> writes;
  DirectoryTransactions directory_reads;
  std::vector<std::uint64_t> lines;
  std::uint64_t bytes=0;
};
inline TsiElfBootstrap tsi_elf_bootstrap(const std::string &path,
                                        std::uint64_t sets,std::uint64_t line_bytes,
                                        bool serialized_tsi64_directory=false) {
  if(!sets || !line_bytes || (line_bytes&(line_bytes-1)) || sets>(1<<20))
    throw std::invalid_argument("loader bootstrap cache geometry unsupported");
  std::ifstream file(path,std::ios::binary);
  if(!file)throw std::invalid_argument("loader bootstrap cannot open original ELF");
  file.seekg(0,std::ios::end);const auto end=file.tellg();
  if(end<64)throw std::invalid_argument("loader bootstrap ELF header missing");
  const auto size=std::uint64_t(end);
  auto read=[&](std::uint64_t at,unsigned char*out,std::size_t n){
    if(at>size || n>size-at || at>std::uint64_t(std::numeric_limits<std::streamoff>::max()))
      throw std::invalid_argument("loader bootstrap ELF input bounds");
    file.clear();file.seekg(static_cast<std::streamoff>(at));file.read(reinterpret_cast<char*>(out),n);
    if(!file)throw std::invalid_argument("loader bootstrap ELF read failed");
  };
  auto u=[](const unsigned char*p,unsigned n){std::uint64_t v=0;for(unsigned i=0;i<n;++i)v|=std::uint64_t(p[i])<<(8*i);return v;};
  std::array<unsigned char,64>h{};read(0,h.data(),h.size());
  if(h[0]!=127 || h[1]!='E' || h[2]!='L' || h[3]!='F' || h[4]!=2 || h[5]!=1 ||
     h[6]!=1 || u(h.data()+16,2)!=2 || u(h.data()+18,2)!=243 || u(h.data()+20,4)!=1)
    throw std::invalid_argument("loader bootstrap requires ELF64 LE RISC-V EXEC");
  const auto off=u(h.data()+32,8),entry=u(h.data()+54,2),count=u(h.data()+56,2);
  if(entry!=56 || !count || count>128 || off>size || count>(size-off)/entry)
    throw std::invalid_argument("loader bootstrap program headers unsupported");
  TsiElfBootstrap out;std::map<std::uint64_t,std::uint64_t> per_set;std::set<std::uint64_t> seen_lines;
  auto transaction=[&](std::uint64_t address,std::uint64_t bytes,bool write){
    // TSIToTileLink emits one64-bit masked Put per beat and awaits its Dack.
    // A memif edge RMW Get is four bytes; every beat is a separate directory
    // request under the separately reviewed serialized-loader contract.
    while(bytes){
      const auto n=std::min(bytes,8-(address&7));
      out.directory_reads.push_back({write?address&~7ULL:address,write?std::uint64_t(8):n,write});
      address+=n;bytes-=n;
    }
  };
  auto chunk=[&](std::uint64_t address,std::uint64_t bytes){
    if(!bytes || bytes>1024 || (address&3) || (bytes&3) || bytes-1>UINT64_MAX-address || out.writes.size()>=(1<<20))
      throw std::invalid_argument("loader bootstrap chunk exceeds bounds");
    out.writes.push_back({address,bytes});out.bytes+=bytes;
    transaction(address,bytes,true);
    const auto last=(address+bytes-1)/line_bytes;
    for(auto line=address/line_bytes;;++line){
      const auto inserted=per_set.emplace(line%sets,line);
      if(!serialized_tsi64_directory && !inserted.second && inserted.first->second!=line)
        throw std::invalid_argument("loader bootstrap replacement-dependent initial cache set");
      if(seen_lines.insert(line).second)out.lines.push_back(line);
      if(line==last)break;
    }
  };
  auto write=[&](std::uint64_t address,std::uint64_t bytes){
    if(bytes>UINT64_MAX-address || bytes>(1ULL<<30))
      throw std::invalid_argument("loader bootstrap PT_LOAD span exceeds bounds");
    // memif writes leading RMW, trailing RMW, then aligned body (not sorted).
    if(bytes && (address&3)){const auto n=std::min(bytes,4-(address&3));transaction(address&~3ULL,4,false);chunk(address&~3ULL,4);address+=n;bytes-=n;}
    if(bytes&3){const auto n=bytes&3;transaction(address+bytes-n,4,false);chunk(address+bytes-n,4);bytes-=n;}
    for(std::uint64_t p=0;p<bytes;p+=1024)chunk(address+p,std::min(std::uint64_t(1024),bytes-p));
  };
  for(std::uint64_t i=0;i<count;++i){
    std::array<unsigned char,56>p{};read(off+i*entry,p.data(),p.size());if(u(p.data(),4)!=1)continue;
    const auto at=u(p.data()+8,8),address=u(p.data()+24,8),filesz=u(p.data()+32,8),memsz=u(p.data()+40,8);
    if(filesz>memsz || at>size || filesz>size-at || memsz>UINT64_MAX-address)
      throw std::invalid_argument("loader bootstrap PT_LOAD invalid");
    if(!memsz)continue;
    write(address,filesz);write(address+filesz,memsz-filesz);
  }
  if(out.lines.empty())throw std::invalid_argument("loader bootstrap has no loadable lines");
  return out;
}
} // namespace spike_timing
#endif
