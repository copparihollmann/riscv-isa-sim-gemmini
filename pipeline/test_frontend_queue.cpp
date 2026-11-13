#include "frontend_queue.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>

using iris::frontend::ShuttleFetchQueue;
int main(int argc,char**argv) {
  if(argc!=2)throw std::invalid_argument("expected RTL queue transition corpus");
  std::ifstream file(argv[1]);unsigned reset,clear,ev,mask,r0,r1,bv,be,bd,av,ae,ad;uint64_t rows=0;
  while(file>>reset>>clear>>ev>>mask>>r0>>r1>>bv>>be>>bd>>av>>ae>>ad) {
    auto q=reset?ShuttleFetchQueue():ShuttleFetchQueue({uint8_t(bv),uint8_t(be),uint8_t(bd)});
    q.clock({bool(reset),bool(clear),bool(ev),uint8_t(mask),bool(r0),bool(r1)});auto s=q.state();
    if(s.valid!=av || s.enq!=ae || s.deq!=ad)throw std::runtime_error("actual RTL queue differs row="+std::to_string(rows));
    ++rows;
  }
  if(!file.eof() || rows<100000)throw std::runtime_error("truncated queue corpus");
  ShuttleFetchQueue full({127,1,1});if(full.enqueue_ready(1))throw std::runtime_error("dequeue speculated as enqueue capacity");
  full.clock({false,false,true,1,true,true});if(full.state().valid!=124 || full.state().enq!=1 || full.state().deq!=4)throw std::runtime_error("full simultaneous dequeue priority changed");
  full.clock({false,true,true,15,true,true});if(full.state().valid || full.state().enq!=1 || full.state().deq!=1)throw std::runtime_error("clear priority changed");
  std::cout<<"PASS actual RTL queue transitions="<<rows<<" plus capacity/clear controls\n";
}
