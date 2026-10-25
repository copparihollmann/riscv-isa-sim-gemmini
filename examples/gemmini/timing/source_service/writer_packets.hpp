#ifndef GEMMINI_WRITER_PACKETS_HPP
#define GEMMINI_WRITER_PACKETS_HPP
#include <algorithm>
#include <cstdint>
#include <limits>
#include <optional>
#include <vector>
namespace gemmini_annotated_spike {
// DMA.scala StreamWriter: maximize useful bytes, keep smaller size on ties.
// Masks are byte masks and include every beat of the chosen TL transaction.
struct WriterPacket {
  std::uint64_t address=0, bytes=0, useful_address=0, useful_bytes=0;
  std::vector<std::uint64_t> beat_masks;
  bool full=false;
};
inline std::optional<std::vector<WriterPacket>> writer_packets(
    std::uint64_t address,std::uint64_t bytes,std::uint64_t beat,
    std::uint64_t maximum,std::size_t budget=256) {
  if(!bytes || !beat || beat>64 || !maximum || maximum>4096 ||
      (beat&(beat-1)) || (maximum&(maximum-1)) || maximum<beat ||
      bytes-1>std::numeric_limits<std::uint64_t>::max()-address) return {};
  std::vector<WriterPacket> out;
  while(bytes) {
    if(out.size()>=budget)return {};
    std::uint64_t chosen=0,useful=0;
    for(auto size=beat;size<=maximum;size*=2) {
      const auto take=std::min(size-address%size,bytes);
      if(take>useful){useful=take;chosen=size;}
      if(size==maximum)break;
    }
    WriterPacket p;
    p.address=address/chosen*chosen;p.bytes=chosen;
    p.useful_address=address;p.useful_bytes=useful;
    p.full=useful==chosen && address==p.address;
    p.beat_masks.resize(chosen/beat);
    for(std::uint64_t i=0;i<chosen;++i)
      if(i>=address-p.address && i-(address-p.address)<useful)
        p.beat_masks[i/beat]|=std::uint64_t{1}<<(i%beat);
    out.push_back(std::move(p));bytes-=useful;
    if(bytes)address+=useful;
  }
  return out;
}
inline std::optional<std::vector<std::vector<WriterPacket>>> full_writer_rows(
    std::uint64_t address,std::uint64_t rows,std::uint64_t width,
    std::uint64_t stride,std::uint64_t beat,std::uint64_t maximum) {
  if(!rows || rows>256 || !width || !stride ||
      (rows-1 && stride>(std::numeric_limits<std::uint64_t>::max()-address)/(rows-1)))return {};
  std::vector<std::vector<WriterPacket>> out;
  std::size_t count=0;
  for(std::uint64_t r=0;r<rows;++r) {
    auto packets=writer_packets(address+r*stride,width,beat,maximum);
    if(!packets)return {};
    for(const auto &p:*packets)if(!p.full)return {};
    count+=packets->size();if(count>4096)return {};
    out.push_back(std::move(*packets));
  }
  return out;
}
inline std::optional<std::vector<std::vector<WriterPacket>>> one_beat_writer_rows(
    std::uint64_t address,std::uint64_t rows,std::uint64_t width,std::uint64_t stride){
  if(!rows||rows>16||!width||width>16||!stride||
     (rows-1&&stride>(UINT64_MAX-address)/(rows-1)))return {};
  std::vector<std::vector<WriterPacket>>out;
  for(std::uint64_t row=0;row<rows;++row){
    auto packets=writer_packets(address+row*stride,width,16,64);
    if(!packets||packets->size()!=1||packets->front().bytes!=16||packets->front().beat_masks.size()!=1)return {};
    out.push_back(std::move(*packets));
  }
  return out;
}
} // namespace gemmini_annotated_spike
#endif
