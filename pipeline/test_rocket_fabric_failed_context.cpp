#include "rocket_fabric_peer.hpp"
#include "verilated.h"
#include <iostream>
#include <stdexcept>
int main(){try{
  VerilatedContext foreign;Verilated::threadContextp(&foreign);unsigned refusals=0;
  for(auto config:{std::pair<unsigned,unsigned>{0,16},{1,0},{1,1},{0x80000000U,16}}){
    try{iris::frontend::RocketFabricPeer peer(config.first,config.second);throw std::runtime_error("invalid source constructor accepted");}
    catch(const std::invalid_argument&){++refusals;}
    if(Verilated::threadContextp()!=&foreign)throw std::runtime_error("failed construction leaked source context");
  }
  for(unsigned seed:{1,7,31}){
    {iris::frontend::RocketFabricPeer peer(seed,16);if(Verilated::threadContextp()!=&foreign)throw std::runtime_error("successful constructor leaked context");}
    if(Verilated::threadContextp()!=&foreign)throw std::runtime_error("composite/context destructor leaked source context");
  }
  std::cout<<"{\"status\":\"passed_source_constructor_failure_and_destructor_context\",\"constructor_refusals\":"<<refusals<<",\"successful_peer_lifecycles\":3}\n";
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
