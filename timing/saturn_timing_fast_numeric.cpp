#include "iris_fp8.hpp"
#include <stdexcept>
// Pure numeric cone. Pipeline validity, destination, register values and write
// priority remain in the source-derived SV. Never alter guest SoftFloat state.
extern "C" unsigned iris_saturn_fp8_fma(unsigned a,unsigned b,unsigned c,unsigned fa,unsigned fb,unsigned rm){
 if(a>255||b>255||fa>1||fb>1||rm>4)throw std::invalid_argument("Unqualified OPU numeric format/rounding input");
 IrisSoftfloatScope scope(rm);
 return f32_mulAdd(float32_t{iris_fp8_to_f32(a,fa)},float32_t{iris_fp8_to_f32(b,fb)},float32_t{c}).v;
}
