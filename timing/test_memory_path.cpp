#include "memory_path.hpp"
#include <iostream>
#include <stdexcept>

using namespace iris;
static void check(bool condition, const char* message) {
  if (!condition) throw std::runtime_error(message);
}
static MemoryStage link(const char* name, uint64_t bytes) {
  return {"transfer", name, 1, 1, bytes, 16, 2, "synthetic test fixture"};
}
int main() {
  // Three concurrent requests serialize on a shared link by transfer length.
  Machine machine(3, 100);
  MemoryPaths fabric(machine, {{"serial-response", 1, "synthetic test fixture"}});
  unsigned visible = 0;
  std::vector<MemoryTransfer> transfers;
  for (unsigned hart = 0; hart < 3; ++hart) {
    MemoryRequest request{hart, 0x80000000 + hart*64, 8, "dram-read", {link("serial-response", 64)}};
    request.on_complete = [&] { ++visible; };
    transfers.push_back(fabric.submit(std::move(request)));
  }
  machine.run_until(6); check(visible == 0, "memory visible before response completion");
  machine.run_until(7); check(visible == 1, "first response missing");
  machine.drain(); check(visible == 3, "not every hart completed");
  for (unsigned h=0; h<3; ++h) {
    const auto& node = machine.nodes().at(transfers[h].nodes.back());
    check(node.start == h*8 && node.end == h*8+7, "shared link lost serialization or contention");
    check(!machine.minstret(h), "memory stages must not retire guest instructions");
    const auto& receipt = transfers[h].parameters[0];
    check(receipt.derived_latency == 7 && receipt.derived_interval == 8 &&
          receipt.port_source == "synthetic test fixture" && receipt.parameters.source == receipt.port_source,
          "transfer parameters lost source association");
  }

  // Two explicitly independent banks overlap. No inferred bank hash is used.
  Machine banks(3, 100);
  MemoryPaths local(banks, {{"bank0", 1, "synthetic"}, {"bank1", 1, "synthetic"}});
  auto a = local.submit({0, 0x70000000, 8, "tcm0", {{"sram", "bank0", 3, 1, 0, 0, 0, "synthetic"}}});
  auto b = local.submit({2, 0x70020000, 8, "tcm1", {{"sram", "bank1", 5, 1, 0, 0, 0, "synthetic"}}});
  banks.drain();
  check(banks.nodes()[a.nodes[0]].start == 0 && banks.nodes()[a.nodes[0]].end == 3, "bank0 latency");
  check(banks.nodes()[b.nodes[0]].start == 0 && banks.nodes()[b.nodes[0]].end == 5, "bank1 overlap");

  Machine path(3, 100);
  MemoryPaths chain(path, {{"request",1,"synthetic"}, {"dram",1,"synthetic"}, {"response",1,"synthetic"}});
  auto transfer = chain.submit({1, 0x80000000, 8, "read-miss", {
      link("request", 8), {"access", "dram", 20, 4, 0, 0, 0, "synthetic"}, link("response", 64)}});
  path.drain();
  check(path.now() == 28, "request, memory and response latencies must compose");
  for (unsigned i=1; i<3; ++i) {
    const auto& prior = path.nodes()[transfer.nodes[i-1]], next = path.nodes()[transfer.nodes[i]];
    check(next.start >= prior.end && next.op.deps == std::vector<NodeId>{prior.id}, "path causality");
  }
  const auto size = path.nodes().size();
  bool refused = false;
  try { chain.submit({0, 1, 8, "bad", {link("request", 8), link("unknown", 8)}}); }
  catch (const std::invalid_argument&) { refused = true; }
  check(refused && path.nodes().size() == size, "unknown path partially mutated graph");
  refused = false;
  auto overflow = link("request", UINT64_MAX); overflow.beat_bytes=1;
  try { chain.submit({0, 1, 8, "overflow", {overflow}}); }
  catch (const std::overflow_error&) { refused = true; }
  check(refused && path.nodes().size() == size, "overflow was not refused atomically");

  // A bridge's output is aligned to the receiving domain, independent of the
  // issuing hart's period. Base ticks are common to both domains.
  Machine domains(1,100);
  domains.configure_resource("cpu",1);
  const auto source=domains.issue({0,"address","cpu",2,1});
  MemoryPaths crossing(domains,{{"receiver",1,"synthetic receiving domain"}});
  auto crossed=crossing.submit({0,0x80000000,8,"crossing",
      {{"receive","receiver",5,5,0,0,0,"synthetic",5}},{source},0,"",2,{}});
  domains.drain();
  const auto& received=domains.nodes()[crossed.nodes[0]];
  check(received.start==5 && received.end==10 && received.op.issue_period==5,
        "memory stage inherited hart clock instead of receiving clock");
  std::cout << "memory path checks passed (synthetic parameters; no Iris calibration)\n";
}
