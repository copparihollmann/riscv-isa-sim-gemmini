#pragma once
#include <array>
#include <algorithm>
namespace iris::noc::source_contract {
inline constexpr std::array<std::uint16_t,48> network0={552,616,680,744,936,1152,1192,5121,8744,8808,8872,8936,9128,9344,9384,13313,16936,17000,17064,17128,17320,17536,17576,21505,25128,25192,25256,25320,25512,25728,25768,29697,33320,33384,33448,33512,33704,33920,33960,37889,41512,41576,41640,41704,41896,42112,42152,46081};
inline constexpr std::array<std::uint16_t,30> network1={160,168,296,360,4129,8352,8360,8488,8552,12321,16544,16552,16680,16744,20513,24736,24744,24872,24936,28705,32928,32936,33064,33128,36897,41120,41128,41256,41320,45089};
inline constexpr std::array<std::uint8_t,9> ingress0={4,6,8,10,12,14,16,18,20};
inline constexpr std::array<std::uint8_t,4> ingress1={7,9,11,13};
template<class T> inline bool contains(const T& table,unsigned x){return std::find(table.begin(),table.end(),x)!=table.end();}
}
