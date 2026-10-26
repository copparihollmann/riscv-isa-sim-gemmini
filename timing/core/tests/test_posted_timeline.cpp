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
 PostedTimeline diagnostic32({2,33554432,16});assert(diagnostic32.token()->id==1);
 PostedTimeline diagnostic64({2,67108864,16});assert(diagnostic64.token()->id==1);
 bool oversized=false;try{PostedTimeline invalid({2,67108865,16});}catch(const std::invalid_argument&){oversized=true;}assert(oversized);
 // Completion storage follows actual live custody. A tiny software bound
 // admits a long regular stream without resetting token identities or time.
 PostedTimeline stream({8,8,1000000});std::optional<PostedTimeline::Token> held;
 std::uint64_t last_id=0;
 for(unsigned i=0;i<200000;++i){
   auto current=stream.token();assert(current&&current->id>last_id);last_id=current->id;
   if(i==0)held=current;
   assert(stream.post(i,{},[current](auto&q,auto){assert(q.complete(*current));}));
   assert(stream.advance(i+1,true));assert(stream.completed(*current)==i);
   assert(stream.completed(*held)==0);
 }
 assert(stream.progress().complete&&stream.summary().live_tokens==1&&stream.summary().peak_live_tokens<=3);
 held.reset();assert(stream.summary().live_tokens==0);
 // A lost producer is not silently made ready or garbage collected.
 PostedTimeline lost({8,8,100});
 for(unsigned i=0;i<8;++i)assert(lost.token());
 assert(lost.summary().unresolved_tokens==8&&!lost.progress().complete);
 assert(!lost.token()&&lost.reason()=="completion token capacity");
 // An externally retained completed record still consumes software custody.
 PostedTimeline retained({8,2,100});std::vector<PostedTimeline::Token> old;
 for(unsigned i=0;i<2;++i){auto token=retained.token();assert(token);old.push_back(*token);assert(retained.post(i,{},[token](auto&q,auto){assert(q.complete(*token));}));assert(retained.advance(i+1,true));}
 assert(retained.progress().complete&&!retained.token());
 // Tokens cannot be redirected to a different timeline or identity.
 PostedTimeline original({4,4,100}),other({4,4,100});auto owner=original.token();assert(owner);
 assert(!other.post(0,{*owner},[](auto&,auto){}));
 auto forged=*owner;++forged.id;assert(!original.post(0,{forged},[](auto&,auto){}));
 // Total useful work may exceed the dispatch guard, but only an actual
 // original source completion resets it; polling/partial events do not.
 PostedTimeline progressing({8,8,4});
 for(unsigned i=0;i<100;++i){auto done=progressing.token();assert(done&&progressing.track_source_completion(*done));assert(progressing.post(i,{},[done](auto&q,auto){assert(q.complete(*done));}));assert(progressing.advance(i+1,true));}
 assert(progressing.progress().dispatched==100&&progressing.peak_dispatches_without_source_completion()==1);
 PostedTimeline polling({8,8,4});auto unfinished=polling.token();assert(unfinished&&polling.track_source_completion(*unfinished));
 for(unsigned i=0;i<5;++i){assert(polling.post(i,{},[](auto&,auto){}));if(i<4)assert(polling.advance(i+1,true));else assert(!polling.advance(i+1,true));}
 assert(polling.reason()=="posted dispatch budget"&&polling.summary().unresolved_tokens==1);
 PostedTimeline repeated_progress({4,4,10});auto milestone=repeated_progress.token();assert(milestone&&repeated_progress.track_source_completion(*milestone));assert(!repeated_progress.track_source_completion(*milestone));
 PostedTimeline no_frontier({2,2,4});assert(!no_frontier.step(false));
}
