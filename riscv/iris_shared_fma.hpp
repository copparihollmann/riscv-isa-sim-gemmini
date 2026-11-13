#ifndef IRIS_SHARED_FMA_HPP
#define IRIS_SHARED_FMA_HPP
// Saturn SharedFPFMA.scala: one scalar-FPU request per element, ignored
// widening-converter exceptions, full FPU flags even when VRF wmask is zero.
namespace iris_shared {
using iris_fma::Kind;
using iris_fma::H;using iris_fma::S;using iris_fma::D;
inline uint64_t input(uint64_t raw,Kind in,Kind out,unsigned rm) {
  IrisSoftfloatScope ignored_conversion_flags(rm);
  if(in==out)return in==H?uint16_t(raw):in==S?uint32_t(raw):raw;
  if(in==H&&out==S)return f16_to_f32(float16_t{uint16_t(raw)}).v;
  if(in==S&&out==D)return f32_to_f64(float32_t{uint32_t(raw)}).v;
  throw std::runtime_error("IRIS_UNSUPPORTED_DATATYPE: unverified shared-FPU conversion");
}
inline uint64_t fused(uint64_t a,uint64_t b,uint64_t c,Kind out,unsigned rm,unsigned cmd,uint8_t& flags) {
  IrisSoftfloatScope scope(rm);
  if(cmd&2)a^=iris_fma::signbit(out);
  if(cmd&1)c^=iris_fma::signbit(out);
  uint64_t result;
  if(out==H)result=f16_mulAdd(float16_t{uint16_t(a)},float16_t{uint16_t(b)},float16_t{uint16_t(c)}).v;
  else if(out==S)result=f32_mulAdd(float32_t{uint32_t(a)},float32_t{uint32_t(b)},float32_t{uint32_t(c)}).v;
  else if(out==D)result=f64_mulAdd(float64_t{a},float64_t{b},float64_t{c}).v;
  else throw std::runtime_error("IRIS_UNSUPPORTED_DATATYPE: hart2 has no BF16 shared FPU");
  flags|=softfloat_exceptionFlags;
  return result;
}
inline uint64_t operation(unsigned f6,Kind in,uint64_t raw_a,uint64_t raw_b,uint64_t raw_c,unsigned rm,uint8_t& flags) {
  const bool wide=f6>=0x30,wide_input=f6==0x34||f6==0x36;
  if(in==iris_fma::BF||(wide&&in==D))
    throw std::runtime_error("IRIS_UNSUPPORTED_DATATYPE: unsupported shared-FPU width");
  const Kind out=wide?(in==S?D:S):in;
  uint64_t a=iris_shared::input(raw_a,wide_input?out:in,out,rm),b=iris_shared::input(raw_b,in,out,rm),c=iris_shared::input(raw_c,out,out,rm);
  unsigned cmd=0;
  if(f6==0||f6==2||f6==0x27||f6==0x30||f6==0x32||wide_input) {
    c=b;b=iris_fma::one(out);cmd=(f6==2||f6==0x32||f6==0x36)?1:f6==0x27?2:0;
  } else if(f6==0x24||f6==0x38)c=(a^b)&iris_fma::signbit(out);
  else {
    const unsigned cmds[4]={0,3,1,2};cmd=cmds[f6&3];
    if(!wide&&f6<0x2c){const auto old=a;a=c;c=old;}
  }
  return iris_shared::fused(a,b,c,out,rm,cmd,flags);
}
inline uint64_t add(uint64_t accum,uint64_t value,Kind in,Kind out,unsigned rm,uint8_t& flags) {
  const auto a=iris_shared::input(accum,out,out,rm),b=iris_shared::input(value,in,out,rm);
  return iris_shared::fused(a,iris_fma::one(out),b,out,rm,0,flags);
}
}
#endif
