#include "posted_source_d.hpp"
#include <timing/write_transaction.hpp>
#include <cassert>
using namespace gemmini_annotated_spike;
int main(){
 using Q=merlin_timing::PostedTimeline;Q q({4096,4096,100000});PostedOneBeatSourceD d(q);
 auto ready=*q.token(),accepted=*q.token();std::optional<merlin_timing::Cycle>published;
 d.push(0x81000000,true,ready,accepted,[&](auto time,auto stored){published=time;q.complete(stored);},0);
 q.post(20,{},[accepted](auto&q,auto){q.complete(accepted);},Q::Kind::response_beat);
 while(q.step(true)){}assert(!q.progress().failed&&!d.busy());
 assert(q.completed(ready)==2&&published==21&&d.sram_reads()==1&&d.retained_bypass(0x81000000));
 // SRAM read2 overlaps S2/S3, rather than becoming an extra ACK fee.
 auto ready2=*q.token(),accepted2=*q.token();std::optional<merlin_timing::Cycle>second;
 d.push(0x81000000,true,ready2,accepted2,[&](auto t,auto stored){second=t;q.complete(stored);},30);
 q.post(30,{ready2},[accepted2](auto&q,auto){q.complete(accepted2);},Q::Kind::response_beat);
 while(q.step(true)){}assert(q.completed(ready2)==32&&second==33&&d.sram_reads()==1&&d.bypassed_reads()==1);
 spike_timing::WriteTransactionV1 packet;packet.address=0x81000000;packet.transaction_bytes=16;packet.beat_bytes=16;
 for(unsigned offset=0;offset<16;++offset){packet.mask=1u<<offset;auto useful=spike_timing::one_beat_write_useful(packet);assert(useful&&useful->address==packet.address+offset&&useful->bytes==1);}
 packet.mask=0xffff;assert(spike_timing::one_beat_write_useful(packet)->bytes==16);
 packet.mask=0;assert(!spike_timing::one_beat_write_useful(packet));packet.mask=5;assert(!spike_timing::one_beat_write_useful(packet));
 packet.mask=1u<<16;assert(!spike_timing::one_beat_write_useful(packet));packet.mask=1;packet.transaction_bytes=32;assert(!spike_timing::one_beat_write_useful(packet));
 // Actual S1 read backpressure delays S2 admission, not a fabricated extra
 // response latency. This also keeps the held input request in finite state.
 auto r3=*q.token(),a3=*q.token();std::optional<merlin_timing::Cycle>third;
 auto entered=d.push(0x81000100,true,r3,a3,[&](auto t,auto stored){third=t;q.complete(stored);},40,
   [&](auto t,auto accepted,auto data){q.post(t+1,{},[accepted](auto&q,auto){q.complete(accepted);},Q::Kind::operand_consume);q.post(t+3,{},[data](auto&q,auto){q.complete(data);},Q::Kind::response_beat);});
 q.post(40,{r3},[a3](auto&q,auto){q.complete(a3);},Q::Kind::response_beat);
 while(q.step(true)){}assert(q.completed(entered)==40&&q.completed(r3)==43&&third==44&&!d.busy());
}
