#include "empirical_hazards.hpp"
#include "../timing/shuttle_issue.cpp"
#include <random>
#include <iostream>
int main(){
 std::mt19937_64 random(0x48415a415244ull);uint64_t checks=0;
 for(unsigned trial=0;trial<200000;++trial){
  std::vector<iris::shuttle::Bypass>entries;
  iris::empirical::IntegerHazardFold folded;
  for(unsigned n=unsigned(random()%33);n;--n){iris::shuttle::Bypass b{bool(random()&1),uint8_t(random()%32),bool(random()&1)};entries.push_back(b);folded.observe(b.valid,b.destination,b.can_bypass);}
  for(unsigned reg=0;reg<32;++reg){const bool expected=iris::shuttle::integer_hazard(reg,true,entries);if((folded.values()[reg]==iris::shuttle::Signal::yes)!=expected)throw std::runtime_error("source integer_hazard differential mismatch");++checks;}
 }
 unsigned refused=0;for(unsigned bad:{32u,255u}){try{iris::empirical::IntegerHazardFold fold;fold.observe(false,bad,true);}catch(const std::invalid_argument&){++refused;}}
 if(refused!=2)throw std::runtime_error("invalid destination guard missing");
 std::cout<<"PASS "<<checks<<" source-hazard comparisons; "<<refused<<" malformed destination refusals\n";
}
