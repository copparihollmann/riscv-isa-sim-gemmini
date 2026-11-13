#ifndef IRIS_FPCOMP_HPP
#define IRIS_FPCOMP_HPP
#include <cstdint>
#include <stdexcept>
namespace iris_cmp {
inline uint64_t mask(unsigned w){return w==64?~uint64_t(0):(uint64_t(1)<<w)-1;}
inline uint64_t sign(unsigned w){return uint64_t(1)<<(w-1);}
inline unsigned fraction(unsigned w){return w==16?10:w==32?23:52;}
inline uint64_t infinity(unsigned w){return (mask(w)>>1)&~((uint64_t(1)<<fraction(w))-1);}
inline bool nan(uint64_t v,unsigned w){return (v&infinity(w))==infinity(w)&&(v&((uint64_t(1)<<fraction(w))-1));}
inline bool equal(uint64_t a,uint64_t b,unsigned w){return a==b||((a&~sign(w))==0&&(b&~sign(w))==0);}
inline bool less(uint64_t a,uint64_t b,unsigned w){
 if(equal(a,b,w))return false;
 if((a^b)&sign(w))return a&sign(w);
 return a&sign(w)?a>b:a<b;
}
inline uint64_t element(uint64_t a,uint64_t b,unsigned w,unsigned f6){
 a&=mask(w);b&=mask(w);const bool an=nan(a,w),bn=nan(b,w),eq=equal(a,b,w),lt=less(a,b,w);
 if(f6==4||f6==5||f6==6||f6==7){
  if(an&&bn)return infinity(w)|(uint64_t(1)<<(fraction(w)-1));
  if(an)return b;
  if(bn)return a;
  return ((f6<6&&lt)||(f6>=6&&!lt&&!eq))?a:b;
 }
 if(f6>=8&&f6<=10){
  const uint64_t s=f6==8?(b&sign(w)):f6==9?(~b&sign(w)):((a^b)&sign(w));
  return (a&~sign(w))|s;
 }
 if(f6==0x1c)return an||bn||!eq;
 if(an||bn)return 0;
 if(f6==0x18)return eq;
 if(f6==0x1b)return lt;
 if(f6==0x19)return lt||eq;
 if(f6==0x1d)return !lt&&!eq;
 if(f6==0x1f)return !lt;
 throw std::runtime_error("IRIS_UNSUPPORTED_FPCOMP opcode");
}
inline uint8_t flags(const uint64_t* a,const uint64_t* b,unsigned lanes,unsigned w){
 const unsigned fw=w==64?32:16;const auto fm=mask(fw);
 for(unsigned i=0;i<lanes;++i)for(unsigned j=0;j<w;j+=fw)
  if(nan((a[i]>>j)&fm,fw)||nan((b[i]>>j)&fm,fw))return 16;
 return 0;
}
}
#endif
