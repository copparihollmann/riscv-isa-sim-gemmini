#include <merlin_timing/arrival_ports.hpp>
#include <cassert>
#include <iostream>
using namespace merlin_timing;
static Cycle accepted(const ArrivalPortPlan &p, std::uint64_t id) {
  for (const auto &r : p.accepted) if (r.id == id) return r.accepted;
  assert(false); return 0;
}
int main() {
  // A future DMA response cannot reserve an earlier idle port interval.
  auto gap=plan_arrival_ports(1,{0,1},{{1,1,0,100,{}},{2,0,0,10,{}}});
  assert(gap.complete && accepted(gap,2)==10 && accepted(gap,1)==100);
  // Strict ready/valid priority; DMA head blocked by Execute, no FIFO bypass
  // to an otherwise free bank. Independent Execute bank sources can run together.
  auto blocked=plan_arrival_ports(2,{0,1,2},{{1,2,0,0,{}},{2,2,1,0,{}},
      {3,0,0,0,{}},{4,0,0,0,{}},{5,1,1,0,{}}});
  assert(blocked.complete && accepted(blocked,3)==0 && accepted(blocked,5)==0);
  assert(accepted(blocked,4)==1 && accepted(blocked,1)==2 && accepted(blocked,2)==3);
  // One FIFO may accept at most one item per cycle even on different ports.
  // Explicit WAW/WAR/RAW dependencies survive priority and future gap filling.
  auto hazard=plan_arrival_ports(1,{0,1},{{1,1,0,100,{}},{2,0,0,10,{1}}});
  assert(hazard.complete && accepted(hazard,2)==101);
  auto reads=plan_arrival_ports(1,{0,1},{{1,1,0,5,{}},{2,0,0,2,{}}},{{0,0,4},{0,8,12}});
  assert(reads.complete && accepted(reads,2)==4 && accepted(reads,1)==5);
  assert(!plan_arrival_ports(1,{0},{{1,0,0,std::nullopt,{}}}).complete);
  assert(!plan_arrival_ports(1,{0},{{1,0,0,0,{2}},{2,0,0,0,{1}}}).complete);
  assert(!plan_arrival_ports(1,{0,0},{{1,0,0,0,{}}}).complete);
  assert(!plan_arrival_ports(1,{0},{{1,0,0,~Cycle{0},{}}}).complete);
  std::cout << "arrival ports: gap, priority, FIFO, dependencies, busy intervals and refusals passed\n";
}
