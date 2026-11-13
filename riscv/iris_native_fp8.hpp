#ifndef IRIS_NATIVE_FP8_HPP
#define IRIS_NATIVE_FP8_HPP
// Exact integer implementation of Saturn SegmentedFMAPipe + rawUnroundedToFp8.
// Source pins: Saturn536774bd4c5e3bcd7813a4a0dc72fc87e5818532,
// HardFloat0ecaef097ce2accbd16a61613699450ed5533f29. No host FP or intermediate rounding.
#include <cstdint>
#include <algorithm>
#include <stdexcept>
namespace iris_fp8 {
using U = unsigned __int128;
using S = __int128;
struct Number { bool sign; unsigned mant; int power; bool inf, nan, signaling; };
struct Result { uint16_t bits; uint8_t flags; };
inline Number decode(uint8_t x, bool e5) {
  const unsigned m=e5?2:3, e=(x&127)>>m, f=x&((1u<<m)-1);
  const bool nan=e5?(e==31&&f):(e==15&&f==7);
  return {bool(x&128), e?((1u<<m)|f):f, (e?int(e):1)-(e5?15:7)-int(m),
          e5&&e==31&&!f,nan,e5&&e==31&&f==1};
}
inline unsigned top(U v) {unsigned b=0;while(v>>1){v>>=1;++b;}return b;}
inline Result ieee(S value,int power,bool negative_zero,unsigned eb,unsigned mb,unsigned rm,
                   bool is_inf=false,bool is_nan=false,bool invalid=false,bool special_sign=false) {
  const unsigned emax=(1u<<eb)-1,bias=(1u<<(eb-1))-1,signbit=eb+mb;
  if(is_nan||invalid)return {uint16_t((emax<<mb)|(1u<<(mb-1))),uint8_t(invalid?16:0)};
  if(is_inf)return {uint16_t((unsigned(special_sign)<<signbit)|(emax<<mb)),0};
  if(!value)return {uint16_t(unsigned(negative_zero)<<signbit),0};
  const bool sign=value<0;U mag=sign?U(-value):U(value);
  const int exponent=int(top(mag))+power;
  const int target=std::max(exponent-int(mb),1-int(bias)-int(mb));
  const int drop=target-power;
  U kept,rem=0;
  if(drop>0) {kept=mag>>drop;rem=mag-(kept<<drop);
    const U half=U(1)<<(drop-1);
    const bool inc=rm==0?(rem>half||(rem==half&&(kept&1))):rm==2?(rem&&sign):rm==3?(rem&&!sign):rm==4?rem>=half:false;
    kept+=inc;
  }else kept=mag<<(-drop);
  const unsigned sig=unsigned(sign)<<signbit;
  if(kept&&int(top(kept))+target>int(bias)) {
    const bool inf=rm==0||rm==4||(rm==2&&sign)||(rm==3&&!sign);
    return {uint16_t(sig|(inf?(emax<<mb):((emax<<mb)-1))),5};
  }
  const bool tiny=!kept||int(top(kept))+target<1-int(bias);
  const uint8_t flags=rem?(tiny?3:1):0;
  if(!kept)return {uint16_t(sig),flags};
  if(tiny)return {uint16_t(sig|unsigned(kept<<(target-(1-int(bias)-int(mb))))),flags};
  const unsigned high=top(kept);
  const unsigned fraction=unsigned(high>mb?kept>>(high-mb):kept<<(mb-high))&((1u<<mb)-1);
  const unsigned exp=int(high)+target+int(bias);
  return {uint16_t(sig|(exp<<mb)|fraction),flags};
}
inline Result fma(uint8_t ax,uint8_t bx,uint8_t cx,bool e5,unsigned rm,unsigned op=0,unsigned lane=1) {
  if(rm>4)throw std::runtime_error("IRIS_UNSUPPORTED_ROUNDING_MODE native FP8");
  auto a=decode(ax,e5),b=decode(bx,e5),c=decode(cx,e5);
  // Physical [D,H,BF16,E5M3,S,H,BF16,E5M3] pipes. Same-exp H widening
  // preserves sNaN; different-exp widening quiets it and drops conversion flags.
  const bool preserve_signaling=(lane&1)!=0;
  const bool ps=a.sign^b.sign^bool(op&2),cs=c.sign^bool(op&1);
  const bool invalid=(preserve_signaling&&(a.signaling||b.signaling||c.signaling)) ||
    (a.inf&&!b.nan&&!b.inf&&!b.mant)||(b.inf&&!a.nan&&!a.inf&&!a.mant)||
    (!a.nan&&!b.nan&&(a.inf||b.inf)&&c.inf&&(ps!=cs));
  const bool nan=a.nan||b.nan||c.nan;
  const bool inf=!nan&&!invalid&&(a.inf||b.inf||c.inf);
  const bool inf_sign=(a.inf||b.inf)?ps:cs;
  S sum=0;int q=0;bool zs=false;
  if(!nan&&!invalid&&!inf) {
    q=std::min(a.power+b.power,c.power);
    const U product=U(a.mant)*b.mant;
    const S p=S(product<<(a.power+b.power-q)),cv=S(U(c.mant)<<(c.power-q));
    sum=(ps?-p:p)+(cs?-cv:cv);
    zs=!product&&!c.mant&&ps==cs?ps:rm==2;
  }
  if(e5) {
    auto result=ieee(sum,q,zs,5,2,rm,inf,nan,invalid,inf_sign);
    if((result.bits&0x7c)==0x7c&&(result.bits&3))result.bits=0x7f;
    return result;
  }
  // E4M3 uses independently rounded IEEE E4M3 and IEEE E5M3, never sequential
  // conversion. Reproduce assembleOFPE4M3 exactly; all flags are hardwired zero.
  const auto r4=ieee(sum,q,zs,4,3,rm,inf,nan,invalid,inf_sign);
  const auto r5=ieee(sum,q,zs,5,3,rm,inf,nan,invalid,inf_sign);
  const unsigned exp=(r5.bits>>3)&31,frac=r5.bits&7;
  const bool special=(exp>>3)==3,overflow=exp==23;
  if(special||overflow) {
    if((special&&frac)||special||frac==7)return {0x7f,0};
    return {uint16_t((r4.bits&128)|0x78|frac),0};
  }
  return {r4.bits,0};
}
}
#endif
