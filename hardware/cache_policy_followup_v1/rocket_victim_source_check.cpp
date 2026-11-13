#define main archived_transport_fixture_main
#include "../../timing/shuttle_memory_system_check.cpp"
#undef main
#include "../../timing/empirical_cache_v9.hpp"

int main() {
 try {
  for (unsigned seed : {1U,17U}) {
   Fixture t(seed);t.startup();
   iris::empirical::CacheHistoryV9 model(iris::empirical::iris_geometry_v9(),true,true);
   std::uint64_t id=0,model_tick=0;
   auto load=[&](std::uint64_t address,unsigned tag) {
    const auto before=t.rocket_responses, acquisitions=t.a;
    bool complete=false;
    for(unsigned attempt=0;attempt<8&&!complete;++attempt) {
     const auto nacks=t.rocket_nacks;t.issue(0,tag,address);
     for(unsigned i=0;i<5;++i)t.iris_step();
     if(t.rocket_responses!=before){complete=true;break;}
     if(t.rocket_nacks!=nacks) {
      unsigned wait=0;do{t.iris_step();need(++wait<12000,"Rocket replay did not become ordered");}
      while(!t.get("rocket_cache","io_cpu_ordered"));
      continue;
     }
     for(unsigned wait=0;wait<12000&&t.rocket_responses==before;++wait)t.iris_step();
     complete=t.rocket_responses!=before;
    }
    need(complete&&t.rocket_responses==before+1,"Exactly one real Rocket load response required");
    need(t.last_rocket_tag==tag&&t.last_rocket_value==pattern(address),"Real Rocket value/tag mismatch");
    auto d=model.begin_read({++id,2,address,8,false,++model_tick});
    model.complete(id,++model_tick);
    return std::pair{t.a-acquisitions,d};
   };
   constexpr std::uint64_t base=0x80030000ULL,stride=4096;
   for(unsigned i=0;i<4;++i) {
    auto [acquires,d]=load(base+i*stride,i+1);
    need(acquires==1&&d.l1_misses==1,"Four cold same-private-set loads required");
   }
   // Source S1 victims reset1 ->ways1,2,0,0, advanced by each finalcachedGrant.
   // Fourth fill evicts the third line while way3 is still invalid.
   auto [acquires,d]=load(base+2*stride,9);
   need(acquires==1,"Source Rocket did not re-acquire third line");
   need(d.l1_hits==1&&d.l1_misses==0,"V9 Rocket LRU did not retain all four cold lines");
   std::cout<<"{\"seed\":"<<seed<<",\"cold_fills\":4,\"third_line_source_reacquires\":"<<acquires
            <<",\"third_line_V9_LRU_hits\":"<<d.l1_hits<<",\"physical_A_requests\":"<<t.a
            <<",\"source_responses\":"<<t.rocket_responses<<",\"virtual_ticks\":"<<t.tick<<"}\n";
  }
  // A noncoherent Icache private hit survives a sharedL2 eviction in V9.
  // This is a public CacheHistory API control, not a wholeIcache RTL proof.
  iris::empirical::CacheHistoryV9 m(iris::empirical::iris_geometry_v9(),true,true);
  constexpr std::uint64_t base=0x90000000ULL,l2_alias=4*512*64;
  std::uint64_t id=1,tick=1;auto initial=m.begin_instruction({id,0,base,4,false,tick});m.complete(id,++tick);
  need(initial.l1_misses==1&&initial.l2_misses==1,"Initial instruction miss required");
  for(unsigned i=1;i<=4;++i){auto d=m.begin_vector({++id,2,base+i*l2_alias,8,false,++tick});m.complete(id,++tick);need(d.l2_misses==1,"SharedL2 set-fill control");}
  need(m.instruction_hit(0,base,4),"V9 incorrectly invalidated privateIcache onL2eviction");
  auto hit=m.touch_instruction(0,base,4,++tick);
  need(hit.l1_hits==1&&hit.l2_hits==0&&hit.l2_misses==0,"PrivateIcache hit touched sharedL2");
  // Independent directL2 observation proves the original line was evicted.
  auto absent=m.begin_vector({++id,2,base,8,false,++tick});m.complete(id,++tick);
  need(absent.l2_misses==1,"L2eviction precondition not witnessed");
  std::cout<<"{\"private_I_survives_verified_L2_eviction\":true,\"source_and_model_checks\":"<<checks<<",\"status\":\"passed\"}\n";
  return 0;
 } catch(const std::exception&e){std::cerr<<e.what()<<'\n';return 1;}
}
