#ifndef GEMMINI_READOUT_GEOMETRY_HPP
#define GEMMINI_READOUT_GEOMETRY_HPP
#include <cstdint>
namespace gemmini_annotated_spike {
// DMA.scala selects the power-of-two packet maximizing written bytes, breaking
// ties toward the smaller packet. An aligned power-of-two row is therefore one
// PutFull transaction. Other rows require byte masks or multiple transactions;
// their response semantics are deliberately not approximated by this network.
inline bool single_full_row_transactions(std::uint64_t address, std::uint64_t rows,
    std::uint64_t row_bytes, std::uint64_t stride, std::uint64_t beat_bytes,
    std::uint64_t max_request_bytes) {
  return rows && row_bytes && beat_bytes && max_request_bytes &&
      row_bytes>=beat_bytes && row_bytes<=max_request_bytes &&
      !(row_bytes&(row_bytes-1)) && row_bytes%beat_bytes==0 &&
      address%row_bytes==0 && (rows==1 || stride%row_bytes==0);
}
}
#endif
