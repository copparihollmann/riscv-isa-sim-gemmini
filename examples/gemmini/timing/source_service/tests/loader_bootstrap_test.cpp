#include "riscv/tsi_elf_bootstrap.hpp"
#include "merlin_timing/engine.hpp"
#include <cassert>
#include <cstdio>
#include <fstream>
#include <functional>
#include <string>
#include <vector>
int main(int argc,char**argv){
  assert(argc==2);const std::string path=argv[1];std::vector<unsigned char>b(4096);
  auto put=[&](unsigned off,std::uint64_t v,unsigned n){for(unsigned i=0;i<n;++i)b.at(off+i)=(v>>(8*i))&255;};
  b[0]=127;b[1]='E';b[2]='L';b[3]='F';b[4]=2;b[5]=1;b[6]=1;
  put(16,2,2);put(18,243,2);put(20,1,4);put(32,64,8);put(54,56,2);put(56,1,2);
  put(64,1,4);put(72,256,8);put(80,0x90000000,8);put(88,0x80000001,8);put(96,7,8);put(104,1031,8);
  auto save=[&]{std::ofstream f(path,std::ios::binary);f.write(reinterpret_cast<const char*>(b.data()),b.size());};save();
  const auto p=spike_timing::tsi_elf_bootstrap(path,1024,64);
  // p_paddr, not p_vaddr. File leading RMW then body; BSS body1024.
  assert(p.writes.size()==3 && p.writes[0].address==0x80000000 && p.writes[0].bytes==4);
  assert(p.writes[1].address==0x80000004 && p.writes[1].bytes==4);
  assert(p.writes[2].address==0x80000008 && p.writes[2].bytes==1024);
  assert(p.lines.size()==17 && p.bytes==1032);
  assert(p.directory_reads.size()==131);
  assert(!p.directory_reads[0].write && p.directory_reads[0].address==0x80000000 && p.directory_reads[0].bytes==4);
  assert(p.directory_reads[1].write && p.directory_reads[1].address==0x80000000 && p.directory_reads[1].bytes==8);
  assert(p.directory_reads[2].write && p.directory_reads[2].address==0x80000000);
  assert(p.directory_reads[3].address==0x80000008);
  merlin_timing::SetAssociativeCache shared({1024,8,64}),private_cache({64,8,64});
  for(auto l:p.lines){const auto r=shared.access(l*64,true);assert(!r.hit && !r.evicted_line);}
  assert(shared.probe(0x80000000).hit && shared.probe(0x80000000).dirty);
  assert(!shared.probe(0x90000000).hit && !private_cache.probe(0x80000000).hit);
  auto denied=[&]{bool refused=false;try{spike_timing::tsi_elf_bootstrap(path,1024,64);}catch(const std::invalid_argument&){refused=true;}assert(refused);};
  put(104,65537,8);save();denied(); // same-set conflict: no guessed replacement
  const auto full=spike_timing::tsi_elf_bootstrap(path,1024,64,true);
  assert(full.lines.size()==1025 && full.directory_reads.size()>8192);
  // More than the old million-event history ceiling; exact serialized
  // directory Get/Put sequence is streamed from a bounded run representation.
  put(88,0x80000000,8);put(96,0,8);put(104,16*1024*1024,8);save();
  const auto large=spike_timing::tsi_elf_bootstrap(path,1024,64,true);
  assert(large.directory_reads.size()==2*1024*1024&&large.directory_reads.stored_runs()==1);
  assert(large.writes.size()==16384&&large.lines.size()==262144);
  std::uint64_t index=0;
  for(const auto&transaction:large.directory_reads){assert(transaction.write&&transaction.bytes==8&&transaction.address==0x80000000+index*8);++index;}
  assert(index==large.directory_reads.size());
  // Mixed edge RMW and overlapping same-address writes preserve order and
  // remain distinct transactions, including accesses to one physical line.
  assert(p.directory_reads.stored_runs()==3);
  std::vector<spike_timing::TsiElfBootstrap::Transaction> expanded;
  for(const auto&transaction:p.directory_reads)expanded.push_back(transaction);
  assert(expanded.size()==131&&!expanded[0].write&&expanded[1].address==expanded[2].address&&expanded[1].write&&expanded[2].write);
  put(88,0x80000001,8);put(96,7,8);
  put(104,1031,8);put(16,3,2);save();denied(); // relocated DYN unsupported
  put(16,2,2);put(96,4097,8);save();denied(); // invalid source range
  std::remove(path.c_str());
}
