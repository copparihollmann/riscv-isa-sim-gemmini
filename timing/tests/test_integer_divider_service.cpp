#include "integer_divider_timing.hpp"
#include <boost/multiprecision/cpp_int.hpp>
#include <cassert>
#include <random>
#include <iostream>
using namespace spike_timing;
using Big=boost::multiprecision::uint256_t;
// Literal register/edge interpreter of selected Multiplier.scala. It also
// computes actual quotient/remainder, independently checking early-out math.
std::pair<unsigned,std::uint64_t>rtl(std::uint64_t bits,std::uint64_t lhs,std::uint64_t rhs){
 const bool half=(bits&127)==0x3b,sign=!((bits>>12)&1),hi=(bits>>13)&1;
 auto extend=[&](std::uint64_t x)->std::uint64_t{if(!half)return x;const auto lo=std::uint32_t(x);return sign&&(lo>>31)?std::uint64_t(lo)|0xffffffff00000000ull:std::uint64_t(lo);};
 const auto a=extend(lhs),b=extend(rhs);const bool as=sign&&(a>>63),bs=sign&&(b>>63);
 const Big m64=(Big(1)<<64)-1,m65=(Big(1)<<65)-1;
 Big rem=a,divisor=Big(b)|(Big(bs)<<64);unsigned state=as||bs?1:3,count=0,cycles=0;bool resHi=false,neg=hi?as:as!=bs;
 auto result=[&](){return resHi?(rem>>65)&m64:rem&m64;};
 while(state!=7){assert(cycles<100);++cycles;
   const Big sub=((rem>>64)-divisor)&m65;
   if(state==1){if(bool(rem&(Big(1)<<63)))rem=(Big(0)-result())&m64;if(bool(divisor&(Big(1)<<63)))divisor=sub;state=3;}
   else if(state==5){rem=(Big(0)-result())&m64;state=7;resHi=false;}
   else{assert(state==3);const bool less=bool(sub&(Big(1)<<64));const bool div0=count==0&&!less;Big old=rem;
     rem=(((less?(old>>64)&m64:sub&m64)<<64)|(old&m64))<<1;rem|=unsigned(!less);
     if(count==64){state=neg?5:7;resHi=hi;}unsigned next=(count+1)&127;
     if(count==0&&!div0){auto msb=[](Big x){unsigned n=0;while(x>1){++n;x>>=1;}return n;};
       unsigned pos=~(msb(old&m64)-msb(divisor&m64))&63;if(pos>=1){rem=(old&m64)<<pos;next=pos;}}
     if(div0&&!hi)neg=false;count=next;
   }
 }
 std::uint64_t out=static_cast<std::uint64_t>(result());if(half)out=std::uint64_t(std::int64_t(std::int32_t(out)));
 return {cycles,out};
}
std::uint64_t expected(std::uint64_t bits,std::uint64_t a,std::uint64_t b){
 const bool half=(bits&127)==0x3b,sign=!((bits>>12)&1),rem=(bits>>13)&1;
 if(half){a=sign?std::uint64_t(std::int64_t(std::int32_t(a))):std::uint32_t(a);b=sign?std::uint64_t(std::int64_t(std::int32_t(b))):std::uint32_t(b);}
 std::uint64_t out;
 if(!b)out=rem?a:UINT64_MAX;
 else if(sign){const auto x=std::int64_t(a),y=std::int64_t(b);if(x==INT64_MIN&&y==-1)out=rem?0:a;else out=std::uint64_t(rem?x%y:x/y);}
 else out=rem?a%b:a/b;
 return half?std::uint64_t(std::int64_t(std::int32_t(out))):out;
}
int main(){
 std::mt19937_64 random(17);
 for(unsigned op:{0x33u,0x3bu})for(unsigned fn:{4u,5u,6u,7u}){
   const auto bits=(1u<<25)|(fn<<12)|op;
   for(auto [a,b]:std::vector<std::pair<std::uint64_t,std::uint64_t>>{{0,0},{0,1},{0,UINT64_MAX},{UINT64_MAX,0},{1ull<<63,UINT64_MAX},{1ull<<63,0},{0x80000000,UINT64_MAX},{0xffffffff,0},{UINT64_MAX,UINT64_MAX}}){
     const auto actual=rtl(bits,a,b);const auto service=integer_divider_service(bits,a,b);
     assert(actual.second==expected(bits,a,b));assert(service.latency==actual.first&&service.occupancy==actual.first+1);
   }
   for(unsigned i=0;i<1024;++i){const auto a=i<16?std::uint64_t(1)<<((i*7)%64):random();
     const auto b=i<16?(i<4?std::uint64_t(i):std::uint64_t(1)<<((i*11)%64)):random();
     const auto actual=rtl(bits,a,b);const auto service=integer_divider_service(bits,a,b);
     if(actual.second!=expected(bits,a,b)){std::cerr<<std::hex<<bits<<" "<<a<<" "<<b<<" got="<<actual.second<<" expected="<<expected(bits,a,b)<<std::dec<<" cycles="<<actual.first<<"\n";return 1;}assert(service.latency==actual.first&&service.occupancy==actual.first+1);
   }
 }
 assert(integer_divider_service((1u<<25)|(5u<<12)|0x33,1,1).latency==3);
 assert(integer_divider_service((1u<<25)|(5u<<12)|0x33,1,0).latency==65);
}
