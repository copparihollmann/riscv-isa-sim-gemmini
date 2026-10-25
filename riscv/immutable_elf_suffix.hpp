#ifndef MERLIN_IMMUTABLE_ELF_SUFFIX_HPP
#define MERLIN_IMMUTABLE_ELF_SUFFIX_HPP
#include <merlin_timing/instruction_suffix.hpp>
#include <array>
#include <cstdint>
#include <fstream>
#include <limits>
#include <optional>
#include <string>
#include <vector>
// Host-only immutable primary-image reader. No guest fetch/MMU/cache access,
// architectural stepping, speculative instruction execution or register reads.
class ImmutableElfSuffix {
 struct Segment {std::uint64_t address,offset,size;};
 std::ifstream file_;std::uint64_t size_=0;std::vector<Segment> segments_;
 static std::uint64_t u(const unsigned char*p,unsigned n){std::uint64_t v=0;for(unsigned i=0;i<n;++i)v|=std::uint64_t(p[i])<<(8*i);return v;}
 bool read(std::uint64_t offset,unsigned char*out,std::size_t n){
  if(offset>size_ || n>size_-offset || offset>std::uint64_t(std::numeric_limits<std::streamoff>::max()))return false;
  file_.clear();file_.seekg(static_cast<std::streamoff>(offset));file_.read(reinterpret_cast<char*>(out),n);return bool(file_);
 }
 public:
 explicit ImmutableElfSuffix(const std::string&path):file_(path,std::ios::binary){
  if(!file_)return;file_.seekg(0,std::ios::end);const auto length=file_.tellg();if(length<64)return;size_=std::uint64_t(length);
  std::array<unsigned char,64>h{};if(!read(0,h.data(),h.size()) || h[0]!=127 || h[1]!='E' || h[2]!='L' || h[3]!='F' || h[4]!=2 || h[5]!=1 || u(h.data()+18,2)!=243)return;
  const auto offset=u(h.data()+32,8),entry=u(h.data()+54,2),count=u(h.data()+56,2);
  if(entry<56 || count>128 || offset>size_ || entry>size_ || count>(size_-offset)/entry)return;
  for(std::uint64_t i=0;i<count;++i){
   std::array<unsigned char,56>p{};if(!read(offset+i*entry,p.data(),p.size())){segments_.clear();return;}
   if(u(p.data(),4)!=1)continue;const auto flags=u(p.data()+4,4);if(!(flags&1) || flags&2)continue;
   const auto off=u(p.data()+8,8),addr=u(p.data()+16,8),bytes=u(p.data()+32,8),mem=u(p.data()+40,8);
   if(bytes>mem || off>size_ || bytes>size_-off || bytes>UINT64_MAX-addr){segments_.clear();return;}
   segments_.push_back({addr,off,bytes});
  }
 }
 std::optional<merlin_timing::ImmutableInstructionV1> instruction(std::uint64_t pc){
  std::optional<std::uint64_t>offset;
  for(const auto&s:segments_)if(pc>=s.address && pc-s.address<s.size){
   if(offset || s.size-(pc-s.address)<2)return {};offset=s.offset+pc-s.address;
  }
  if(!offset)return {};std::array<unsigned char,4>b{};if(!read(*offset,b.data(),2))return {};
  const unsigned length=(b[0]&3)==3?4:2;if(length==4 && !read(*offset,b.data(),4))return {};
  // Source cannot cross the selected immutable executable segment boundary.
  bool contained=false;for(const auto&s:segments_)if(pc>=s.address && pc-s.address<=s.size && length<=s.size-(pc-s.address))contained=true;
  const auto bits=u(b.data(),length);if(!contained || (length==4 && (bits&31)==31))return {};
  return merlin_timing::ImmutableInstructionV1{pc,bits,length};
 }
};
#endif
