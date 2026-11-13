#include "saturn_timing.hpp"
#include <verilated.h>
#include <iostream>
#include <stdexcept>
using namespace iris::saturn;
int main(){try{
 VerilatedContext caller;const char*args[]={"guard-host","+iris_activity_owner=guard"};caller.commandArgs(2,args);Verilated::threadContextp(&caller);
 unsigned refusals=0,checks=0;
 const auto owner=[&](){if(Verilated::threadContextp()!=&caller)throw std::runtime_error("Activity API changed caller context");++checks;};
 const auto refuses=[&](auto action){bool failed=false;try{action();}catch(const std::exception&){failed=true;}if(!failed)throw std::runtime_error("Missing activity phase refusal");++refusals;owner();};
 for(auto profile:{Profile::Compute128,Profile::Rocket256}){
  SaturnTimingCut unit(profile,profile==Profile::Compute128?0:2,17,ReferenceScope::ExplicitTwoStateWithExternalDefinedness);owner();
  refuses([&]{unit.sample_activity();});
  ReferenceInputs input;input.words.resize(unit.input_fields(profile).size());
  const auto fields=unit.input_fields(profile);unsigned reset=0;for(unsigned n=0;n<fields.size();++n)if(fields[n].name=="reset")reset=n;
  input.words[reset]=1;
  unit.evaluate(input);owner();auto a=unit.sample_activity(123);owner();auto b=unit.sample_activity(124);owner();
  if(a.words!=b.words||a.source_edge!=0||a.uncore_tick!=123||b.uncore_tick!=124||unit.edges()!=0)throw std::runtime_error("Read-only activity sample changed state/time");++checks;
  unit.evaluate(input);owner();if(unit.sample_activity().words!=a.words)throw std::runtime_error("Same-edge settle changed activity");++checks;
  unit.commit();owner();refuses([&]{unit.sample_activity();});
  const auto before=unit.inspect_dispatch_registers();owner();if(before.source_edge!=1||before.next_debug_id||before.allocated_mask)throw std::runtime_error("Actual reset did not clear dispatch state");++checks;
  input.words.pop_back();refuses([&]{unit.evaluate(input);});refuses([&]{unit.sample_activity();});
  input.words.push_back(0);input.words[reset]=0;unit.evaluate(input);auto moved=std::move(unit);owner();
  if(moved.sample_activity(1).source_edge!=1||moved.edges()!=1)throw std::runtime_error("Move lost sampled source phase");++checks;owner();moved.commit();owner();
 }
 std::cout<<"{\"phase_refusals\":"<<refusals<<",\"state_context_checks\":"<<checks<<"}\n";return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
