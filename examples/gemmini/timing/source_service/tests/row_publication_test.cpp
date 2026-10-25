#include "staged.hpp"
#include <cassert>
#include <iostream>
using namespace gemmini_annotated_spike;
void check(unsigned columns,bool row_publication) {
 std::vector<merlin_timing::ResourceSpec> resources;for(unsigned i=0;i<17;++i)resources.push_back({i,1,128});
 Engine engine(18000,resources);StagedConfig c{};c.reservations={8,16,4};c.controller_entries={8,10,2};c.dma_commands={2,2};c.issue_resources={6,7,8};c.controller_resources={9,10,11};c.issue_latency=1;c.issue_occupancy=1;
 c.conservative_local_store_holds=true;c.scratchpad_bank_rows=4096;c.scratchpad_bank_resources={12,13,14,15};c.accumulator_storage_resource=16;c.scratchpad_load_stream=ScratchpadLoadConfig{16,3,2,4,true};c.scratchpad_packet_loads=true;c.source_identity_ingress=true;
 StagedObserver staged(engine,c,17412,{},0,16384,16,1024);TransferPhase phase{};phase.row_bytes=columns;phase.scratchpad_load=true;phase.individual_row_publication=row_publication;phase.reader_packets=reader_packets(0x10000,2,columns,columns+17,16,64,127);phase.row_memory=[](View<Transfer>){TransferEffects effects;effects.minimum_latency=2;return effects;};
 for(const auto &p:phase.reader_packets)phase.row_transfers.push_back({p.address,1,p.bytes,p.bytes,false});
 std::vector<ValueId> writes;for(unsigned b=0;b<(columns+15)/16;++b)for(unsigned r=0;r<2;++r)writes.push_back(8192+b*16+r);phase.reader_destinations=writes;
 Event load{0,{},{writes.data(),writes.size()},{},Cycle{2}};
 auto result=staged.submit("load",load,Cycle{1},1,0,(std::uint64_t(2)<<48)|(std::uint64_t(columns)<<32),phase);assert(result.ready&&engine.report().complete);
 auto first=engine.ready(writes.front()),last=engine.ready(writes.back());assert(first&&last);
 if(row_publication)assert(*first<*last&&*last<=*result.ready);else assert(first==last);
 const auto before=first;
 Event fence{*result.ready,{},{},{},Cycle{0}};auto done=staged.submit("fence",fence,Cycle{0},0,0,0);assert(done.ready);assert(engine.ready(writes.front())==before); // command completion/full fence must not overwrite per-row readiness
 std::uint64_t fragments=0;for(const auto&p:phase.reader_packets)fragments+=p.outputs.size();
 for(const auto&r:engine.report().resources)if(r.id==14)assert(r.busy_unit_cycles==fragments); // one actual bank write per fragment, not full DMA flight
}
int main(){check(16,false);for(auto width:{17u,32u,80u,127u})check(width,true);std::cout<<"width16 narrow compatibility;17/32/80/127 actual row-ready preserved through command+fence; exact bank-port writes PASS\n";}
