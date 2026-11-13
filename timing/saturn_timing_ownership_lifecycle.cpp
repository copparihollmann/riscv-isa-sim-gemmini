#include "saturn_timing.hpp"
#include <verilated.h>
#include <iostream>
#include <stdexcept>
using namespace iris::saturn;
int main(){try{
 VerilatedContext caller;const char*args[]={"ownership-lifecycle","+iris_owner=foreign"};caller.commandArgs(2,args);Verilated::threadContextp(&caller);unsigned refusals=0,checks=0,destructions=0;
 const auto own=[&](){if(Verilated::threadContextp()!=&caller)throw std::runtime_error("Ownership SDK leaked foreign caller context");++checks;};
 const auto reject=[&](auto fn){bool failed=false;try{fn();}catch(const std::exception&){failed=true;}if(!failed)throw std::runtime_error("Expected constructor/phase refusal was absent");++refusals;own();};
 for(auto p:{Profile::Compute128,Profile::Rocket256})for(unsigned seed:{0u,17u}){
  const auto h=p==Profile::Compute128?0u:2u;
  reject([&]{SaturnTimingCut bad(p,p==Profile::Compute128?2:0,seed,ReferenceScope::ExplicitTwoStateWithExternalDefinedness);});
  reject([&]{SaturnTimingCut bad(p,h,seed,static_cast<ReferenceScope>(88));});
  reject([&]{const std::string_view badarg[]={"+verilator+seed+123"};SaturnTimingCut bad(p,h,seed,ReferenceScope::ExplicitTwoStateWithExternalDefinedness,badarg);});
  {
   const std::string_view plusargs[]={"+iris_owner=source-unit"};SaturnTimingCut unit(p,h,seed,ReferenceScope::ExplicitTwoStateWithExternalDefinedness,plusargs);own();
   reject([&]{unit.sample_ownership();});
   ReferenceInputs input;input.words.resize(unit.input_fields(p).size());for(unsigned n=0;n<unit.input_fields(p).size();++n)if(unit.input_fields(p)[n].name=="reset")input.words[n]=1;
   unit.evaluate(input);own();auto first=unit.sample_ownership(42);own();auto second=unit.sample_ownership(43);own();if(first.words!=second.words||first.source_edge||second.source_edge||first.uncore_tick!=42||second.uncore_tick!=43)throw std::runtime_error("Ownership sampling changed source state/clock");++checks;
   if(unit.context_argument("iris_owner=")!="+iris_owner=source-unit")throw std::runtime_error("Ownership method queried wrong context arguments");own();
   SaturnTimingCut moved(std::move(unit));own();if(moved.sample_ownership(44).words!=first.words)throw std::runtime_error("Move changed ownership snapshot");own();moved.commit();own();reject([&]{moved.sample_ownership();});
  }
  // Both the moved-to owned context and moved-from object are now destroyed.
  own();++destructions;
  if(std::string(caller.commandArgsPlusMatch("iris_owner="))!="+iris_owner=foreign")throw std::runtime_error("Destructor left a dead source context active");++checks;
 }
 std::cout<<"{\"constructor_phase_refusals\":"<<refusals<<",\"foreign_context_state_checks\":"<<checks<<",\"explicit_post_destructor_checks\":"<<destructions<<"}\n";return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
