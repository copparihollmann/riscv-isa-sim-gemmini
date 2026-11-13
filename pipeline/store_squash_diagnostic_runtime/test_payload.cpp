#include "empirical_engine.hpp"
#include <iostream>
#include <stdexcept>
static unsigned checks=0;
static void check(bool x){if(!x)throw std::runtime_error("payload phase assertion");++checks;}
template<class F>void reject(F f){bool caught=false;try{f();}catch(const std::logic_error&){caught=true;}check(caught);}
int main(){
 iris::Machine m(3,1000);m.configure_resource("COM",2);m.configure_resource("memory",1);
 reject([&]{m.set_completing_payload(0,8);});
 iris::NodeId store=0,peer=0;iris::Op a{0,"store.COM","COM",3,1};a.retires=false;
 a.on_complete=[&]{check(!m.nodes().at(store).completed&&m.nodes().at(store).op.bytes==0);reject([&]{m.set_completing_payload(peer,8);});m.set_completing_payload(store,8);check(m.nodes().at(store).op.bytes==8);};store=m.issue(std::move(a));
 iris::Op b{1,"other.COM","COM",5,1};b.bytes=4;b.retires=false;b.on_complete=[&]{reject([&]{m.set_completing_payload(peer,8);});m.set_completing_payload(peer,4);};peer=m.issue(std::move(b));
 m.run_until(2);check(m.nodes().at(store).op.bytes==0&&!m.nodes().at(store).completed);reject([&]{m.set_completing_payload(store,8);});
 m.run_until(3);check(m.nodes().at(store).completed&&m.nodes().at(store).op.bytes==8);reject([&]{m.set_completing_payload(store,8);});m.drain();check(m.nodes().at(peer).op.bytes==4&&m.nodes().at(peer).completed);
 iris::Op accepted{2,"accepted-store-response","memory",4,1};accepted.retires=false;auto id=m.issue(std::move(accepted));reject([&]{m.cancel(id,"not-CPU-work");});m.drain();check(m.nodes().at(id).completed);
 iris::Machine bounded(3,1000);bounded.retain_history(false);bounded.configure_resource("COM",1);
 uint64_t published=0;
 for(unsigned i=0;i<10000;++i){
  iris::NodeId token=0;iris::Op next{i%3,"store.COM","COM",1,1};next.retires=false;
  next.on_complete=[&]{bounded.set_completing_payload(token,8);published+=bounded.nodes().at(token).op.bytes;};
  token=bounded.issue(std::move(next));bounded.drain();check(bounded.retained_nodes()==0);
  reject([&]{bounded.set_completing_payload(token,8);});
 }
 check(published==80000&&bounded.completed_total()==10000);
 std::cout<<"PASS checks="<<checks<<'\n';
}
