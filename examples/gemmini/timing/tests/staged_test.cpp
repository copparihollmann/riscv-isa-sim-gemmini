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
static StagedConfig epoch_config() {
  auto result = config();
  result.require_fenced_phases = true;
  result.allow_dependency_ordered_phases = true;
  result.conservative_local_store_holds = true;
  result.serialized_execute_epochs = true;
  result.scratchpad_bank_rows = 16;
  result.scratchpad_bank_resources = {6,7,8,9};
  result.accumulator_storage_resource = 10;
  return result;
}
static std::vector<ResourceSpec> epoch_resources() {
  auto result = resources();
  for (unsigned id=6; id<=10; ++id) result.push_back({id,1,0});
  return result;
}

int main() {
  // Accumulating WS only releases SP operands early. ACC RMW, configuration,
  // PE state, result publication and following PRELOAD retain old lifetimes.
  // Ineligible tails, transpose, strides, foreign ACC reads, and explicit
  // retained SP readers keep the original conservative behavior.
  for (unsigned variant=0;variant<8;++variant) for (bool enabled:{false,true}) {
    auto selected=epoch_config(); selected.serialized_output_stationary_epochs=true;
    selected.split_ws_feed_lifetimes=true; selected.split_ws_accumulate_operands=enabled;
    selected.ws_feed_queue_release=true; selected.ws_resident_mul_pre_pairing=true;
    Engine e(128,epoch_resources()); StagedObserver p(e,selected,100,{},0,64,4,32);
    Event cfg{0,{},{},{},1};
    p.submit("config",cfg,1,0,4|(1ull<<16)|(variant==2?1ull<<8:0),
        (variant==3?2ull:1ull)<<48);
    const auto packet=[](std::uint32_t a,unsigned rows=4) {
      return std::uint64_t(a)|(4ull<<32)|(std::uint64_t(rows)<<48);
    };
    const ValueId desc=101,outputs[]={64,65,66,67,102};
    std::vector<ValueId> reads={desc,0,16,64,65,66,67};
    if(variant==4) reads.push_back(68);
    const ValueId retained=0;
    Event pre{2,{},{&desc,1},{},4};
    Event mul{3,{reads.data(),reads.size()},{outputs,5},{},30};
    if(variant==5)mul.retained_reads={&retained,1};
    if(variant==7)mul.latency.reset();
    p.submit("preload",pre,4,6,packet(16,variant==1?2:4),packet(0xc0000000));
    const auto done=p.submit("compute_ws",mul,4,4,
        packet(variant==6?0x80000000:0),packet(0xffffffff));
    if(variant==7) { assert(!done.ready && !e.report().complete); continue; }
    assert(done.start && done.ready && *done.ready==*done.start+30);
    const bool split=enabled && variant==0;
    const Cycle consumed=split?*done.start+4:*done.ready;
    assert(e.last_use(0)==consumed && e.last_use(16)==consumed);
    assert(e.ready(64)==done.ready && e.last_use(64)==done.ready);
    assert(e.ready(102)==done.ready && e.last_use(desc)==done.ready);
    const ValueId input=0; const Demand sp{6,1,1};
    Event overwrite{0,{},{&input,1},{&sp,1},1};
    assert(e.submit_detached(overwrite).start==consumed);
    // An unrelated ACC row still shares the retained conservative ACC port.
    const ValueId acc=68; const Demand acc_port{10,1,1};
    Event acc_access{0,{&acc,1},{},{&acc_port,1},1};
    assert(e.submit_detached(acc_access).start==done.ready);
    if(variant==0) {
      const auto next=p.submit("preload",pre,4,6,packet(16),packet(0xc0000000));
      assert(next.issue); // Operand feed waits for the next lookahead command.
      const auto second=p.submit("compute_ws",mul,4,4,packet(0),packet(0xffffffff));
      assert(second.start>=done.ready && e.report().complete);
    }
  }
  {
    auto bad=epoch_config();bad.split_ws_accumulate_operands=true;
    Engine e(128,epoch_resources());bool rejected=false;
    try {StagedObserver p(e,bad,100,{},0,64,4,32);} catch(const std::invalid_argument &) {rejected=true;}
    assert(rejected);
  }
  // Row loads reserve SRAM only when data arrives; actual destination and
  // resource hazards still hold; a prior bank reservation delays acceptance.
  for(const Cycle blocked:{0u,100u}) for(bool partial:{false,true}) for(bool frontend:{false,true}) {
    auto selected=epoch_config();selected.scratchpad_load_stream=
        partial?ScratchpadLoadConfig{16,3,2,3,true,true,1}:ScratchpadLoadConfig{};
    selected.load_frontend_registered_cycles=frontend?6:0;
    auto specs=epoch_resources();specs.push_back({11,1,0});
    Engine e(128,specs);StagedObserver p(e,selected,100,{},0,64,16,32);
    if(blocked) {const Demand hold{6,1,blocked};Event prior{0,{},{},{&hold,1},blocked};e.submit_detached(prior);}
    const ValueId destination=0;
    Event load{0,{},{&destination,1},{},Cycle{11}};
    TransferPhase phase{0,{}};phase.row_bytes=partial?4:16;phase.scratchpad_load=true;
    phase.row_transfers.push_back({4096,1,16,16,false});
    phase.row_memory=[](View<Transfer> rows) {
      assert(rows.size==1 && !rows.data[0].write && rows.data[0].row_bytes==16);
      return TransferEffects{{},{},{{11,1,Cycle{1}}},Cycle{20}};
    };
    const auto loaded=p.submit("load",load,2,2,4096,0,phase);
    assert(loaded.start==1+6*frontend && loaded.ready==std::max(Cycle{27}+partial+6*frontend,blocked+1));
    assert(e.ready(destination)==loaded.ready);
    const ValueId read=destination;Event consumer{0,{&read,1},{},{},Cycle{1}};
    const auto used=e.submit_detached(consumer);assert(used.start==loaded.ready);
    const auto report=e.report();assert(report.complete);
    assert(report.resources[0].busy_unit_cycles==1);
    assert(report.resources[11].busy_unit_cycles==1);
  }
  // A long source dependency absorbs the arrival pipeline; adding the delay
  // after dependency resolution would incorrectly extend this result.
  for(bool frontend:{false,true}) {
    auto selected=epoch_config();selected.scratchpad_load_stream=ScratchpadLoadConfig{};
    selected.load_frontend_registered_cycles=frontend?6:0;
    Engine e(128,epoch_resources());StagedObserver p(e,selected,100,{},0,64,16,32);
    const ValueId dependency=90,destination=0;
    Event prior{0,{},{&dependency,1},{},Cycle{100}};e.submit_detached(prior);
    Event load{0,{&dependency,1},{&destination,1},{},Cycle{11}};
    TransferPhase phase{0,{}};phase.row_bytes=16;phase.scratchpad_load=true;
    phase.row_transfers.push_back({4096,1,16,16,false});
    phase.row_memory=[](View<Transfer>){return TransferEffects{{},{},{},Cycle{20}};};
    const auto done=p.submit("load",load,1,2,4096,0,phase);
    assert(done.start==101 && done.ready==127);
  }
  // Streamed row services retain their exact memory dependencies and final
  // local read hazard; shared memory congestion backpressures finite queues.
  for(const Cycle blocked:{0u,100u}) {
    auto selected=epoch_config();selected.readout_stream=ReadoutStreamConfig{2,6,2,6,5,8,16,16};
    auto specs=epoch_resources();specs.push_back({11,1,0});
    Engine e(128,specs);StagedObserver p(e,selected,100,{},0,64,16,32);
    const Demand busy{11,1,blocked};Event prior{0,{},{},{&busy,1},blocked};e.submit_detached(prior);
    const ValueId source=64;
    std::vector<ValueId> outputs;for(unsigned row=0;row<16;++row)outputs.push_back(110+row);
    Event store{0,{&source,1},{outputs.data(),outputs.size()},{},84};
    TransferPhase phase{8,{}};phase.row_bytes=64;
    for(unsigned row=0;row<16;++row)
      phase.rows.push_back(TransferEffects{{},{ValueId(110+row)},{{11,1,4}},4});
    const auto result=p.submit("store",store,84,3,0,0,phase);
    assert(result.ready && *result.ready>=84 && e.ready(125)==result.ready);
    const ValueId output=source;Event overwrite{0,{},{&output,1},{},1};
    const auto after=e.submit_detached(overwrite);
    assert(after.start>=result.ready && e.report().complete);
  }
  // Credit paired feeds only with actual PRELOAD + third-COMPUTE residency.
  // Narrow FIFO capacity, late third arrival, or a different weight tile must
  // preserve the separately scheduled fallback; no descriptor/result shortcut.
  for (const unsigned fifo : {2u,8u}) for (const bool late : {false,true})
      for (const bool same_weights : {false,true}) for (unsigned hazard=0;hazard<3;++hazard) {
    std::array<Cycle,2> starts{};
    for (unsigned enabled=0;enabled<2;++enabled) {
      auto selected=epoch_config(); selected.serialized_output_stationary_epochs=true;
      selected.split_ws_feed_lifetimes=true; selected.ws_feed_queue_release=true;
      selected.ws_resident_mul_pre_pairing=enabled; selected.reservations[1]=8;
      selected.controller_entries[1]=fifo;
      Engine e(128,epoch_resources()); StagedObserver p(e,selected,100,{},0,64,4,32);
      Event cfg{0,{},{},{},1};p.submit("config",cfg,1,0,4|(1ull<<16),1ull<<48);
      const auto packet=[](std::uint32_t x){return std::uint64_t(x)|(4ull<<32)|(4ull<<48);};
      const ValueId weights=hazard==1?4:16,destination=hazard==2?64:68;
      const ValueId desc=101,reads1[]={desc,0,weights},reads2[]={desc,0,same_weights?weights:32u};
      const ValueId out1[]={64,65,66,67,102},out2[]={destination,destination+1,destination+2,destination+3,102};
      Event pre{2,{}, {&desc,1},{},2},one{3,{reads1,3},{out1,5},{},30};
      p.submit("preload",pre,8,6,packet(weights),packet(0x80000000));
      const auto first=p.submit("compute_ws",one,8,4,packet(0),packet(0xffffffff));
      p.submit("preload",pre,8,6,packet(same_weights?weights:32),packet(0x80000000+destination-64));
      Event two{late?100u:3u,{reads2,3},{out2,5},{},30};
      const auto second=p.submit("compute_ws",two,8,4,packet(0),packet(0xffffffff));
      assert(second.start && second.ready && e.ready(destination)==second.ready);
      assert(first.ready && *second.start>=*first.start+8);
      starts[enabled]=*second.start;
      const ValueId out=destination; Event read{0,{&out,1},{},{},1};
      const auto stored=p.submit("store",read,1,3,0,0);
      assert(stored.start>=second.ready && e.report().complete);
    }
    if(fifo==8 && !late && same_weights && !hazard) assert(starts[1]<starts[0]);
    else assert(starts[1]==starts[0]);
  }
  // FIFO slots that become free before the already scheduled feed starts
  // must allow the same resident pairing as a wider FIFO. This stream fills
  // ten entries before the seventh PRELOAD, but does not need to move any
  // previously reserved feed. Late residency still falls back above.
  std::array<std::array<Cycle,8>,2> queued_starts{};
  for (unsigned wide=0;wide<2;++wide) {
    auto selected=epoch_config(); selected.serialized_output_stationary_epochs=true;
    selected.split_ws_feed_lifetimes=true; selected.ws_feed_queue_release=true;
    selected.ws_resident_mul_pre_pairing=true; selected.reservations[1]=32;
    selected.controller_entries[1]=wide?32:10; selected.scratchpad_bank_rows=32;
    Engine e(512,epoch_resources()); StagedObserver p(e,selected,400,{},0,128,16,256);
    Event cfg{0,{},{},{},1};p.submit("config",cfg,1,0,4|(1ull<<16),1ull<<48);
    const auto packet=[](std::uint32_t x){return std::uint64_t(x)|(16ull<<32)|(16ull<<48);};
    const ValueId desc=401,reads[]={desc,0,64};
    for(unsigned tile=0;tile<8;++tile) {
      std::array<ValueId,17> output{};
      for(unsigned row=0;row<16;++row)output[row]=128+tile*16+row;
      output[16]=402;
      Event pre{2+8*tile,{},{&desc,1},{},12};
      Event mul{3+8*tile,{reads,3},{output.data(),output.size()},{},56};
      p.submit("preload",pre,16,6,packet(64),packet(0x80000000+tile*16));
      const auto done=p.submit("compute_ws",mul,17,4,packet(0),packet(0xffffffff));
      assert(done.start && done.ready && e.ready(128+tile*16)==done.ready);
      queued_starts[wide][tile]=*done.start;
    }
    assert(e.report().complete);
  }
  assert(queued_starts[0]==queued_starts[1]);
  // ACC first-data arrival precedes coherent memory service, while the
  // remaining producer stream overlaps it. Scalar local service is a floor,
  // not a duration added wholesale to memory. Output hazards publish last.
  for (const Cycle memory_cycles : {64u,160u}) for (const Cycle blocked_until : {0u,50u}) {
    auto rs=resources(); rs.push_back({6,1,0}); Engine e(128,rs);
    if (blocked_until) { const Demand busy{6,1,blocked_until}; Event occupy{0,{},{},{&busy,1},blocked_until}; e.submit_detached(occupy); }
    StagedObserver p(e,config(),100,{},0,64,4,32);
    const ValueId acc=64,output=110;
    Event source{0,{&acc,1},{&output,1},{},std::max(Cycle{84},Cycle{8}+memory_cycles)};
    TransferPhase phase{8,{{6,1,memory_cycles}}};
    const auto stored=p.submit("store",source,65,3,0,0,phase);
    assert(stored.start && stored.ready);
    const Cycle memory_start=std::max(*stored.start+8,blocked_until);
    assert(stored.ready==memory_start+std::max(Cycle{76},memory_cycles));
    assert(e.ready(output)==stored.ready && e.last_use(acc)==stored.ready);
    const Demand after{6,1,1}; Event subsequent{0,{},{},{&after,1},1};
    const auto used=e.submit_detached(subsequent);
    assert(used.start==memory_start+memory_cycles && e.report().complete);
  }
  // The full-WS COMPUTE entry is distinct from its PRELOAD result tag. With
  // two RS slots, early COMPUTE retirement admits the next PRELOAD, but the
  // next COMPUTE still waits for the previous result-tag slot. Output readers
  // and an overlapping input DMA continue to wait for their real lifetimes.
  for (const bool release : {false,true}) {
    auto selected=epoch_config(); selected.serialized_output_stationary_epochs=true;
    selected.split_ws_feed_lifetimes=true; selected.ws_feed_queue_release=release;
    selected.reservations[1]=2; selected.controller_entries[1]=1;
    Engine e(128,epoch_resources()); StagedObserver p(e,selected,100,{},0,64,4,32);
    Event cfg{0,{},{},{},1}; p.submit("config",cfg,1,0,4|(1ull<<16),1ull<<48);
    const auto packet=[](std::uint32_t a){return std::uint64_t(a)|(4ull<<32)|(4ull<<48);};
    const ValueId desc=101,reads[]={desc,0,16},outputs[]={64,65,66,67,102};
    Event pre{2,{}, {&desc,1},{},4},mul{3,{reads,3},{outputs,5},{},30};
    p.submit("preload",pre,4,6,packet(16),packet(0x80000000));
    const auto first=p.submit("compute_ws",mul,4,4,packet(0),packet(0xffffffff));
    const auto next=p.submit("preload",pre,4,6,packet(16),packet(0x80000000));
    assert(first.ready && next.issue && e.ready(64)==first.ready);
    assert(release ? *next.issue==*first.start+5 : next.issue==first.ready);
    const auto second=p.submit("compute_ws",mul,4,4,packet(0),packet(0xffffffff));
    assert(second.start>=first.ready && e.ready(64)==second.ready);
    const ValueId input=0; Event dma{0,{}, {&input,1},{},1};
    const auto moved=p.submit("load",dma,1,2,0,0);
    assert(moved.start>=*second.start+4);
    const ValueId output=64; Event store{0,{&output,1},{},{},1};
    const auto stored=p.submit("store",store,1,3,0,0);
    assert(stored.start>=second.ready && e.report().complete);
  }
  // A previous mesh output still in flight makes completion arbitration
  // uncertain. Keep the second COMPUTE's conservative RS release rather than
  // assuming that its registered completion wins over that output tag.
  {
    auto selected=epoch_config(); selected.serialized_output_stationary_epochs=true;
    selected.split_ws_feed_lifetimes=true; selected.ws_feed_queue_release=true;
    selected.reservations[1]=3;
    Engine e(128,epoch_resources()); StagedObserver p(e,selected,100,{},0,64,4,32);
    Event cfg{0,{},{},{},1}; p.submit("config",cfg,1,0,4|(1ull<<16),1ull<<48);
    const auto packet=[](std::uint32_t a){return std::uint64_t(a)|(4ull<<32)|(4ull<<48);};
    const ValueId desc=101,reads[]={desc,0,16},out1[]={64,65,66,67,102},out2[]={68,69,70,71,102};
    Event pre{2,{}, {&desc,1},{},4},mul1{3,{reads,3},{out1,5},{},30},mul2{3,{reads,3},{out2,5},{},30};
    p.submit("preload",pre,4,6,packet(16),packet(0x80000000));
    const auto first=p.submit("compute_ws",mul1,4,4,packet(0),packet(0xffffffff));
    p.submit("preload",pre,4,6,packet(16),packet(0x80000004));
    const auto second=p.submit("compute_ws",mul2,4,4,packet(0),packet(0xffffffff));
    assert(*second.start+5<*first.ready);
    const auto third=p.submit("preload",pre,4,6,packet(16),packet(0x80000008));
    assert(third.issue==first.ready && e.report().complete);
  }
  // v5 narrows operand lifetime without early result publication or early RS
  // reuse. Full WS feeds remain separate; tails retain the old conservative rule.
  for (const auto slots : {2u, 8u}) for (const bool full : {false, true}) {
    auto selected = epoch_config();
    selected.serialized_output_stationary_epochs = true;
    selected.split_ws_feed_lifetimes = true;
    selected.reservations[1] = slots;
    Engine engine(128, epoch_resources()); std::vector<std::string> missing;
    StagedObserver scheduler(engine,selected,100,[&](const auto &x){missing.push_back(x);},0,64,4,32);
    Event cfg{0,{},{},{},1};
    scheduler.submit("config",cfg,1,0,4 | (1ull<<16),1ull<<48);
    const auto packet=[](std::uint32_t addr,unsigned rows=4) {
      return std::uint64_t(addr) | (4ull<<32) | (std::uint64_t(rows)<<48);
    };
    const ValueId descriptor=101, reads[]={descriptor,0,16};
    const ValueId writes1[]={64,65,66,67,102}, writes2[]={68,69,70,71,102};
    Event preload{2,{}, {&descriptor,1},{},4};
    Event compute1{3,{reads,3},{writes1,5},{},30};
    Event compute2{3,{reads,3},{writes2,5},{},30};
    scheduler.submit("preload",preload,4,6,packet(16,full?4:2),packet(0x80000000));
    const auto first=scheduler.submit("compute_ws",compute1,4,4,packet(0),packet(0xffffffff));
    const auto admitted=scheduler.submit("preload",preload,4,6,packet(16),packet(0x80000004));
    const auto second=scheduler.submit("compute_ws",compute2,4,4,packet(0),packet(0xffffffff));
    assert(first.ready && second.ready && missing.empty());
    assert(engine.ready(64)==first.ready && engine.ready(68)==second.ready);
    if (full) assert(engine.last_use(0) == *second.start + 4);
    else assert(engine.last_use(0) >= second.start);
    if (full && slots==8) assert(second.start < first.ready);
    else assert(second.start >= first.ready);
    if (slots==2) assert(admitted.issue >= first.ready);
    const ValueId output=68;
    Event store{4,{&output,1},{},{},2};
    const auto stored=scheduler.submit("store",store,1,3,0,0);
    assert(stored.start>=second.ready);
    Event fence{4,{},{},{},1};
    const auto drained=scheduler.submit("fence",fence,1,127,0,0);
    assert(drained.start>=stored.ready && engine.report().complete);
  }
  // Explicit v3: CPU can enqueue the next WS epoch without a fence. Its
  // descriptor consumption waits prior output completion; RS ownership is
  // retained. This does NOT assert mesh-stage pipelining.
  for (const auto slots : {2u,4u}) {
    auto selected = epoch_config(); selected.reservations[1] = slots;
    Engine engine(128,epoch_resources()); std::vector<std::string> missing;
    StagedObserver scheduler(engine,selected,100,[&](const auto &s){missing.push_back(s);},0,64,4,32);
    Event configured{0,{},{},{},1};
    scheduler.submit("config",configured,1,0,4 | (1ull<<16),1ull<<48);
    const ValueId descriptor=101;
    Event preload{2,{}, {&descriptor,1},{},3};
    scheduler.submit("preload",preload,1,6,0xffffffffu,0x80000000u);
    Event compute{3,{&descriptor,1},{},{},50};
    const auto first=scheduler.submit("compute_ws",compute,1,4,0xffffffffu,0xffffffffu);
    const auto second_preload=scheduler.submit("preload",preload,1,6,0xffffffffu,0x80000000u);
    const auto second=scheduler.submit("compute_ws",compute,1,4,0xffffffffu,0xffffffffu);
    assert(first.ready && second.ready && second.start >= *first.ready);
    assert(slots==2 ? second_preload.issue==first.ready : second_preload.issue<first.ready);
    assert(missing.empty() && engine.report().complete);
  }
  // Explicit v4 OS service retains the output tag through flush/readout and
  // serializes PE-state reuse. Two RS slots backpressure the next PRELOAD;
  // four permit early CPU admission but never early execution/result access.
  for (const auto slots : {2u,4u}) {
    auto selected=epoch_config(); selected.reservations[1]=slots;
    selected.serialized_output_stationary_epochs=true;
    Engine engine(128,epoch_resources()); std::vector<std::string> missing;
    StagedObserver scheduler(engine,selected,100,[&](const auto &s){missing.push_back(s);},0,64,4,32);
    Event configuration{0,{},{},{},1};
    scheduler.submit("config",configuration,1,0,1ull<<16,1ull<<48);
    const ValueId descriptor=101, output=64;
    Event preload{2,{}, {&descriptor,1},{},4};
    Event compute{3,{&descriptor,1},{&output,1},{},30};
    scheduler.submit("preload",preload,4,6,0xffffffffu,0x80000000u);
    const auto first=scheduler.submit("compute_os",compute,30,4,0xffffffffu,0xffffffffu);
    const auto admitted=scheduler.submit("preload",preload,4,6,0xffffffffu,0x80000000u);
    const auto second=scheduler.submit("compute_os",compute,30,4,0xffffffffu,0xffffffffu);
    assert(first.ready && second.ready && second.start>=*first.ready);
    assert(slots==2 ? admitted.issue==first.ready : admitted.issue<first.ready);
    Event store{4,{&output,1},{},{},2};
    const auto stored=scheduler.submit("store",store,1,3,0,0);
    assert(stored.start>=*second.ready && engine.report().complete && missing.empty());
  }
  // OS PRELOAD obtains A from the following compute lookahead. It cannot
  // feed the transposer before an outstanding input DMA has completed.
  {
    auto selected=epoch_config(); selected.serialized_output_stationary_epochs=true;
    Engine engine(128,epoch_resources());
    StagedObserver scheduler(engine,selected,100,{},0,64,4,32);
    Event configuration{0,{},{},{},1};
    scheduler.submit("config",configuration,1,0,1ull<<16,1ull<<48);
    const ValueId input=0,descriptor=101;
    Event load{1,{}, {&input,1},{},50};
    const auto loaded=scheduler.submit("load",load,1,2,0,0);
    Event preload{2,{}, {&descriptor,1},{},4};
    scheduler.submit("preload",preload,4,6,0xffffffffu,0x80000000u);
    const ValueId reads[]={descriptor,input};
    Event compute{3,{reads,2},{},{},30};
    const auto computed=scheduler.submit("compute_os",compute,30,4,0xffffffffu,0xffffffffu);
    assert(loaded.ready && computed.ready && engine.ready(descriptor)>=*loaded.ready+4);
  }
  // The conservative mode uses bounded live resource holds, not unused global
  // phase ancestry. A long legal pipeline must not fail after 4096 commands.
  {
    Engine engine(128,epoch_resources()); std::vector<std::string> missing;
    StagedObserver scheduler(engine,epoch_config(),100,[&](const auto &s){missing.push_back(s);},0,64,4,32);
    Event configured{0,{},{},{},1};
    scheduler.submit("config",configured,1,0,4 | (1ull<<16),1ull<<48);
    const ValueId descriptor=101;
    Event preload{2,{}, {&descriptor,1},{},3};
    Event compute{3,{&descriptor,1},{},{},50};
    Cycle completed=0;
    for (unsigned iteration=0; iteration<5000; ++iteration) {
      scheduler.submit("preload",preload,1,6,0xffffffffu,0x80000000u);
      const auto result=scheduler.submit("compute_ws",compute,1,4,0xffffffffu,0xffffffffu);
      assert(result.ready && result.start>=completed);
      completed=*result.ready;
    }
    assert(missing.empty() && engine.report().complete && completed>0);
  }
  // Independent LD can overlap EX; reusing the bank waits its full lifetime.
  for (const auto row : {0u,16u}) {
    auto selected=epoch_config(); Engine engine(128,epoch_resources());
    StagedObserver scheduler(engine,selected,100,{},0,64,4,32);
    const ValueId input=0, output=row;
    Event compute{0,{&input,1},{},{},50};
    const auto first=scheduler.submit("compute_ws",compute,1,4,0xffffffffu,0xffffffffu);
    Event load{1,{}, {&output,1},{},10};
    const auto second=scheduler.submit("load",load,1,2,0,0);
    assert(first.ready && second.ready);
    assert(row==16 ? second.start<*first.ready : second.start>=*first.ready);
  }
  // Store dependencies clear on completion, not FIFO dequeue/issue.
  {
    Engine engine(128,epoch_resources()); StagedObserver scheduler(engine,epoch_config(),100,{},0,64,4,32);
    Event first{0,{},{},{},50}, second{1,{},{},{},2};
    const auto a=scheduler.submit("store",first,1,3,0,0);
    const auto b=scheduler.submit("store",second,1,3,0,0);
    assert(a.ready && b.start>=*a.ready);
  }
  // No unpriced completion, OS, or transposed sequence gains an epoch permit.
  for (const auto mode : {0u,4u,260u}) {
    Engine engine(128,epoch_resources()); std::vector<std::string> missing;
    StagedObserver scheduler(engine,epoch_config(),100,[&](const auto &s){missing.push_back(s);},0,64,4,32);
    Event configuration{0,{},{},{},1}; scheduler.submit("config",configuration,1,0,mode,0);
    Event compute{2,{},{},{},mode==4 ? std::nullopt : std::optional<Cycle>{50}};
    scheduler.submit("compute_ws",compute,1,4,0xffffffffu,0xffffffffu);
    Event preload{3,{},{},{},1};
    assert(!scheduler.submit("preload",preload,1,6,0xffffffffu,0xffffffffu).ready);
    assert(!missing.empty());
  }
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
