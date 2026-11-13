#include "empirical_cache_v6.hpp"
#include "empirical_cache_v7.hpp"
#include <iostream>
#include <stdexcept>
using namespace iris::empirical;
static void expect(bool x){if(!x)throw std::runtime_error("causal witness expectation");}
int main(){
 constexpr uint64_t address=0x80018100;CacheHistoryV6 old(iris_geometry_v6());CacheHistoryV7 fixed(iris_geometry_v7(),true);
 for(unsigned h=0;h<3;++h){Access x{h+1,h,address,8,false,2*h};old.begin(x);fixed.begin_read(x);old.complete(x.id,2*h+1);fixed.complete(x.id,2*h+1);}
 Access first{4,0,address+28,4,false,6};old.begin(first);fixed.begin_read(first);
 bool old_ready=old.data_hit(1,address+28,4),new_ready=fixed.data_hit(1,address+28,4);expect(!old_ready&&new_ready);
 Access second{5,1,address+28,4,false,7};auto before=old.begin(second),after=fixed.begin_read(second);expect(before.l1_hits==1&&after.l1_hits==1);expect(before.wait_for==std::vector<uint64_t>{4}&&after.wait_for.empty());
 Access write{6,2,address+28,4,true,8};auto ow=old.begin(write),nw=fixed.begin(write);expect(ow.wait_for==nw.wait_for&&nw.wait_for==std::vector<uint64_t>({4,5}));
 expect(!fixed.data_hit(0,address+28,4));Access read_after{7,0,address+28,4,false,9};auto ob=old.begin(read_after),nb=fixed.begin_read(read_after);expect(ob.wait_for==nb.wait_for&&nb.wait_for==std::vector<uint64_t>({4,5,6}));
 bool blocked=false;try{fixed.complete(6,10);}catch(const std::logic_error&){blocked=true;}expect(blocked);
 fixed.complete(5,10);fixed.complete(4,11);fixed.complete(6,12);fixed.complete(7,13);
 std::cout<<"{\"pass\":true,\"address\":"<<address+28<<",\"bytes\":4,\"hart0_pending_ordinary_read\":4,\"hart1_private_L1_ready_before\":"<<(old_ready?"true":"false")<<",\"hart1_private_L1_ready_after\":"<<(new_ready?"true":"false")<<",\"old_second_read_wait\":[4],\"new_second_read_wait\":[],\"both_second_read_L1hits\":1,\"old_writer_wait\":[4,5],\"new_writer_wait\":[4,5],\"both_later_read_wait\":[4,5,6],\"writer_premature_completion_refused\":true,\"read_completion_reorder_allowed\":true,\"values_or_knownness_modified_by_cache\":false,\"physical_RTL_permission_claim\":false}\n";
}
