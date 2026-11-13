#include "store_front_completion_runtime/empirical_engine.hpp"
#include <iostream>
#include <stdexcept>
#include <vector>
unsigned checks=0;
void check(bool value){if(!value)throw std::runtime_error("completion receipt assertion");++checks;}
template<class F>void reject(F&&f){bool caught=false;try{f();}catch(const std::logic_error&){caught=true;}check(caught);}
void simultaneous(bool bounded){
 iris::Machine m(3,1000);m.retain_history(!bounded);m.configure_resource("COM",1);m.configure_resource("EX",1);m.configure_resource("memory",1);
 iris::NodeId younger=0,response=0;std::vector<iris::NodeId>deferred;
 iris::Op older{2,"store.COM","COM",3,1};older.retires=false;older.cancellable=true;
 older.on_complete=[&]{const auto&n=m.nodes().at(younger);check(n.issued&&!n.completed&&n.end==m.now()&&n.op.cancellable);deferred.push_back(younger);iris::Op memory{2,"accepted-store-response","memory",5,1};memory.retires=false;response=m.issue(std::move(memory));};
 m.issue(std::move(older));iris::Op ex{2,"younger.EX","EX",3,1};ex.retires=false;ex.cancellable=true;younger=m.issue(std::move(ex));
 m.run_until(3);check(m.completed_total()==2&&deferred.size()==1);
 if(bounded){check(younger<m.nodes().base());reject([&]{m.mark_squashed(younger,"original guard remains strict");});}
 const bool retained=m.mark_cpu_completed_this_cycle_squashed(younger,"actual-same-edge-CPU-work");check(retained==!bounded);
 if(retained)check(m.nodes().at(younger).squashed&&m.nodes().at(younger).completed);
 reject([&]{m.mark_cpu_completed_this_cycle_squashed(response,"pending memory is not CPU completion");});
 reject([&]{m.mark_cpu_completed_this_cycle_squashed(younger,"");});
 m.drain();check(m.now()==8&&m.completed_total()==3);reject([&]{m.mark_cpu_completed_this_cycle_squashed(younger,"older cycle receipt expired");});reject([&]{m.mark_cpu_completed_this_cycle_squashed(response,"completed accepted memory remains excluded");});
 iris::Op canceled{0,"canceled.COM","COM",1,1};canceled.retires=false;canceled.cancellable=true;auto id=m.issue(std::move(canceled));m.cancel(id,"annulled before issue");reject([&]{m.mark_cpu_completed_this_cycle_squashed(id,"cancel is not completion");});
 check(m.completed_busy_by_resource().at("EX")==3&&m.completed_busy_by_resource().at("COM")==3&&m.completed_busy_by_resource().at("memory")==5);
}
void previous_edge(bool bounded){
 iris::Machine m(3,1000);m.retain_history(!bounded);m.configure_resource("MEM",1);m.configure_resource("EX",1);iris::NodeId younger=0;
 iris::Op branch{0,"branch.MEM","MEM",2,1};branch.retires=false;branch.cancellable=true;
 branch.on_complete=[&]{check(m.nodes().at(younger).completed&&m.nodes().at(younger).end==1);m.mark_squashed(younger,"prior-edge-EX source branch kill");check(m.nodes().at(younger).squashed);reject([&]{m.mark_cpu_completed_this_cycle_squashed(younger,"current-edge API must reject previous-edge work");});};
 m.issue(std::move(branch));iris::Op ex{0,"younger.EX","EX",1,1};ex.retires=false;ex.cancellable=true;younger=m.issue(std::move(ex));m.drain();check(m.completed_total()==2&&m.now()==2);
}
int main(){simultaneous(false);simultaneous(true);previous_edge(false);previous_edge(true);std::cout<<"PASS checks="<<checks<<'\n';}
