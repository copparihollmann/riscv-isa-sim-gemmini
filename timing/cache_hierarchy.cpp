// Implementation body is generated into the isolated build from its exact
// physical-port manifest. No Verilated internals appear in the public SDK.
#include "cache_hierarchy.hpp"
#include "cache_hierarchy_identity.hpp"
#include "VCacheShuttle.h"
#include "VCacheShuttle___024root.h"
#include "VCacheRocket.h"
#include "VCacheL2.h"
#include "verilated.h"
#include <stdexcept>
#include <string>

namespace iris::cache {
struct Model::Impl {
  Component kind;
  std::unique_ptr<VerilatedContext> context;
  std::unique_ptr<VCacheShuttle> shuttle;
  std::unique_ptr<VCacheRocket> rocket;
  std::unique_ptr<VCacheL2> l2;
  bool evaluated=false;
  UnresetReplayPolicy replay_policy;
  std::array<std::array<bool,16>,4> replay_command_known{};
  bool pending_unknown_replay=false;
  bool concretized_unknown_replay=false;
  bool reset_seen=false;
  bool evaluated_reset=false;
  std::uint64_t edge_count=0;
  explicit Impl(Component component,std::uint32_t seed,UnresetReplayPolicy policy):kind(component),context(std::make_unique<VerilatedContext>()),replay_policy(policy) {
    context->randReset(2);context->randSeed(seed);
    switch(kind){
      case Component::ShuttleL1D:shuttle=std::make_unique<VCacheShuttle>(context.get());shuttle->clock=0;break;
      case Component::RocketL1D:rocket=std::make_unique<VCacheRocket>(context.get());rocket->clock=0;break;
      case Component::InclusiveL2:l2=std::make_unique<VCacheL2>(context.get());l2->clock=0;break;
      default:throw std::invalid_argument("unknown saved cache component");
    }
  }
};
Model::Model(Component kind,std::uint32_t seed,UnresetReplayPolicy policy):impl_(std::make_unique<Impl>(kind,seed,policy)){}
Model::~Model()=default;
Component Model::component()const{return impl_->kind;}
bool Model::concretized_unknown_replay_timing()const{return impl_->concretized_unknown_replay;}
std::uint64_t Model::edges()const{return impl_->edge_count;}
const char* Model::source_identity(){return IRIS_CACHE_HIERARCHY_SOURCE_ID;}
std::vector<Bits> Model::step(std::span<const Bits> inputs){evaluate(inputs);auto out=sample();commit();return out;}
// BEGIN GENERATED PHYSICAL PORT MAP
