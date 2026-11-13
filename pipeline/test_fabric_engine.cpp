#include "fabric_engine.hpp"
#include <iostream>
#include <sstream>
#include <stdexcept>
static unsigned checks=0,refusals=0;
static void check(bool yes,const char*why){++checks;if(!yes)throw std::runtime_error(why);}
template<class F>static void reject(F f){try{f();}catch(const std::logic_error&){++refusals;return;}throw std::runtime_error("missing physical lifecycle guard");}
int main(){try{
  iris::Machine m(3,10);m.configure_resource("cpu",1);m.configure_resource("physical",1);
  auto read=m.accept_physical({2,"cache-load","physical",0x80000000,8,0,{},"source-cache-witness",true});
  check(!m.next_event_cycle()&&m.now()==0,"external acceptance creates no guessed completion event");
  reject([&]{m.finish_physical(read);});reject([&]{m.cancel(read,"kill");});reject([&]{m.drain();});
  std::ostringstream unfinished;m.write_json(unfinished,true);check(unfinished.str().find("\"pending_operations\":1")!=std::string::npos,"accepted physical actor remains pending in snapshot");
  check(unfinished.str().find("\"physical_acceptance\":true")!=std::string::npos&&unfinished.str().find("\"completed\":false")!=std::string::npos,"just-accepted source request is exported as unfinished acceptance point");
  auto independent=m.issue({2,"independent-ALU","cpu",1,1});m.run_until(1);check(m.nodes()[independent].completed&&!m.nodes()[read].completed,"independent CPU advances while load has no response");
  m.run_until(30);m.finish_physical(read);check(m.nodes()[read].start==0&&m.nodes()[read].end==30&&m.minstret(2)==1,"physical response finishes on supplied edge without extra instruction retirement");reject([&]{m.finish_physical(read);});
  auto mac=m.record_physical_edge({0,"source-int8-cell","physical",0x80000100,0,256,{read},"source-cell-witness",true});
  check(m.now()==30&&m.nodes()[mac].completed&&m.nodes()[mac].physical_edge&&m.nodes()[mac].start==30&&m.nodes()[mac].end==30,"same-edge physical MAC is a point event without invented occupancy");
  auto fp=m.accept_physical({1,"source-FP8-cell","physical",0x80000104,0,256,{mac},"source-cell-witness",true});m.run_until(32);m.finish_physical(fp);
  std::ostringstream final;m.write_json(final);check(final.str().find("\"physical_edge\":true")!=std::string::npos&&final.str().find("same-source-edge")!=std::string::npos,"point marker explicit in final graph");
  check(!m.next_event_cycle()&&m.minstret(0)==0&&m.minstret(1)==0,"physical payload never creates instruction or queue events");
  std::cout<<"{\"status\":\"passed_source_physical_lifecycle\",\"checks\":"<<checks<<",\"guard_refusals\":"<<refusals<<",\"queued_synthetic_events\":0}\n";
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
