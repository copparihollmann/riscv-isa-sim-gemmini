#ifndef IRIS_IEEE_FMA_HPP
#define IRIS_IEEE_FMA_HPP
// Source-exact compute SegmentedFMAPipe IEEE/BF16 behavior. SoftFloat performs
// the one final fused rounding; physical widening is exact for finite operands.
// Saturn536774bd4c5e3bcd7813a4a0dc72fc87e5818532 FPFMAPipe.scala199-375.
namespace iris_fma {
enum Kind { H, BF, S, D };
inline unsigned width(Kind k){return k==D?64:k==S?32:16;}
inline unsigned exponent(Kind k){return k==D?11:k==S||k==BF?8:5;}
inline unsigned fraction(Kind k){return width(k)-exponent(k)-1;}
inline uint64_t signbit(Kind k){return uint64_t(1)<<(width(k)-1);}
inline uint64_t one(Kind k){return k==D?0x3ff0000000000000ULL:k==S?0x3f800000:k==BF?0x3f80:0x3c00;}
inline bool nan(uint64_t v,Kind k){const unsigned m=fraction(k),e=exponent(k);return ((v>>m)&((1u<<e)-1))==((1u<<e)-1)&&(v&((uint64_t(1)<<m)-1));}
inline uint64_t canonical(Kind k){return (((uint64_t(1)<<exponent(k))-1)<<fraction(k))|(uint64_t(1)<<(fraction(k)-1));}
inline Kind physical(Kind out,unsigned lane){
 // Per64bit segments [D,H,S,H], [D,BF,S,BF], [D,S], [D].
 if(out==D)return D;
 if(out==S)return lane%2?S:D;
 switch(lane%4){case 0:return D;case 2:return S;default:return out;}
}
inline uint64_t input(uint64_t raw,Kind in,Kind out,unsigned lane){
 // RecFNToRecFN same-exp widening shifts recoded bits without quieting;
 // different-exp widening canonicalizes NaNs and ignores its invalid flag.
 if(nan(raw,in)&&exponent(in)!=exponent(physical(out,lane)))raw=canonical(in);
 if(in==out)return raw;
 if(in==BF&&out==S)return raw<<16; // same exp8; preserve signalingness.
 if(in==H&&out==S)return f16_to_f32(float16_t{uint16_t(raw)}).v;
 if(in==S&&out==D)return f32_to_f64(float32_t{uint32_t(raw)}).v;
 throw std::runtime_error("IRIS_UNSUPPORTED_DATATYPE: unverified compute FMA conversion");
}
inline uint64_t fused(uint64_t a,uint64_t b,uint64_t c,Kind out,unsigned rm,unsigned cmd,uint8_t& flags){
 IrisSoftfloatScope scope(rm);
 if(cmd&2)a^=signbit(out);if(cmd&1)c^=signbit(out);
 uint64_t bits;
 switch(out){
  case H:bits=f16_mulAdd(float16_t{uint16_t(a)},float16_t{uint16_t(b)},float16_t{uint16_t(c)}).v;break;
  case BF:bits=bf16_mulAdd(float16_t{uint16_t(a)},float16_t{uint16_t(b)},float16_t{uint16_t(c)}).v;break;
  case S:bits=f32_mulAdd(float32_t{uint32_t(a)},float32_t{uint32_t(b)},float32_t{uint32_t(c)}).v;break;
  default:bits=f64_mulAdd(float64_t{a},float64_t{b},float64_t{c}).v;break;
 }
 // SegmentedFMAPipe wires narrower.io.invalidExc (Bool), not exceptionFlags,
 // into UInt5. Hence invalid becomes bit0 and all rounding flags disappear.
 flags|=bool(softfloat_exceptionFlags&softfloat_flag_invalid);
 return bits;
}
}
#endif
