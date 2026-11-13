#include "serial_memory.hpp"
#include "fased_service.hpp"
#include "verilated.h"
#include <cstdlib>
#include <iostream>
#include <limits>
#include <memory>
#include <new>
#include <stdexcept>
#include <string>
namespace allocation_failure {
thread_local bool enabled=false;
thread_local unsigned count=0,target=0;
void edge(){if(enabled&&++count==target)throw std::bad_alloc();}
}
void*operator new(std::size_t n){allocation_failure::edge();if(auto*p=std::malloc(n?n:1))return p;throw std::bad_alloc();}
void*operator new[](std::size_t n){return::operator new(n);}
void operator delete(void*p)noexcept{std::free(p);}
void operator delete[](void*p)noexcept{std::free(p);}
void operator delete(void*p,std::size_t)noexcept{std::free(p);}
void operator delete[](void*p,std::size_t)noexcept{std::free(p);}
void*operator new(std::size_t n,std::align_val_t a){allocation_failure::edge();void*p=nullptr;if(posix_memalign(&p,std::size_t(a),n?n:1))throw std::bad_alloc();return p;}
void*operator new[](std::size_t n,std::align_val_t a){return::operator new(n,a);}
void operator delete(void*p,std::align_val_t)noexcept{std::free(p);}
void operator delete[](void*p,std::align_val_t)noexcept{std::free(p);}
void operator delete(void*p,std::size_t,std::align_val_t)noexcept{std::free(p);}
void operator delete[](void*p,std::size_t,std::align_val_t)noexcept{std::free(p);}
namespace {
unsigned checks=0,injections=0,successful_constructions=0;
void require(bool ok,const std::string&message){++checks;if(!ok)throw std::runtime_error(message);}
template<class Factory>void run(const char*name,Factory factory,bool constructor_only){
  VerilatedContext foreign;foreign.commandArgs(0,static_cast<const char**>(nullptr));Verilated::threadContextp(&foreign);
  if(!constructor_only){
    auto first=factory();require(Verilated::threadContextp()==&foreign,std::string(name)+"_constructor_context_leak");
    auto second=factory();require(Verilated::threadContextp()==&foreign,std::string(name)+"_peer_constructor_context_leak");
    successful_constructions+=2;
    *first=std::move(*second);require(Verilated::threadContextp()==&foreign,std::string(name)+"_move_assignment_context_leak");
    *first=std::move(*first);require(Verilated::threadContextp()==&foreign,std::string(name)+"_self_move_context_leak");
    second.reset();require(Verilated::threadContextp()==&foreign,std::string(name)+"_moved_from_destructor_context_leak");
    first.reset();require(Verilated::threadContextp()==&foreign,std::string(name)+"_destructor_context_leak");
  }
  allocation_failure::count=0;allocation_failure::target=std::numeric_limits<unsigned>::max();allocation_failure::enabled=true;
  auto baseline=factory();allocation_failure::enabled=false;unsigned constructor_allocations=allocation_failure::count;++successful_constructions;baseline.reset();
  if(!constructor_only)require(Verilated::threadContextp()==&foreign,std::string(name)+"_baseline_destructor_context_leak");
  Verilated::threadContextp(&foreign);require(constructor_allocations<=4096,std::string(name)+"_allocation_frontier_exceeds_test_bound");
  unsigned failures=0;
  for(unsigned point=1;point<=constructor_allocations+4;++point){
    Verilated::threadContextp(&foreign);allocation_failure::count=0;allocation_failure::target=point;allocation_failure::enabled=true;
    bool threw=false;
    try{auto model=factory();allocation_failure::enabled=false;++successful_constructions;model.reset();}
    catch(const std::bad_alloc&){allocation_failure::enabled=false;threw=true;++failures;++injections;}
    catch(...){allocation_failure::enabled=false;throw;}
    if(threw)require(Verilated::threadContextp()==&foreign,std::string(name)+"_constructor_unwind_context_leak_at_"+std::to_string(point));
    else if(!constructor_only)require(Verilated::threadContextp()==&foreign,std::string(name)+"_destructor_context_leak_after_allocation_sweep");
    // Constructor-only historical controls intentionally do not credit or
    // mask the separate old destructor failure; it has its own named control.
    Verilated::threadContextp(&foreign);
  }
  require(failures>=8,std::string(name)+"_allocation_failure_coverage_missing");
}
}
int main(int argc,char**argv){try{
  std::string mode=argc==2?argv[1]:"";
  const std::vector<std::string>args={"owned-context-test","+tilelink_timeout=0"};
  if(mode!="--fased-constructor-only")run("serial",[&](){return std::make_unique<iris::serial_memory::Model>(31,args);},mode=="--serial-constructor-only");
  if(mode!="--serial-constructor-only")run("fased",[&](){return std::make_unique<iris::fased::Model>(iris::fased::Parameters{3,7,16,16},113,args);},mode=="--fased-constructor-only");
  std::cout<<"{\"status\":\"passed\",\"checks\":"<<checks<<",\"constructor_bad_alloc_injections\":"<<injections<<",\"successful_constructions\":"<<successful_constructions<<",\"target_RTL_edges\":0}\n";return 0;
}catch(const std::exception&e){allocation_failure::enabled=false;std::cerr<<e.what()<<'\n';return 1;}}
