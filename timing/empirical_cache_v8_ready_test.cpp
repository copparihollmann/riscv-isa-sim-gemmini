#include "empirical_cache_v8.hpp"
#include <deque>
#include <iostream>
#include <stdexcept>
using namespace iris::empirical;
static unsigned checks=0;void check(bool b){++checks;if(!b)throw std::runtime_error("response readiness guard");}
int main(){
 constexpr uint64_t address=0x84000000;CacheHistoryV8 c(iris_geometry_v8(),true);uint64_t id=0,t=0;
 for(unsigned h=1;h<3;++h){c.begin_read({++id,h,address,8,false,t});check(!c.data_hit(h,address,8));c.complete(id,++t);check(c.data_hit(h,address,8));}
 c.begin_read({++id,0,address,8,false,t});check(!c.data_hit(0,address,8));std::deque<uint64_t> p{id};
 for(unsigned h=1;h<3;++h){auto d=c.begin_read({++id,h,address,8,false,t});check(d.wait_for.empty()&&d.l1_hits==1);p.push_back(id);}
 for(unsigned i=0;i<1000;++i){c.complete(p.front(),++t);p.pop_front();const auto h=i%3;check(c.data_hit(h,address,8));auto d=c.begin_read({++id,h,address,8,false,t});check(d.l1_hits==1&&d.wait_for.empty());p.push_back(id);}
 check(c.warm_read_accepts()>=1002&&c.compatible_read_dependencies_omitted()>=2000);
 auto writer=++id;auto w=c.begin({writer,2,address,8,true,++t});check(w.wait_for.size()==3);check(!c.data_hit(0,address,8));
 auto reader=++id;auto r=c.begin_read({reader,0,address,8,false,++t});check(r.wait_for.size()==4);bool refused=false;try{c.complete(writer,t);}catch(const std::logic_error&){refused=true;}check(refused);
 while(!p.empty()){c.complete(p.back(),++t);p.pop_back();}c.complete(writer,++t);check(!c.data_hit(0,address,8));c.complete(reader,++t);check(c.data_hit(0,address,8));
 // A real eviction revokes readiness. An old accepted response does not
 // recreate an invalid tag; a new fill requires its own matching response.
 auto cfg=iris_geometry_v8();cfg.l2={1,1,1,64};for(auto&g:cfg.l1d)g={1,1,1,64};CacheHistoryV8 e(cfg,true);
 e.begin_read({1,0,address,8,false,0});e.complete(1,1);check(e.data_hit(0,address,8));e.begin_read({2,0,address,8,false,2});
 e.begin_read({3,1,address+64,8,false,3});check(!e.data_hit(0,address,8));e.complete(2,4);check(!e.data_hit(0,address,8));e.complete(3,5);
 e.begin_read({4,0,address,8,false,6});check(!e.data_hit(0,address,8));e.complete(4,7);check(e.data_hit(0,address,8));
 // Failed responses cannot publish a response-ready private copy.
 e.begin({5,0,address+64,8,true,8});e.complete(5,9,false);check(!e.data_hit(0,address+64,8));
 std::cout<<"{\"pass\":true,\"checks\":"<<checks<<",\"continuous_hit_readers\":1000,\"same_line_write_after_readers_preserved\":true,\"read_after_writer_waits_matching_fill\":true,\"eviction_does_not_resurrect_old_response\":true,\"failed_response_does_not_publish_ready\":true,\"physical_coherence_certified\":false}\n";
}
