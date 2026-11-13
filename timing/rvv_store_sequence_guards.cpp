#include "rvv_store_sequence.hpp"
#include <chrono>
#include <iostream>
#include <functional>
using namespace iris::rvv_store;
static void need(bool x){if(!x)throw std::runtime_error("Guard failed");}
int main(){try{
 unsigned geometry_checks=0;
 for(auto profile:{Profile::Compute128,Profile::Rocket256})for(unsigned bytes:{16u,32u,64u,128u,256u}){auto g=aligned_geometry(profile,bytes,0x80000000ULL);const unsigned internal=profile==Profile::Compute128?16:32,outer=profile==Profile::Compute128?32:8;need(g.payload_bytes==bytes&&g.VRF_groups==(bytes+internal-1)/internal&&g.TL_requests==g.VRF_groups&&g.A_beats==g.TL_requests*((internal+outer-1)/outer)&&g.wire_data_slot_bytes==g.A_beats*outer);++geometry_checks;}
 unsigned guards=0;auto reject=[&](const std::function<void()>&f){try{f();}catch(const std::exception&){++guards;return;}throw std::runtime_error("Unexpected guard acceptance");};
 reject([&]{Sequencer invalid(static_cast<Profile>(9));});reject([&]{aligned_geometry(Profile::Compute128,0,0x80000000);});reject([&]{aligned_geometry(Profile::Rocket256,257,0x80000000);});reject([&]{aligned_geometry(Profile::Rocket256,32,0x80000008);});
 Sequencer q(Profile::Compute128);Inputs reset{true,false,{},true,true,0,0,true};reject([&]{q.sample();});reject([&]{q.commit();});auto no=reset;no.reset=false;reject([&]{q.evaluate(no);});q.evaluate(reset);need(!q.sample().control_defined);q.commit();q.evaluate(no);need(q.sample().control_defined&&!q.sample().payload);q.commit();
 Command c{0x02056c27,32,0,2,0,0,2,0,1};Inputs i{false,true,c,true,true,0,0,true};
 for(unsigned which=0;which<6;++which){auto bad=i;if(which==0)bad.dispatch->raw&=~(1u<<25);if(which==1)bad.dispatch->raw|=1u<<29;if(which==2)bad.dispatch->vl=0;if(which==3)bad.dispatch->vstart=32;if(which==4)bad.environment_defined=false;if(which==5)bad.dispatch->raw|=1u<<28;reject([&]{q.evaluate(bad);});}
 q.evaluate(i);auto a=q.sample();q.evaluate(i);need(a.dispatch_fire==q.sample().dispatch_fire);q.commit();need(q.edges()==3);reject([&]{q.commit();});
 auto start=std::chrono::steady_clock::now();uint64_t checksum=0,dispatches=0,micro=0;constexpr unsigned edges=2000000;
 for(unsigned e=0;e<edges;++e){i.dispatch->token=e;i.dispatch->debug_id=e&65535;q.evaluate(i);auto o=q.sample();dispatches+=o.dispatch_fire;micro+=o.data_fire;checksum=checksum*1099511628211ULL+(o.payload?o.payload->read_intent:0)+o.dispatch_fire;q.commit();}
 double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();need(micro>edges*.9&&dispatches>1000);std::cout<<"{\"pass\":true,\"geometry_checks\":"<<geometry_checks<<",\"guard_refusals\":"<<guards<<",\"active_edges\":"<<edges<<",\"data_microissues\":"<<micro<<",\"tail_replacement_dispatches\":"<<dispatches<<",\"host_seconds\":"<<seconds<<",\"native_active_edges_per_second\":"<<edges/seconds<<",\"checksum\":"<<checksum<<",\"SoC_MIPS_claimed\":false}\n";return 0;}catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 2;}}
