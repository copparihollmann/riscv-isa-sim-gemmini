#include "staged.hpp"
#include <cassert>

using namespace merlin_timing;
using namespace gemmini_annotated_spike;

static StagedConfig config() {
  StagedConfig result;
  result.reservations={2,4,2}; result.controller_entries={2,2,2}; result.dma_commands={2,2};
  result.issue_resources={0,1,2}; result.controller_resources={3,4,5};
  result.issue_latency=1; result.issue_occupancy=1; return result;
}
static std::vector<ResourceSpec> resources() {
  return {{0, 1, 0}, {1, 1, 0}, {2, 1, 0}, {3, 1, 0}, {4, 1, 0}, {5, 1, 0}};
}

int main() {
  // Isolated PRELOAD survives a fence, then actually schedules with the next
  // execute command. The old descriptor is not dropped or declared retired.
  {
    Engine engine(8, resources()); StagedObserver scheduler(engine, config(), 4);
    const ValueId descriptor = 5;
    Event preload{2, {}, {&descriptor, 1}, {}, 7};
    assert(scheduler.submit("preload", preload, 3, 6, 0, 0).issue == 2);
    assert(scheduler.pending_preload() && engine.report().events == 0);
    Event fence{3, {}, {}, {}, 0};
    assert(scheduler.submit("fence", fence, 0, 127, 0, 0).ready == 3);
    assert(scheduler.pending_preload() && engine.ready(descriptor) == 0);
    Event compute{10, {&descriptor, 1}, {}, {}, 20};
    const auto executed = scheduler.submit("compute_ws", compute, 4, 4, 0, 0);
    assert(!scheduler.pending_preload() && engine.ready(descriptor) >= 18);
    assert(executed.ready && *executed.ready >= 39);
    assert(engine.issue_frontier() == 10); // effects do not stall CPU through completion
  }
  // The exception never skips prior unfinished DMA. A later config consumes in
  // controller FIFO service order but releases its RS entry at controller issue.
  {
    Engine engine(8, resources()); StagedObserver scheduler(engine, config(), 4);
    const ValueId local = 0, load_config = 1, descriptor = 5;
    Event load{0, {}, {&local, 1}, {}, 50};
    const auto dma = scheduler.submit("load", load, 10, 2, 0, 0);
    assert(dma.ready == 51);
    Event set_config{1, {}, {&load_config, 1}, {}, 1};
    const auto configured = scheduler.submit("config", set_config, 1, 0, 1, 0);
    assert(configured.start == 11 && configured.ready == 12);
    Event preload{2, {}, {&descriptor, 1}, {}, 2};
    scheduler.submit("preload", preload, 1, 6, 0, 0);
    Event fence{3, {}, {}, {}, 0};
    assert(scheduler.submit("fence", fence, 0, 127, 0, 0).ready == 51);
    assert(scheduler.pending_preload());
    Event stale{10, {&descriptor, 1}, {}, {}, 2};
    assert(scheduler.submit("compute_ws", stale, 1, 4, 0, 0).issue == 51);
  }
  // Ordinary entries remain owned until actual effects complete, not until
  // service starts or the controller queue dequeues.
  {
    auto selected = config(); selected.reservations[0] = 1;
    Engine engine(8, resources()); StagedObserver scheduler(engine, selected, 4);
    Event first{0, {}, {}, {}, 50}, second{1, {}, {}, {}, 2};
    assert(scheduler.submit("load", first, 1, 2, 0, 0).ready == 51);
    assert(scheduler.submit("load", second, 1, 2, 0, 0).issue == 51);
  }
  // A non-garbage PRELOAD's entry is not released at descriptor readiness.
  // With two EX slots, compute occupies the other slot; the next EX admission
  // must wait for actual output/tag completion.
  {
    auto selected = config(); selected.reservations[1] = 2;
    Engine engine(8, resources()); StagedObserver scheduler(engine, selected, 4);
    const ValueId descriptor = 5;
    Event preload{0, {}, {&descriptor, 1}, {}, 2};
    scheduler.submit("preload", preload, 1, 6, 0, 0x80000000u);
    Event compute{1, {&descriptor, 1}, {}, {}, 50};
    const auto result = scheduler.submit("compute_ws", compute, 1, 4, 0, 0);
    Event following{2, {}, {}, {}, 1};
    const auto next = scheduler.submit("config", following, 1, 0, 0, 0);
    assert(result.ready && next.issue == result.ready);
  }
  // EX config waits all prior execute completion. ST config uses ST's path.
  {
    Engine engine(8, resources()); StagedObserver scheduler(engine, config(), 4);
    Event compute{0, {}, {}, {}, 40}, set_config{1, {}, {}, {}, 1};
    assert(scheduler.submit("compute_ws", compute, 2, 4, 0, 0).ready == 41);
    assert(scheduler.submit("config", set_config, 1, 0, 0, 0).start == 42);
    const auto store = scheduler.submit("config", set_config, 1, 0, 2, 0);
    assert(store.start == 2); // independent controller can overlap
  }
  // Missing timing never turns into an implicit zero or a released reservation.
  {
    Engine engine(8, resources()); auto selected = config(); selected.issue_latency.reset();
    StagedObserver scheduler(engine, selected, 4);
    Event load{0, {}, {}, {}, 5};
    assert(!scheduler.submit("load", load, 1, 2, 0, 0).ready);
    assert(!engine.report().complete && !engine.barrier());
  }
  // Unknown prices do not erase observed ordering fences or hide a later
  // unsupported phase transition. These are semantic-domain refusals, not
  // prices to be fitted away.
  {
    auto selected = config(); selected.require_fenced_phases = true;
    selected.issue_latency.reset();
    std::vector<std::string> missing;
    Engine engine(8, resources());
    StagedObserver scheduler(engine, selected, 4, [&](const auto &s) { missing.push_back(s); });
    Event event{0, {}, {}, {}, 1};
    scheduler.submit("load", event, 1, 2, 0, 0);
    scheduler.submit("fence", event, 0, 127, 0, 0);
    scheduler.submit("preload", event, 1, 6, 0, 0);
    scheduler.submit("compute_ws", event, 1, 4, 0, 0);
    assert(missing.empty());
    scheduler.submit("preload", event, 1, 6, 0, 0);
    assert(missing.size() == 1);
    assert(missing[0] == "staged:compute_preload_overlap_without_completion_fence");
    scheduler.submit("store", event, 1, 3, 0, 0);
    assert(missing.back() == "staged:cross_controller_phase_without_completion_dependency");
  }
  // Cross-controller storage hazards prove full completion ancestry. An
  // unrelated earlier DMA cannot disappear merely because a later one is read.
  {
    DependencyPhases phases;
    assert(phases.observe(0, {}, {0}));
    assert(phases.observe(1, {0}, {1}));
    assert(phases.observe(2, {1}, {2}));
    assert(!phases.observe(0, {}, {3}));
    assert(!phases.observe(1, {0}, {1}));
    phases.fence(false);
    assert(phases.observe(1, {0}, {1}));
  }
  {
    DependencyPhases phases;
    phases.observe(0, {}, {0});
    phases.observe(0, {}, {1});
    assert(!phases.observe(1, {1}, {2}));
  }
  // PRELOAD feed and result/tag are separate graph edges. ST waits the
  // PRELOAD destination tag, which retires with its following compute output.
  {
    DependencyPhases phases;
    assert(phases.observe(0, {}, {0}));
    assert(phases.observe(1, {0}, {2}, true));
    phases.fence(true);
    assert(phases.observe(1, {1}, {}, false, true));
    assert(phases.observe(2, {2}, {}));
  }
  // LD/EX same-controller issue ordering never becomes completion ancestry.
  {
    DependencyPhases phases;
    phases.observe(0, {}, {0});
    phases.observe(0, {}, {1});
    phases.observe(1, {1}, {});
    assert(!phases.observe(2, {}, {}));
  }
  // The original owner supplies independently established physical resources;
  // arrival order or distinct row addresses alone never imply independence.
  {
    DependencyPhases phases([](auto group, const auto &rows, auto other, const auto &prior) {
      return (group == 1 || other == 1) && !rows.empty() && !prior.empty() && *rows.begin()/16 != *prior.begin()/16;
    });
    phases.observe(0, {}, {0});
    assert(phases.observe(1, {16}, {32}));
    assert(!phases.observe(2, {48}, {})); // DMA paths still shared
  }
  for (const auto rhs : {16u, 1u}) {
    auto selected=config(); selected.require_fenced_phases=true; selected.allow_dependency_ordered_phases=true;
    selected.allow_disjoint_scratchpad_banks=true; selected.scratchpad_bank_rows=16;
    selected.issue_latency.reset();
    std::vector<std::string> missing;
    Engine engine(128, resources());
    StagedObserver scheduler(engine, selected, 100, [&](const auto &reason) { missing.push_back(reason); },0,64,4,32);
    Event configured{0, {}, {}, {}, 1};
    scheduler.submit("config",configured,1,0,1ull<<16,1ull<<48);
    const ValueId a=0,descriptor=101;
    Event load{1, {}, {&a,1}, {}, 10};
    scheduler.submit("load",load,1,2,0,0);
    Event preload{2, {}, {&descriptor,1}, {}, 4};
    scheduler.submit("preload",preload,1,6,rhs | 1ull<<32 | 1ull<<48,0x80000000ull | 1ull<<32 | 1ull<<48);
    assert(missing.empty() == (rhs == 16)); // row-disjoint in one bank is insufficient
  }
  // The explicit conservative policy serializes independent rows sharing one
  // physical SP bank, while preserving overlap in a different physical bank.
  // Its full-latency holding interval is visible in resource accounting.
  for (const auto rhs : {16u, 1u}) {
    auto selected=config(); selected.require_fenced_phases=true; selected.allow_dependency_ordered_phases=true;
    selected.conservative_local_store_holds=true; selected.scratchpad_bank_rows=16;
    selected.scratchpad_bank_resources={6,7,8,9}; selected.accumulator_storage_resource=10;
    auto available=resources();
    for (unsigned id=6;id<=10;++id) available.push_back({id,1,0});
    Engine engine(128,available); std::vector<std::string> missing;
    StagedObserver scheduler(engine,selected,100,[&](const auto &s){missing.push_back(s);},0,64,4,32);
    const ValueId a=0,b=rhs;
    Event load{0,{}, {&a,1},{},50};
    assert(scheduler.submit("load",load,1,2,0,0).ready==51);
    Event compute{1,{&b,1},{},{},10};
    const auto result=scheduler.submit("compute_ws",compute,1,4,rhs | 1ull<<32 | 1ull<<48,0xffffffffu);
    assert(result.start==(rhs==16 ? 2 : 51));
    assert(missing.empty());
    const auto stats=engine.report();
    assert(stats.resources[6].busy_unit_cycles==(rhs==16 ? 50 : 60));
  }
}
