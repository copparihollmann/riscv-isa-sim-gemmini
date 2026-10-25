#include <merlin_timing/posted_timeline.hpp>
#include <cassert>
#include <vector>
#include <stdexcept>
using namespace merlin_timing;
int main(){
 PostedTimeline timeline({16,16,64});auto row=timeline.token(),end=timeline.token();assert(row&&end);
 std::vector<unsigned>trace;bool cpu_update=false;
 // Posted LOAD owns a future continuation, not a future bank booking.
 assert(timeline.post(0,{},[&](auto&q,auto){trace.push_back(0);assert(q.post(20,{},[&](auto&q,auto at){assert(at==20&&cpu_update);trace.push_back(2);assert(q.complete(*row));assert(q.post(24,{},[&](auto&q,auto){trace.push_back(4);assert(q.complete(*end));}));}));}));
 assert(timeline.advance(4,true));assert((trace==std::vector<unsigned>{0}));assert(!timeline.completed(*row));
 // Actual CPU shared arrival precedes future DMA delivery; it is neither
 // retroactively inserted nor hidden by an eagerly booked LOAD result.
 assert(timeline.post(4,{},[&](auto&,auto at){assert(at==4);cpu_update=true;trace.push_back(1);}));
 assert(timeline.post(5,{*row},[&](auto&,auto at){assert(at==20);trace.push_back(3);}));
 assert(timeline.advance(21,true));assert((trace==std::vector<unsigned>{0,1,2,3}));assert(timeline.completed(*row)==20&&!timeline.completed(*end));
 assert(timeline.advance(25,true));assert(timeline.completed(*row)==20&&timeline.completed(*end)==24);assert(timeline.progress().complete);
 // Unproduced completion is blocked, not cycle zero or an invented fee.
 PostedTimeline blocked({2,2,4});auto absent=blocked.token();assert(absent);bool fired=false;assert(blocked.post(0,{*absent},[&](auto&,auto){fired=true;}));assert(blocked.advance(100,true));assert(!fired&&!blocked.progress().complete);
 PostedTimeline open({2,2,4});assert(!open.advance(10,false)&&open.progress().failed);
 PostedTimeline repeated({2,2,4});auto t=repeated.token();assert(t);assert(repeated.post(0,{},[&](auto&q,auto){assert(q.complete(*t));assert(!q.complete(*t));}));assert(!repeated.advance(1,true));assert(!repeated.completed(*t));
 PostedTimeline exception({2,2,4});assert(exception.post(0,{},[](auto&,auto){throw std::runtime_error("actor");}));try{exception.advance(1,true);assert(false);}catch(const std::runtime_error&){}assert(exception.progress().failed);
 PostedTimeline late({2,2,4});assert(late.advance(10,true));assert(!late.post(9,{},[](auto&,auto){}));
 // A blocked in-order source can dispatch one actual event and then
 // introduce its next instruction on the SAME edge without reopening time.
 PostedTimeline stepped({8,8,16});auto accepted=stepped.token();assert(accepted);
 assert(stepped.post(12,{},[&](auto&q,auto){assert(q.complete(*accepted));}));
 assert(stepped.step(true)&&stepped.completed(*accepted)==12&&stepped.now()==12);
 assert(stepped.post(12,{},[](auto&,auto){}));assert(stepped.step(true));
 assert(!stepped.post(11,{},[](auto&,auto){}));
 PostedTimeline no_frontier({2,2,4});assert(!no_frontier.step(false));
}
