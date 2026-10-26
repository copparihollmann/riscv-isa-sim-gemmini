#ifndef SPIKE_TIMING_FETCH_PARCEL_BUFFER_HPP
#define SPIKE_TIMING_FETCH_PARCEL_BUFFER_HPP
#include <cstdint>
#include <optional>
#include <stdexcept>
namespace spike_timing {
// Selected fetchWidth2/decodeWidth1 IBuf. This models only the one retained
// halfword after an actual fetch, never an unobserved fetch/FQ/prediction.
class FetchParcelBuffer {
 std::optional<std::uint64_t>parcel_;
 public:
 struct Plan{std::uint64_t address,bytes;bool retained;};
 Plan plan(std::uint64_t pc,unsigned length)const{
   if((pc&1)||(length!=2&&length!=4)||pc>UINT64_MAX-8)throw std::invalid_argument("invalid RV64C fetch parcel geometry");
   const bool retained=parcel_==std::optional<std::uint64_t>{pc};
   if(retained&&length==2)return {pc,0,true};
   const auto start=retained?pc+2:pc&~std::uint64_t{3};
   const auto end=(pc+length+3)&~std::uint64_t{3};
   return {start,end-start,retained};
 }
 void commit(std::uint64_t pc,unsigned length,std::uint64_t next_pc,bool redirect_or_fence,const Plan&p){
   parcel_.reset();
   if(redirect_or_fence||next_pc!=pc+length||!p.bytes)return;
   const auto end=p.address+p.bytes;
   if(end==next_pc+2)parcel_=next_pc;
 }
 void reset(){parcel_.reset();}
};
}
#endif
