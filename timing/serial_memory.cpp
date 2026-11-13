#include "serial_memory.hpp"
#include "serial_memory_identity.hpp"
#include "VIrisSerialMemoryPath.h"
#include "verilated.h"
#include <stdexcept>
namespace iris::serial_memory {
namespace {
struct OwnerContext {
  VerilatedContext* previous=Verilated::threadContextp();
  explicit OwnerContext(VerilatedContext*owner){Verilated::threadContextp(owner);}
  ~OwnerContext(){Verilated::threadContextp(previous);}
};
}
struct Model::Impl {
  std::unique_ptr<VerilatedContext> context;
  std::unique_ptr<VIrisSerialMemoryPath> model;
  bool evaluated=false,iris_reset=false,bringup_reset=false;
  AssertionPolicy assertion_policy;
  unsigned reset_seen=0;
  std::uint64_t phases=0;
  explicit Impl(unsigned seed,const std::vector<std::string>&args,AssertionPolicy policy):assertion_policy(policy){
    auto*previous=Verilated::threadContextp();
    try{
      context=std::make_unique<VerilatedContext>();OwnerContext scoped(context.get());context->randSeed(seed);context->randReset(2);
      std::vector<const char*>argv;for(const auto&s:args)argv.push_back(s.c_str());context->commandArgs(argv.size(),argv.data());
      model=std::make_unique<VIrisSerialMemoryPath>(context.get());model->iris_clock=model->bringup_clock=model->serial_clock=0;
    }catch(...){Verilated::threadContextp(previous);throw;}
    Verilated::threadContextp(previous);
  }
  ~Impl(){if(context){OwnerContext scoped(context.get());model.reset();}}
};
Model::Model(unsigned seed,std::vector<std::string>args,AssertionPolicy policy):impl_(std::make_unique<Impl>(seed,args,policy)){}
Model::~Model()=default;
Model::Model(Model&&)noexcept=default;
Model&Model::operator=(Model&&)noexcept=default;
const char*Model::source_identity()const{return IRIS_SERIAL_MEMORY_SOURCE_ID;}
std::uint64_t Model::committed_phases()const{if(!impl_)throw std::logic_error("moved SerialTL model");return impl_->phases;}
void Model::commit(Edges edges){
  if(!impl_||!impl_->evaluated)throw std::logic_error("IRIS_SERIAL_MEMORY_COMMIT_REQUIRES_EVALUATION");
  if(!edges.iris&&!edges.bringup&&!edges.serial)throw std::invalid_argument("IRIS_SERIAL_MEMORY_EMPTY_EDGE_SET");
  OwnerContext scoped(impl_->context.get());auto&m=*impl_->model;
  m.iris_clock=edges.iris;m.bringup_clock=edges.bringup;m.serial_clock=edges.serial;m.eval();
  m.iris_clock=m.bringup_clock=m.serial_clock=0;m.eval();
  if(impl_->iris_reset&&edges.iris)impl_->reset_seen|=1;
  if(impl_->bringup_reset&&edges.bringup)impl_->reset_seen|=2;
  if(impl_->iris_reset&&impl_->bringup_reset&&edges.serial)impl_->reset_seen|=4;
  impl_->evaluated=false;++impl_->phases;
}
// BEGIN GENERATED PHYSICAL PORT MAP
