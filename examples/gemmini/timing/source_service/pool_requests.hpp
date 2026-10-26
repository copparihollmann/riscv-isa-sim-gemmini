#ifndef GEMMINI_ORDERED_POOL_REQUESTS_HPP
#define GEMMINI_ORDERED_POOL_REQUESTS_HPP
#include <optional>
#include <vector>
#include <cstdint>
namespace gemmini_annotated_spike {
struct PoolReadoutRequest {
 std::optional<std::uint64_t> local_row;
 std::uint64_t output_address=0,bytes=0;
 bool pool=false,store=false;
};
// StoreController original y,x,window-y,window-x order. Padding is a
// garbage-address metadata request, not an invented accumulator row.
inline std::optional<std::vector<PoolReadoutRequest>> pool_readout_requests(
 std::uint64_t base,unsigned height,unsigned width,unsigned rows,unsigned cols,
 unsigned window,unsigned stride,unsigned upad,unsigned lpad,unsigned out_dim,
 std::uint64_t output,std::uint64_t pitch,unsigned channels,std::size_t budget=1048576){
 if(!height||!width||!rows||!cols||!window||!stride||!out_dim||!pitch||!channels||channels>16||
    std::uint64_t(rows)*cols>budget/window/window||
    base>UINT64_MAX-std::uint64_t(height)*width)return {};
 std::vector<PoolReadoutRequest>result;
 for(unsigned y=0;y<rows;++y)for(unsigned x=0;x<cols;++x){
   const auto pixel=std::uint64_t(y)*out_dim+x;
   if(pixel>(UINT64_MAX-output)/pitch||output+pixel*pitch>UINT64_MAX-channels)return {};
   const auto address=output+pixel*pitch;
   for(unsigned wy=0;wy<window;++wy)for(unsigned wx=0;wx<window;++wx){
     const auto iy=std::int64_t(std::uint64_t(y)*stride+wy)-upad;
     const auto ix=std::int64_t(std::uint64_t(x)*stride+wx)-lpad;
     std::optional<std::uint64_t>local;
     if(iy>=0&&ix>=0&&iy<height&&ix<width)local=base+std::uint64_t(iy)*width+ix;
     result.push_back({local,address,channels,wy!=0||wx!=0,wy+1==window&&wx+1==window});
   }
 }
 return result;
}
}
#endif
