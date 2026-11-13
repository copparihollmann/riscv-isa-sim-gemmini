#include "frontend_engine.hpp"
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <iostream>
int main(int argc,char**argv) {
  if(argc!=2)throw std::invalid_argument("output graph path required");
  iris::Machine m(3,2);m.configure_resource("cpu",2);m.configure_resource("accepted-ifetch",1);
  unsigned effects=0;
  auto cpu=[&](const char* name,unsigned hart,iris::Cycle duration,iris::Cycle earliest=0) {
    iris::Op op{hart,name,"cpu",duration,1};op.earliest=earliest;op.on_complete=[&]{++effects;};op.cancellable=true;op.retires=false;return op;
  };
  auto pending=m.issue(cpu("pending-WB",0,2,20));m.cancel(pending,"source MEM redirect");
  auto inflight=m.issue(cpu("inflight-EX",1,10));m.run_until(3);m.cancel(inflight,"source MEM redirect");
  // The older resolution callback cancels a same-edge younger completion.
  iris::NodeId younger=0;auto older=cpu("older-MEM-redirect",0,2);older.retires=false;
  older.on_complete=[&]{m.cancel(younger,"same-edge source MEM redirect");};m.issue(older);
  auto young=cpu("younger-EX",0,2);young.retires=false;younger=m.issue(young);
  m.drain();
  auto done=m.issue(cpu("completed-wrongpath-EX",1,1));m.drain();m.mark_squashed(done,"older branch resolves after this work");
  iris::Op memory{2,"accepted-Icache-refill","accepted-ifetch",4,1};memory.retires=false;memory.on_complete=[&]{effects+=100;};auto request=m.issue(memory);
  unsigned refused=0;try{m.cancel(request,"wrongpath must not kill accepted request");}catch(const std::logic_error&){++refused;}
  try{m.cancel(done,"cannot undo completed work");}catch(const std::logic_error&){++refused;}
  try{m.cancel(pending,"duplicate");}catch(const std::logic_error&){++refused;}
  try{m.cancel(request,"");}catch(const std::invalid_argument&){++refused;}
  m.drain();
  if(effects!=101 || m.minstret(0)!=0 || m.minstret(1)!=0 || refused!=4)throw std::runtime_error("cancel/squash callbacks or retirement changed");
  const auto& p=m.nodes()[pending];const auto& e=m.nodes()[inflight];const auto& y=m.nodes()[younger];
  if(p.issued || !p.cancelled || p.completed || p.start!=p.end || p.end!=p.cancel_cycle)throw std::runtime_error("pending cancellation span");
  if(!e.issued || e.completed || e.end!=3 || e.cancel_cycle!=3 || !y.cancelled || y.completed)throw std::runtime_error("issued/sameedge cancellation span");
  std::ofstream output(argv[1]);m.write_json(output);output.close();
  std::cout<<"PASS source CPU cancellation pending/inflight/sameedge/completed-work plus accepted-memory control; effects="<<effects<<" refusals="<<refused<<"\n";
}
