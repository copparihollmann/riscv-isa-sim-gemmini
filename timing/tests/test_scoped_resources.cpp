#include "scoped_resources.hpp"
#include <cassert>
using namespace merlin_timing;
using spike_timing::ScopedResources;
int main(){
  Engine engine(8,{{0,2,4},{1,1,4}});ScopedResources scope({{0,2,4},{1,1,4}});scope.pair(0,1);
  engine.trace_sink([&](const Trace& t){scope.record(t);});
  Demand a{0,1,20};Event event{};event.latency=20;event.demands={&a,1};
  engine.submit_detached(event); // pre-window work crosses the opening boundary
  scope.begin(5);
  Demand b{0,1,10};event.earliest=5;event.demands={&b,1};event.latency=10;engine.submit_detached(event);
  Demand c{1,1,20};event.earliest=10;event.demands={&c,1};event.latency=20;engine.submit_detached(event);
  scope.end(15);
  assert(scope.complete());const auto& rows=scope.rows();
  assert(rows[0].busy==20&&rows[0].active==10&&rows[0].peak_units==2);
  assert(rows[1].busy==5&&rows[1].active==5);
  assert(scope.pairs()[0].active==5);
  Engine queued(4,{{0,1,4}});ScopedResources q({{0,1,4}});
  queued.trace_sink([&](const Trace& t){q.record(t);});q.begin(5);
  event.earliest=0;event.demands={&a,1};event.latency=20;queued.submit_detached(event);
  queued.submit_detached(event);q.end(15);
  assert(q.rows()[0].busy==10&&q.rows()[0].queued==10&&q.rows()[0].peak_queue==1);
  ScopedResources unknown({{0,1,0}});unknown.begin(0);Trace trace{};trace.action="submit";trace.frontier_before=0;
  trace.result.unknown=UnknownReason::missing_occupancy;unknown.record(trace);unknown.end(10);assert(!unknown.complete());
  ScopedResources bounded({{0,1,0}});bounded.begin(0);
  trace.result.unknown=UnknownReason::none;trace.result.issue=0;trace.result.start=10;
  trace.event.demands={&a,1};
  for(int i=0;i<40000;++i)bounded.record(trace);
  bounded.end(20);assert(!bounded.complete()); // endpoint budget fails closed
}
