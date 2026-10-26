#ifndef GEMMINI_READER_PACKETS_HPP
#define GEMMINI_READER_PACKETS_HPP
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <vector>
namespace gemmini_annotated_spike {
struct ReaderRowFragment {
  std::size_t destination;std::uint64_t mask,source_offset,bytes,required_beat;
  bool destination_complete;
};
struct ReaderPacket {
  std::uint64_t address,bytes,shift,useful; std::size_t row; bool last;
  std::vector<ReaderRowFragment> outputs{};
};
// DMA.scala read_packets.reduce: maximize useful bytes, strict tie retains
// the smaller power-of-two Get. This is packet geometry, not a timing price.
inline std::vector<ReaderPacket> reader_packets(std::uint64_t source,
    std::uint64_t rows,std::uint64_t columns,std::uint64_t pitch,
    std::uint64_t beat,std::uint64_t maximum,std::uint64_t maximum_columns=16,
    std::uint64_t local_row_bytes=16) {
  std::vector<ReaderPacket> out;
  if(beat!=16 || maximum!=64 || !rows || rows>16 || !columns || columns>maximum_columns || maximum_columns>127 || (rows>1 && pitch<columns) ||
     (local_row_bytes!=16 && local_row_bytes!=64))
    return out;
  for(std::size_t row=0;row<rows;++row) {
    if(row && pitch>(std::numeric_limits<std::uint64_t>::max()-source)/row)return {};
    auto current=source+row*pitch,left=columns;
    while(left) {
      std::uint64_t size=beat,useful=0;
      for(auto candidate=beat;candidate<=maximum;candidate*=2) {
        auto bytes=std::min(candidate-current%candidate,left);
        if(bytes>useful){size=candidate;useful=bytes;}
      }
      if(!useful || out.size()>=64 || current>std::numeric_limits<std::uint64_t>::max()-useful)return {};
      ReaderPacket packet{current-current%size,size,current%size,useful,row,useful==left};
      const auto column_before=columns-left;
      for(std::uint64_t sent=0;sent<useful;) {
        const auto column=column_before+sent,band=column/local_row_bytes,offset=column%local_row_bytes;
        const auto count=std::min<std::uint64_t>(local_row_bytes-offset,useful-sent);
        // BeatMerger.out.valid waits a full row of useful bytes OR the end
        // of this transaction, even when the first destination is partial.
        const auto threshold=sent+std::min<std::uint64_t>(local_row_bytes,useful-sent);
        const auto required=(packet.shift+threshold+15)/16-1;
        const auto end=column+count;
        const auto mask=count==64?~std::uint64_t{0}:((std::uint64_t{1}<<count)-1)<<offset;
        packet.outputs.push_back({std::size_t(band*rows+row),mask,
            sent,count,required,end==std::min<std::uint64_t>((band+1)*local_row_bytes,columns)});
        sent+=count;
      }
      out.push_back(std::move(packet));
      current+=useful;left-=useful;
    }
  }
  return out;
}
}
#endif
