#include "provider.hpp"
#include <cassert>
#include <iostream>
using namespace gemmini_annotated_spike;
Counters run(unsigned columns,bool wide,bool packet=true){
 std::vector<merlin_timing::ResourceSpec> resources;for(unsigned i=0;i<6;++i)resources.push_back({i,1,32});Engine e(18000,resources);
 HardwareConfig h{16,16384,1024,1,4,32,true,true,0};h.scratchpad_packet_loads=packet;h.source_identity_ingress=true;h.wide_scratchpad_row_publication=wide;h.selected_mvin_cols_bits=7;h.selected_mvin_rows_bits=5;
 Parameters prices;for(const auto*k:{"config","load"})for(const auto*f:{"latency_cycles","occupancy_cycles","latency_per_byte_cycles","occupancy_per_byte_cycles","latency_per_mac_cycles","occupancy_per_mac_cycles"})prices[std::string(k)+"."+f]=1;prices["dma.read_bytes_per_cycle"]=16;
 TargetObserver observer(e,h,prices,{0,1,2,3,4,5},0,[](auto){TransferEffects x;x.minimum_latency=0;return x;},[](const auto&,const auto&,auto,auto,auto,auto,const auto&){return Result{0,0,0,merlin_timing::UnknownReason::none};});
 observer.observe_command(0,0,1ull|(1ull<<8)|(16ull<<16)|(0x3f800000ull<<32),160);
 observer.observe_command(4,2,0x10000,(2ull<<48)|(std::uint64_t(columns)<<32));if(columns==128&&wide)assert(observer.unknown_timing().count("unsupported_pitched_load_packet_geometry"));return observer.counters();
}
int main(){
 const auto narrow=run(16,true);assert(narrow.load_packet_command_publication==1&&narrow.load_packet_per_row_publication==0);
 const auto wide=run(17,true);assert(wide.load_packet_per_row_publication==1&&wide.load_packet_command_publication==0);
 const auto old=run(17,false);assert(old.load_aggregate_publication==1&&old.load_packet_per_row_publication==0);
 const auto disabled=run(17,true,false);assert(disabled.load_aggregate_publication==1);
 const auto unsupported=run(128,true);assert(unsupported.load_unsupported_publication==1);
 std::cout<<"publication coverage distinguishes narrow command, wide per-row, aggregate fallback and unsupported geometry PASS\n";
}
