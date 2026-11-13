#include "frontend_values.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
using iris::frontend::ForwardedValues;
static uint32_t add(unsigned rd,unsigned rs1,unsigned rs2) {return rs2<<20|rs1<<15|rd<<7|0x33;}
int main(int argc,char**argv) {
  if(argc!=2)throw std::invalid_argument("independent ALU corpus required");
  std::ifstream file(argv[1]);uint64_t raw,pc,a,b,want,rows=0;
  while(file>>raw>>pc>>a>>b>>want) {
    const auto op=iris::frontend::PureAluValue::decode(raw);
    if(!op || op->evaluate(pc,a,b)!=want)throw std::runtime_error("independent ALU value differs row="+std::to_string(rows));
    ++rows;
  }
  if(!file.eof() || rows<20000)throw std::runtime_error("truncated ALU corpus");
  ForwardedValues::Snapshot initial{};initial[1]=10;initial[2]=20;initial[3]=40;initial[4]=80;
  ForwardedValues flow(initial);
  flow.issue(1,add(5,1,2),0x80000000);flow.issue(2,add(5,3,4),0x80000004);flow.issue(3,add(6,5,1),0x80000008);
  auto branch_sources=flow.latch(5,6);
  unsigned refuses=0;
  try{flow.complete(3);}catch(const std::logic_error&){++refuses;}
  if(flow.complete(2)!=ForwardedValues::Value(120) || flow.complete(1)!=ForwardedValues::Value(30) || flow.complete(3)!=ForwardedValues::Value(130))throw std::runtime_error("private RAW/WAW value versions");
  if(flow.future(5)!=ForwardedValues::Value(120) || flow.future(6)!=ForwardedValues::Value(130) || flow.architectural()[5] || flow.architectural()[6])throw std::runtime_error("speculative value leaked to architecture");
  if(flow.read(branch_sources)!=std::array<ForwardedValues::Value,2>{120,130})throw std::runtime_error("branch source version latch");
  try{flow.commit(2,120);}catch(const std::logic_error&){++refuses;}
  try{flow.commit(1,31);}catch(const std::logic_error&){++refuses;}
  flow.commit(1,30);flow.commit(2,120);flow.commit(3,130);
  try{flow.discard_younger(1);}catch(const std::logic_error&){++refuses;}
  ForwardedValues rollback(initial);rollback.issue(10,add(5,1,2),0);rollback.complete(10);rollback.issue(11,add(5,3,4),4);rollback.complete(11);
  const auto canceled=rollback.latch(5,0);rollback.discard_younger(10);
  if(rollback.future(5)!=ForwardedValues::Value(30))throw std::runtime_error("rollback selected wrong surviving writer");
  try{rollback.read(canceled);}catch(const std::logic_error&){++refuses;}
  rollback.issue(12,add(6,5,1),8);if(rollback.complete(12)!=ForwardedValues::Value(40))throw std::runtime_error("post-cancel value flow");
  ForwardedValues unknown({});unknown.issue(1,add(5,1,2),0);if(unknown.complete(1))throw std::runtime_error("unknown operands manufactured a value");
  unknown.issue(2,add(6,5,0),4);if(unknown.complete(2))throw std::runtime_error("unknown result became branch-safe");
  if(unknown.future(0)!=ForwardedValues::Value(0))throw std::runtime_error("x0 lost defined value");
  ForwardedValues counters(initial);counters.issue_external(1,5);counters.issue(2,add(6,5,1),4);
  try{counters.complete(2);}catch(const std::logic_error&){++refuses;}
  counters.complete_external(1,77);if(counters.complete(2)!=ForwardedValues::Value(87))throw std::runtime_error("late CSR/response result forwarding");
  counters.commit(1,77);counters.commit(2,87);
  ForwardedValues constants({});constants.issue(1,0x0010c2b3,0);
  if(constants.complete(1)!=ForwardedValues::Value(0))throw std::runtime_error("unknown self-XOR lost source constant");
  constants.issue(2,0x0000f313,4);if(constants.complete(2)!=ForwardedValues::Value(0))throw std::runtime_error("ANDI0 lost source constant");
  constants.issue(3,0xfff0e393,8);if(constants.complete(3)!=ForwardedValues::Value(~uint64_t(0)))throw std::runtime_error("ORI-1 lost source constant");
  for(uint32_t bad:{0x00003003u,0x02000033u,0x00000063u,0x00000073u,0x0000101bu|0x02000000u})
    if(iris::frontend::PureAluValue::decode(bad))throw std::runtime_error("pure shadow domain broadened");
  if(refuses!=6)throw std::runtime_error("missing value-flow precision refusal");
  std::cout<<"PASS independent pure-ALU values="<<rows<<" RAW/WAW/COM/cancel/unknown controls=8 refusals=6\n";
}
