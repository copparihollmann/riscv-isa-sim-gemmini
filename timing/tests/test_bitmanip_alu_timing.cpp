#include "bitmanip_alu_timing.hpp"
#include <cassert>
#include <iostream>
using namespace spike_timing;
int main(int argc,char**argv){
 assert(argc==2);Model model(argv[1]);assert(!bitmanip_alu_service(model));
 for(auto&r:model.resources)r.queue_capacity=0; // synthetic fixture selects the reviewed unqueued ALU
 model.prices.erase("cpu.bitmanip.latency_cycles");model.prices.erase("cpu.bitmanip.occupancy_cycles");
 auto&cpu=model.document.get_child("cpu");cpu.put("isa","rv64imafdcb_zba_zbb_zbs");
 boost::property_tree::ptree law;
 law.put("schema","merlin.rocket_bitmanip_alu_service.v1");law.put("xlen",64);
 for(auto key:{"zba","zbb","zbs"})law.put(key,true);
 law.put("execute_to_memory_stages",1);law.put("initiation_interval",1);
 for(auto key:{"selected_isa_sha256","decode_source_sha256","alu_source_sha256","pipeline_source_sha256","rtl_sha256"})law.put(key,std::string(64,'0'));
 cpu.put_child("bitmanip_alu_service",law);
 auto service=bitmanip_alu_service(model);assert(service&&service->latency==1&&service->occupancy==1);
 auto refuses=[&]{try{(void)bitmanip_alu_service(model);return false;}catch(const std::invalid_argument&){return true;}};
 cpu.put("isa","rv64imafdc");assert(refuses());cpu.put("isa","rv64imafdcb_zba_zbb_zbs");
 cpu.get_child("bitmanip_alu_service").put("execute_to_memory_stages",2);assert(refuses());
 cpu.get_child("bitmanip_alu_service").put("execute_to_memory_stages",1);
 model.prices["cpu.bitmanip.latency_cycles"]=1;assert(refuses());model.prices.erase("cpu.bitmanip.latency_cycles");
 cpu.get_child("bitmanip_alu_service").put("decode_source_sha256","unbound");assert(refuses());
}
