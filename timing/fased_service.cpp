#include "fased_service.hpp"
#include "fased_service_identity.hpp"
#include "VFASEDLatencyPipe.h"
#include "verilated.h"
#include <stdexcept>
#include <utility>

namespace iris::fased {
namespace {
struct OwnerContext {
  VerilatedContext* previous=Verilated::threadContextp();
  explicit OwnerContext(VerilatedContext* owner) { Verilated::threadContextp(owner); }
  ~OwnerContext() { Verilated::threadContextp(previous); }
};
}
struct Model::Impl {
  Parameters parameters;
  std::unique_ptr<VerilatedContext> context;
  std::unique_ptr<VFASEDLatencyPipe> model;
  bool evaluated=false, evaluated_reset=false, reset_seen=false;
  std::uint64_t edges=0;
  explicit Impl(Parameters p,unsigned seed,const std::vector<std::string>& arguments):parameters(p) {
    if(!p.read_latency||!p.write_latency||p.read_max_requests<1||p.read_max_requests>16||p.write_max_requests<1||p.write_max_requests>16)
      throw std::invalid_argument("IRIS_FASED_EXPLICIT_PARAMETERS_OUTSIDE_QUALIFIED_ENVELOPE");
    // A new VerilatedContext changes the thread context. Preserve the caller
    // even across allocation, model construction or command-argument failures.
    auto* previous=Verilated::threadContextp();
    try {
      context=std::make_unique<VerilatedContext>();
      OwnerContext scoped(context.get());
      context->randSeed(seed);context->randReset(2);
      std::vector<const char*> argv;for(const auto& s:arguments)argv.push_back(s.c_str());
      context->commandArgs(argv.size(),argv.data());
      model=std::make_unique<VFASEDLatencyPipe>(context.get());
      model->clock=0;
    } catch(...) { Verilated::threadContextp(previous);throw; }
    Verilated::threadContextp(previous);
  }
  ~Impl() {
    if(context) { OwnerContext scoped(context.get());model.reset(); }
  }
};
Model::Model(Parameters p,unsigned seed,std::vector<std::string> args):impl_(std::make_unique<Impl>(p,seed,args)){}
Model::~Model()=default;
Model::Model(Model&&) noexcept=default;
Model& Model::operator=(Model&&) noexcept=default;
const char* Model::source_identity() const {return IRIS_FASED_SERVICE_SOURCE_ID;}
std::uint64_t Model::committed_edges() const {if(!impl_)throw std::logic_error("moved FASED model");return impl_->edges;}
// BEGIN GENERATED PHYSICAL PORT MAP
