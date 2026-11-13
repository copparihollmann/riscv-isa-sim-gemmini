#include "saturn_timing.hpp"
#include "verilated.h"
#include <array>
#include <iostream>
#include <stdexcept>
using namespace iris::saturn;
int main(){try{
 VerilatedContext foreign;const char*argv[]={"foreign","+iris-owner=foreign"};foreign.commandArgs(2,argv);Verilated::threadContextp(&foreign);unsigned checks=0,refusals=0;
 auto same=[&]{if(Verilated::threadContextp()!=&foreign)throw std::runtime_error("Lifecycle leaked/deleted caller context");++checks;};
 auto reject=[&](auto f){bool refused=false;try{f();}catch(const std::invalid_argument&){refused=true;}if(!refused)throw std::runtime_error("Invalid constructor admitted");++refusals;same();};
 reject([&]{SaturnTimingCut bad(Profile::Compute128,2,17,ReferenceScope::ExplicitTwoStateWithExternalDefinedness);});
 reject([&]{SaturnTimingCut bad(Profile::Compute128,0,17,static_cast<ReferenceScope>(77));});
 for(const auto bad:std::array<std::string_view,3>{"not-a-plusarg","+verilator+seed+0",""})reject([&]{const std::array<std::string_view,1> args{bad};SaturnTimingCut bad_arg(Profile::Compute128,0,17,ReferenceScope::ExplicitTwoStateWithExternalDefinedness,args);});
 {SaturnTimingCut defaults(Profile::Rocket256,2,17,ReferenceScope::ExplicitTwoStateWithExternalDefinedness);same();if(!defaults.context_argument("iris-owner=").empty())throw std::runtime_error("Inherited foreign commandArgs");same();}
 same();const std::array<std::string_view,1>a_args{"+iris-owner=A"},b_args{"+iris-owner=B"};
 {SaturnTimingCut a(Profile::Compute128,0,17,ReferenceScope::ExplicitTwoStateWithExternalDefinedness,a_args);same();SaturnTimingCut b(Profile::Compute128,1,91,ReferenceScope::ExplicitTwoStateWithExternalDefinedness,b_args);same();a=std::move(b);same();if(a.hart()!=1||a.context_argument("iris-owner=")!="+iris-owner=B")throw std::runtime_error("Move-assignment lost owning context");same();SaturnTimingCut c(std::move(a));same();if(c.hart()!=1||c.context_argument("iris-owner=")!="+iris-owner=B")throw std::runtime_error("Move construction lost context");same();}
 same();std::cout<<"{\"constructor_refusals\":"<<refusals<<",\"caller_context_checks\":"<<checks<<",\"explicit_default_args_isolation\":true,\"move_ownership_checked\":true}\n";return 0;
}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
